"""
AI-based spam monitoring via classifier.dev (monitor-only).

Messages that survive every enforcement handler reach this handler last
(handler_group 7). Text is classified in a background task so the update
pipeline is never blocked by the network call. High-confidence results
are reported to the configured admin chat (``ai_spam_alert_chat_id``)
with inline buttons so a human admin can delete, delete+restrict,
delete+ban, or dismiss. This handler never deletes, restricts, or warns
on its own and raises no ``ApplicationHandlerStop``.

Profile metadata (photo/username) is fetched locally for the alert only;
it is never sent to the classification API.
"""

import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, User
from telegram.ext import CallbackQueryHandler, ContextTypes, MessageHandler, filters

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
    RESTRICTED_PERMISSIONS,
)
from bot.group_config import get_group_registry
from bot.services.classifier_client import (
    DEFAULT_DAILY_BUDGET,
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

AI_SPAM_FILTER = filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND
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
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(AI_SPAM_BUTTON_DELETE, callback_data=f"aispam:{ACTION_DELETE}{suffix}"),
            InlineKeyboardButton(AI_SPAM_BUTTON_DISMISS, callback_data=f"aispam:{ACTION_DISMISS}{suffix}"),
        ],
        [
            InlineKeyboardButton(AI_SPAM_BUTTON_DELETE_RESTRICT, callback_data=f"aispam:{ACTION_DELETE_RESTRICT}{suffix}"),
            InlineKeyboardButton(AI_SPAM_BUTTON_DELETE_BAN, callback_data=f"aispam:{ACTION_DELETE_BAN}{suffix}"),
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


def _already_alerted(context: ContextTypes.DEFAULT_TYPE, key: tuple[int, int]) -> bool:
    alerts: dict[tuple[int, int], int] = context.bot_data.setdefault(ALERTS_KEY, {})
    if len(alerts) >= ALERTS_MAX_SIZE:
        for oldest in list(alerts)[: ALERTS_MAX_SIZE // 2]:
            del alerts[oldest]
    if key in alerts:
        return True
    alerts[key] = 0
    return False


def _get_group_config(context: ContextTypes.DEFAULT_TYPE, group_id: int):
    try:
        return get_group_registry().get(group_id)
    except RuntimeError:
        logger.error("Group registry not initialized; skipping AI spam alert")
        return None


async def _fetch_profile_status(
    context: ContextTypes.DEFAULT_TYPE, user: User
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


async def _classify_and_alert(
    context: ContextTypes.DEFAULT_TYPE,
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
    )
    if result is None:
        logger.info(
            f"ai_spam_monitor: classification failed for user_id={user.id} "
            f"in group={group_id}"
        )
        return

    confidence_display = (
        f"{result.confidence:.0%}" if result.confidence is not None else "n/a"
    )
    logger.info(
        f"ai_spam_monitor: group={group_id} user_id={user.id} "
        f"label={result.label} confidence={confidence_display} "
        f"model={result.model} message_id={message_id}"
    )

    if result.label != "spam":
        return
    if result.confidence is None or result.confidence < settings.ai_spam_alert_threshold:
        return

    group_config = _get_group_config(context, group_id)
    alert_chat_id = group_config.ai_spam_alert_chat_id if group_config else None
    if alert_chat_id is None:
        return
    if _already_alerted(context, (group_id, message_id)):
        return

    profile_status = await _fetch_profile_status(context, user)
    alert_text = AI_SPAM_ALERT.format(
        group_id=group_id,
        user_mention=plain_mention(user),
        user_id=user.id,
        confidence=confidence_display,
        model=result.model or "classifier.dev",
        profile_status=profile_status,
        message_text=truncate_alert_text(message_text),
    )
    try:
        await context.bot.send_message(
            chat_id=alert_chat_id,
            text=alert_text,
            reply_markup=build_alert_keyboard(group_id, user.id, message_id),
        )
    except Exception:
        logger.error(
            f"ai_spam_monitor: failed to send alert for user_id={user.id}",
            exc_info=True,
        )


async def handle_ai_spam_monitor(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Last-defense entry handler: spawn a background classification."""
    message = update.effective_message
    user = update.effective_user
    if message is None or message.text is None or user is None or user.is_bot:
        return
    if len(message.text.strip()) < AI_SPAM_MIN_LENGTH:
        return

    group_id = update.effective_chat.id
    if is_user_admin_or_trusted(context, group_id, user.id):
        return
    if daily_budget_exhausted(get_settings().ai_spam_daily_budget):
        return
    if breaker_is_open(
        time.monotonic(), cooldown_seconds=get_settings().classifier_cooldown_seconds
    ):
        return

    # Application.create_task keeps a strong reference and logs exceptions.
    context.application.create_task(
        _classify_and_alert(
            context,
            group_id=group_id,
            user=user,
            message_id=message.message_id,
            message_text=message.text,
        ),
        update=update,
    )


async def handle_ai_spam_action(
    update: Update, context: ContextTypes.DEFAULT_TYPE
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
        await query.edit_message_text(
            (query.message.text or "") + handled_text, reply_markup=None
        )
    except Exception:
        logger.warning("ai_spam_monitor: failed to mark alert handled", exc_info=True)


def get_handlers() -> list[MessageHandler | CallbackQueryHandler]:
    """Return the message handler and callback handler for this module."""
    return [
        MessageHandler(AI_SPAM_FILTER, handle_ai_spam_monitor),
        CallbackQueryHandler(handle_ai_spam_action, pattern=AI_SPAM_CALLBACK_PATTERN),
    ]
