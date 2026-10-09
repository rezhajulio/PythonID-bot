"""
AI-based moderation monitoring via classifier.dev (monitor-only).

Messages that survive every enforcement handler reach this handler last
(handler_group 7). Text is classified in a background task so the update
pipeline is never blocked by the network call. One multi-label
classification covers the spam, hostile, and trolling aspects at once
(see ``AI_SPAM_LABELS``). High-confidence flags are reported to the
configured admin chat (``ai_spam_alert_chat_id``) with inline buttons so
a human admin can delete, delete+restrict, delete+ban, or dismiss. This
handler never deletes, restricts, or warns on its own and raises no
``ApplicationHandlerStop``.

Profile metadata (photo/username) is fetched locally for the alert only;
it is never sent to the classification API.
"""

import logging
import time

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update, User

from bot.dispatch import (
    HandlerContext,
    HandlerSpec,
    callback_data_pattern,
    effective_chat,
    effective_message,
    effective_user,
    is_command_message,
    is_group_chat,
)

from bot.config import get_settings
from bot.constants import (
    AI_SPAM_ACTION_LABELS,
    AI_SPAM_ALERT,
    AI_SPAM_ALERT_HANDLED,
    AI_SPAM_BUTTON_DELETE,
    AI_SPAM_BUTTON_DELETE_BAN,
    AI_SPAM_BUTTON_DELETE_RESTRICT,
    AI_SPAM_BUTTON_DISMISS,
    AI_SPAM_CB_MESSAGE_GONE,
    AI_SPAM_CB_NOT_ADMIN,
    AI_SPAM_INSTRUCTIONS,
    AI_SPAM_LABELS,
    AI_SPAM_MAX_LABELS,
    RESTRICTED_PERMISSIONS,
)
from bot.group_config import get_group_registry
from bot.services.classifier_client import (
    DEFAULT_DAILY_BUDGET,
    ClassificationResult,
    breaker_is_open,
    classify_text,
    daily_budget_exhausted,
    try_spend_budget,
)
from bot.services.telegram_utils import (
    is_user_admin_in_group,
    is_user_admin_or_trusted,
    restrict_chat_member_with_retry,
)
from bot.services.user_checker import check_user_profile

logger = logging.getLogger(__name__)

def _classifiable_text(message: Message) -> str:
    """Return the text available for classification: body text or media caption."""
    return message.text or message.caption or ""


def ai_spam_filter(update: Update) -> bool:
    """Match group text/caption messages that are not commands."""
    if not is_group_chat(update) or is_command_message(update):
        return False
    message = effective_message(update)
    return message is not None and bool(_classifiable_text(message).strip())


AI_SPAM_FILTER = ai_spam_filter
AI_SPAM_CALLBACK_PATTERN = r"^aispam:(del|delres|delban|dismiss):-?\d+:\d+:\d+$"

AI_SPAM_MIN_LENGTH = 20
AI_SPAM_ALERT_MESSAGE_MAX_LEN = 500

ALERTS_KEY = "ai_spam_alerts"
ALERTS_MAX_SIZE = 500

ACTION_DELETE = "del"
ACTION_DELETE_RESTRICT = "delres"
ACTION_DELETE_BAN = "delban"
ACTION_DISMISS = "dismiss"


def build_alert_keyboard(
    group_id: int, user_id: int, message_id: int
) -> InlineKeyboardMarkup:
    """Build the admin action keyboard for a suspected spam message."""
    suffix = f":{group_id}:{user_id}:{message_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=AI_SPAM_BUTTON_DELETE, callback_data=f"aispam:{ACTION_DELETE}{suffix}"),
            InlineKeyboardButton(text=AI_SPAM_BUTTON_DISMISS, callback_data=f"aispam:{ACTION_DISMISS}{suffix}"),
        ],
        [
            InlineKeyboardButton(text=AI_SPAM_BUTTON_DELETE_RESTRICT, callback_data=f"aispam:{ACTION_DELETE_RESTRICT}{suffix}"),
            InlineKeyboardButton(text=AI_SPAM_BUTTON_DELETE_BAN, callback_data=f"aispam:{ACTION_DELETE_BAN}{suffix}"),
        ],
    ])


def truncate_alert_text(text: str, max_length: int = AI_SPAM_ALERT_MESSAGE_MAX_LEN) -> str:
    """Truncate the quoted message so the alert stays readable."""
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "…"


def plain_mention(user: User) -> str:
    """Plain-text mention for alerts sent without parse_mode.

    ``get_user_mention`` returns Markdown, which would render literally
    in a plain-text alert; the alert already shows the numeric ID.
    """
    return f"@{user.username}" if user.username else user.full_name


def _already_alerted(context: HandlerContext, key: tuple[int, int]) -> bool:
    alerts: dict[tuple[int, int], int] = context.state.data.setdefault(ALERTS_KEY, {})
    if len(alerts) >= ALERTS_MAX_SIZE:
        for oldest in list(alerts)[: ALERTS_MAX_SIZE // 2]:
            del alerts[oldest]
    if key in alerts:
        return True
    alerts[key] = 0
    return False


def _get_group_config(context: HandlerContext, group_id: int):
    try:
        return get_group_registry().get(group_id)
    except RuntimeError:
        logger.error("Group registry not initialized; skipping AI spam alert")
        return None


async def _fetch_profile_status(
    context: HandlerContext, user: User
) -> str:
    """Best-effort local profile completeness note for the alert."""
    try:
        result = await check_user_profile(context.bot, user)
        if result.is_complete:
            return "lengkap (foto + username)"
        return "tidak lengkap: tanpa " + ", tanpa ".join(result.get_missing_items())
    except Exception:
        logger.debug("ai_spam_monitor: profile check failed", exc_info=True)
        return "tidak diketahui"


def flagged_aspects(
    result: ClassificationResult, threshold: float, valid_labels: tuple[str, ...]
) -> list[tuple[str, float]]:
    """Return non-benign aspects at or above ``threshold``, highest score first.

    Multi-label results carry independent per-label ``scores``. Only labels
    the caller requested (``valid_labels``) can flag — an unexpected label
    in the API response never reaches the alert — and the benign anchor
    never flags. Single-label (legacy) results fall back to the
    label + confidence check under the same whitelist.
    """
    flaggable = set(valid_labels) - {"benign"}
    if result.scores:
        flagged = [
            (label, score)
            for label, score in result.scores.items()
            if label in flaggable and score >= threshold
        ]
        return sorted(flagged, key=lambda item: item[1], reverse=True)
    if (
        result.label in flaggable
        and result.confidence is not None
        and result.confidence >= threshold
    ):
        return [(result.label, result.confidence)]
    return []


async def _classify_and_alert(
    context: HandlerContext,
    group_id: int,
    user: User,
    message_id: int,
    message_text: str,
) -> None:
    """Classify one message off the update path and alert on high confidence.

    Runs as a background task: every failure path returns quietly, and the
    circuit breaker + daily budget stop a dead or rate-limited upstream
    from being hammered.
    """
    settings = get_settings()
    # Log-friendly sender/text snippets: no "@None" for users without a
    # handle, and truncated text so one long message can't bloat the logs.
    username_display = f"@{user.username}" if user.username else "none"
    text_snippet = truncate_alert_text(message_text)
    if breaker_is_open(
        time.monotonic(), cooldown_seconds=settings.classifier_cooldown_seconds
    ):
        logger.debug("ai_spam_monitor: circuit open, skipping classification")
        return
    if not try_spend_budget(
        getattr(settings, "ai_spam_daily_budget", DEFAULT_DAILY_BUDGET)
    ):
        logger.warning("ai_spam_monitor: daily budget exhausted, skipping classification")
        return

    result = await classify_text(
        message_text,
        labels=list(AI_SPAM_LABELS),
        instructions=AI_SPAM_INSTRUCTIONS,
        timeout=settings.classifier_timeout_seconds,
        multi=True,
        max_labels=AI_SPAM_MAX_LABELS,
    )
    if result is None:
        logger.info(
            f"ai_spam_monitor: classification failed for user_id={user.id} "
            f"username={username_display} name={user.full_name!r} "
            f"group={group_id} message_id={message_id} text={text_snippet!r}"
        )
        return

    flags = flagged_aspects(result, settings.ai_spam_alert_threshold, AI_SPAM_LABELS)
    flags_display = ", ".join(f"{label} ({score:.0%})" for label, score in flags)
    logger.info(
        f"ai_spam_monitor: group={group_id} user_id={user.id} "
        f"username={username_display} name={user.full_name!r} "
        f"message_id={message_id} labels={result.labels or [result.label]} "
        f"flags={flags_display or '-'} model={result.model} "
        f"text={text_snippet!r}"
    )

    if not flags:
        return

    group_config = _get_group_config(context, group_id)
    alert_chat_id = group_config.ai_spam_alert_chat_id if group_config else None
    if alert_chat_id is None:
        logger.warning(
            f"ai_spam_monitor: no alert chat configured for group={group_id}; "
            f"dropping alert user_id={user.id} message_id={message_id} flags={flags_display}"
        )
        return
    if _already_alerted(context, (group_id, message_id)):
        logger.info(
            f"ai_spam_monitor: alert already sent for group={group_id} "
            f"message_id={message_id}; skipping duplicate"
        )
        return

    profile_status = await _fetch_profile_status(context, user)
    alert_text = AI_SPAM_ALERT.format(
        group_id=group_id,
        user_mention=plain_mention(user),
        user_id=user.id,
        flags=flags_display,
        model=result.model or "classifier.dev",
        profile_status=profile_status,
        message_text=truncate_alert_text(message_text),
    )
    logger.info(
        f"ai_spam_monitor: sending alert to chat_id={alert_chat_id} "
        f"for group={group_id} user_id={user.id} message_id={message_id} flags={flags_display}"
    )
    try:
        await context.bot.send_message(
            chat_id=alert_chat_id,
            text=alert_text,
            reply_markup=build_alert_keyboard(group_id, user.id, message_id),
        )
    except Exception:
        logger.error(
            f"ai_spam_monitor: failed to send alert to chat_id={alert_chat_id} "
            f"for user_id={user.id} message_id={message_id}",
            exc_info=True,
        )
    else:
        logger.info(
            f"ai_spam_monitor: alert sent to chat_id={alert_chat_id} "
            f"for group={group_id} message_id={message_id}"
        )


async def handle_ai_spam_monitor(
    update: Update, context: HandlerContext
) -> None:
    """Last-defense entry handler: spawn a background classification."""
    message = effective_message(update)
    user = effective_user(update)
    if message is None or user is None or user.is_bot:
        return
    classifiable = _classifiable_text(message)
    if len(classifiable.strip()) < AI_SPAM_MIN_LENGTH:
        return

    chat = effective_chat(update)
    if chat is None:
        return
    group_id = chat.id
    if is_user_admin_or_trusted(context, group_id, user.id):
        return
    if daily_budget_exhausted(get_settings().ai_spam_daily_budget):
        return
    if breaker_is_open(
        time.monotonic(), cooldown_seconds=get_settings().classifier_cooldown_seconds
    ):
        return

    # create_task keeps the update pipeline non-blocking and logs exceptions.
    context.create_task(
        _classify_and_alert(
            context,
            group_id=group_id,
            user=user,
            message_id=message.message_id,
            message_text=classifiable,
        ),
    )


async def handle_ai_spam_action(
    update: Update, context: HandlerContext
) -> None:
    """Admin pressed an action button on an AI spam alert."""
    query = update.callback_query
    if query is None or query.data is None or query.message is None:
        return

    _, action, group_id_raw, user_id_raw, message_id_raw = query.data.split(":")
    group_id = int(group_id_raw)
    user_id = int(user_id_raw)
    message_id = int(message_id_raw)

    admin = query.from_user
    if not is_user_admin_in_group(context, group_id, admin.id):
        await query.answer(AI_SPAM_CB_NOT_ADMIN, show_alert=True)
        return

    await query.answer()
    action_label = AI_SPAM_ACTION_LABELS.get(action, action)
    detail_parts: list[str] = []

    if action in (ACTION_DELETE, ACTION_DELETE_RESTRICT, ACTION_DELETE_BAN):
        try:
            await context.bot.delete_message(chat_id=group_id, message_id=message_id)
        except Exception:
            logger.info(
                f"ai_spam_monitor: message {message_id} in group {group_id} already gone",
                exc_info=True,
            )
            detail_parts.append(AI_SPAM_CB_MESSAGE_GONE)

    if action == ACTION_DELETE_RESTRICT:
        try:
            ok = await restrict_chat_member_with_retry(
                context.bot,
                chat_id=group_id,
                user_id=user_id,
                permissions=RESTRICTED_PERMISSIONS,
            )
            if not ok:
                detail_parts.append("pembatasan gagal")
        except Exception:
            logger.error(
                f"ai_spam_monitor: restrict failed for user_id={user_id}",
                exc_info=True,
            )
            detail_parts.append("pembatasan gagal")

    elif action == ACTION_DELETE_BAN:
        try:
            await context.bot.ban_chat_member(chat_id=group_id, user_id=user_id)
        except Exception:
            logger.error(
                f"ai_spam_monitor: ban failed for user_id={user_id}", exc_info=True
            )
            detail_parts.append("ban gagal")

    handled_text = AI_SPAM_ALERT_HANDLED.format(
        admin_mention=plain_mention(admin),
        action=action_label + (f" ({'; '.join(detail_parts)})" if detail_parts else ""),
    )
    try:
        await query.message.edit_text(
            (query.message.text or "") + handled_text, reply_markup=None
        )
    except Exception:
        logger.warning("ai_spam_monitor: failed to mark alert handled", exc_info=True)


def get_handlers() -> list[HandlerSpec]:
    """Return the message handler and callback handler for this module.

    The message spec runs at group=7 (last defense); the callback spec at
    group=0. The plugin layer wraps each callback with ``guard_plugin``
    using the spec's own ``plugin_name``.
    """
    return [
        HandlerSpec(
            plugin_name="ai_spam_monitor",
            group=7,
            update_kinds=("message", "edited_message"),
            check=AI_SPAM_FILTER,
            callback=handle_ai_spam_monitor,
            label="ai_spam_monitor",
        ),
        HandlerSpec(
            plugin_name="ai_spam_callback",
            group=0,
            update_kinds=("callback_query",),
            check=callback_data_pattern(AI_SPAM_CALLBACK_PATTERN),
            callback=handle_ai_spam_action,
            label="ai_spam_callback",
        ),
    ]
