"""
Admin /warn command handler for the PythonID bot.

Lets an admin make the bot send a generic warning to a group member.
Three invocation modes:

1. Reply mode:   admin replies to the member's message with ``/warn [reason]``
2. ID mode:      admin sends ``/warn USER_ID [reason]`` in the group
3. Username mode: admin sends ``/warn @username [reason]`` in the group

In forum-topic groups, Telegram auto-sets ``reply_to_message`` to the topic
anchor message.  To avoid mistaking the anchor for a real reply, we check
``forum_topic_created`` and skip it.

The warning is sent to the moderation topic when ``moderation_topic_id`` is
configured (per-group), otherwise to the main group chat.

The admin's command message is deleted early to protect their identity.
Non-admin callers are silently ignored.
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from bot.constants import (
    WARN_COMMAND_NOT_FOUND,
    WARN_COMMAND_NO_REASON,
    WARN_COMMAND_NOT_MEMBER,
    WARN_COMMAND_USAGE,
    WARN_COMMAND_WITH_REASON,
)
from bot.group_config import get_group_config_for_update
from bot.services.telegram_utils import get_user_mention_by_id, is_user_admin_in_group

logger = logging.getLogger(__name__)


async def _delete_command_message(update: Update) -> None:
    """Best-effort delete the admin's /warn command message."""
    try:
        await update.message.delete()  # type: ignore[union-attr]
    except Exception:
        logger.warning(
            "Failed to delete admin /warn command message",
            exc_info=True,
        )


def _is_real_reply(message: object) -> bool:
    """Check if reply_to_message is a real user reply, not a forum topic anchor."""
    reply = getattr(message, "reply_to_message", None)
    if reply is None:
        return False
    if getattr(reply, "forum_topic_created", None) is not None:
        return False
    if getattr(reply, "from_user", None) is None:
        return False
    return True


async def handle_warn_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /warn command in a monitored group.

    Resolution priority:
    1. ``args[0]`` is numeric   → ID mode (get_chat_member, membership check)
    2. ``args[0]`` starts with @ → username mode (mention only, no membership check)
    3. Real reply_to_message     → reply mode
    4. None of the above         → usage error
    """
    if not update.message or not update.message.from_user:
        return

    admin = update.message.from_user
    message = update.message

    group_config = get_group_config_for_update(update)
    if group_config is None:
        return

    if not is_user_admin_in_group(context, group_config.group_id, admin.id):
        return

    await _delete_command_message(update)

    args = context.args or []
    has_real_reply = _is_real_reply(message)

    # --- Determine target and reason ---
    target_user: object | None = None
    target_username: str | None = None
    reason = ""

    if args and args[0].lstrip("-").isdigit():
        # --- ID mode ---
        target_user_id = int(args[0])
        reason = " ".join(args[1:]) if len(args) > 1 else ""
        try:
            member = await context.bot.get_chat_member(
                chat_id=group_config.group_id,
                user_id=target_user_id,
            )
        except Exception:
            logger.error(
                f"Failed to fetch member {target_user_id} for /warn",
                exc_info=True,
            )
            try:
                await message.reply_text(
                    WARN_COMMAND_NOT_FOUND.format(user_id=target_user_id),
                    do_quote=False,
                )
            except Exception:
                logger.error("Failed to send error reply", exc_info=True)
            return
        if member.status in ("left", "kicked"):
            try:
                await message.reply_text(
                    WARN_COMMAND_NOT_MEMBER.format(user_id=target_user_id),
                    do_quote=False,
                )
            except Exception:
                logger.error("Failed to send not-member reply", exc_info=True)
            return
        target_user = member.user
        if target_user is None:
            return
    elif args and args[0].startswith("@"):
        # --- Username mode ---
        target_username = args[0].lstrip("@")
        reason = " ".join(args[1:]) if len(args) > 1 else ""
    elif has_real_reply:
        # --- Reply mode ---
        target_user = message.reply_to_message.from_user  # type: ignore[union-attr]
        reason = " ".join(args) if args else ""
    else:
        try:
            await message.reply_text(WARN_COMMAND_USAGE, do_quote=False)
        except Exception:
            logger.error("Failed to send usage message", exc_info=True)
        return

    # --- Build warning text ---
    if target_user is not None:
        if target_user.is_bot:
            return
        if target_user.id == admin.id:
            return
        user_mention = get_user_mention_by_id(
            target_user.id,
            target_user.full_name,
            getattr(target_user, "username", None),
        )
    elif target_username is not None:
        user_mention = f"@{escape_markdown(target_username, version=1)}"
    else:
        return

    if reason:
        warn_text = WARN_COMMAND_WITH_REASON.format(
            user_mention=user_mention,
            reason=escape_markdown(reason, version=1),
        )
    else:
        warn_text = WARN_COMMAND_NO_REASON.format(user_mention=user_mention)

    try:
        send_kwargs: dict[str, object] = {
            "chat_id": group_config.group_id,
            "text": warn_text,
            "parse_mode": "Markdown",
        }
        if group_config.moderation_topic_id is not None:
            send_kwargs["message_thread_id"] = group_config.moderation_topic_id
        await context.bot.send_message(**send_kwargs)
    except Exception:
        logger.error(
            f"Failed to send warning to group {group_config.group_id}",
            exc_info=True,
        )
        return

    logger.info(
        f"Admin {admin.id} warned "
        f"{'@' + target_username if target_username else target_user.id} "  # type: ignore[union-attr]
        f"in group {group_config.group_id}"
    )
