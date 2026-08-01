"""
Admin /warn command handler for the PythonID bot.

Lets an admin make the bot send a generic warning to a group member.
Two invocation modes:

1. Reply mode: admin replies to the member's message with ``/warn [reason]``
2. ID mode:    admin sends ``/warn USER_ID [reason]`` in the group

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


async def handle_warn_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /warn command in a monitored group.

    Admin replies to a member's message with ``/warn [reason]``, or
    provides a user ID: ``/warn USER_ID [reason]``.

    Sends a warning message mentioning the target member. The admin's
    command message is deleted before any network lookups to protect
    their identity.
    """
    if not update.message or not update.message.from_user:
        return

    admin = update.message.from_user
    message = update.message

    group_config = get_group_config_for_update(update)
    if group_config is None:
        return

    # Per-group admin check (not global union)
    if not is_user_admin_in_group(context, group_config.group_id, admin.id):
        return

    # Delete command message early to protect admin identity on all paths
    await _delete_command_message(update)

    # Resolve target user and reason
    reply_user = (
        message.reply_to_message.from_user
        if message.reply_to_message
        else None
    )

    if reply_user is not None:
        target_user = reply_user
        reason = " ".join(context.args) if context.args else ""
    elif context.args:
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            try:
                await message.reply_text(WARN_COMMAND_USAGE, do_quote=False)
            except Exception:
                logger.error("Failed to send usage message", exc_info=True)
            return
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
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""
    else:
        try:
            await message.reply_text(WARN_COMMAND_USAGE, do_quote=False)
        except Exception:
            logger.error("Failed to send usage message", exc_info=True)
        return

    if target_user.is_bot:
        return

    if target_user.id == admin.id:
        return

    user_mention = get_user_mention_by_id(
        target_user.id, target_user.full_name, getattr(target_user, "username", None)
    )

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
            f"Failed to send warning to group {group_config.group_id} for user {target_user.id}",
            exc_info=True,
        )
        return

    logger.info(
        f"Admin {admin.id} warned user {target_user.id} in group {group_config.group_id}"
    )
