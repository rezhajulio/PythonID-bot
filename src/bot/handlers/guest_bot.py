"""Guest bot message moderation for Telegram Guest Mode."""

import logging

from telegram import Message, Update, User
from telegram.ext import ApplicationHandlerStop, ContextTypes, filters

from bot.constants import (
    GUEST_BOT_RESTRICTION,
    GUEST_BOT_WARNING,
    RESTRICTED_PERMISSIONS,
)
from bot.database.service import get_database
from bot.group_config import get_group_config_for_update
from bot.services.telegram_utils import get_user_mention, is_user_admin_or_trusted

logger = logging.getLogger(__name__)


class GuestBotFilter(filters.MessageFilter):
    """Message filter matching only Telegram Guest Mode messages."""

    def filter(self, message: Message) -> bool:
        return (
            message.guest_bot_caller_user is not None
            or message.guest_bot_caller_chat is not None
        )


def is_guest_bot_message(message: Message) -> bool:
    """Check if a message was posted by a guest bot."""
    return message.guest_bot_caller_user is not None or message.guest_bot_caller_chat is not None


def is_guest_bot_whitelisted(message: Message, whitelist: list[str]) -> bool:
    """Check if the guest bot that posted this message is whitelisted."""
    username = message.from_user.username if message.from_user else None
    if not username:
        return False
    normalized_whitelist = {entry.strip().removeprefix("@").lower() for entry in whitelist}
    return username.lower() in normalized_whitelist


async def handle_guest_bot_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete unapproved guest bot messages and progressively restrict their caller."""
    message = update.message
    if message is None:
        return

    group_config = get_group_config_for_update(update)
    if group_config is None or not is_guest_bot_message(message):
        return
    if is_guest_bot_whitelisted(message, group_config.guest_bot_whitelist):
        return

    caller = message.guest_bot_caller_user or message.guest_bot_caller_chat
    try:
        await message.delete()
    except Exception:
        logger.error("Failed to delete guest bot message", exc_info=True)

    if caller is None or not isinstance(caller, User):
        raise ApplicationHandlerStop
    if is_user_admin_or_trusted(context, group_config.group_id, caller.id):
        raise ApplicationHandlerStop

    db = get_database()
    if db.is_user_restricted_by_bot(caller.id, group_config.group_id, warning_kind="guest_bot"):
        raise ApplicationHandlerStop

    record = db.get_or_create_user_warning(caller.id, group_config.group_id, warning_kind="guest_bot")
    user_mention = get_user_mention(caller)

    if record.message_count == 1:
        try:
            await context.bot.send_message(
                chat_id=group_config.group_id,
                message_thread_id=group_config.warning_topic_id,
                text=GUEST_BOT_WARNING.format(
                    user_mention=user_mention,
                    warning_threshold=group_config.warning_threshold,
                    rules_link=group_config.rules_link,
                ),
                parse_mode="Markdown",
            )
        except Exception:
            logger.error("Failed to send guest bot warning for user %s", caller.id, exc_info=True)

    if record.message_count >= group_config.warning_threshold:
        try:
            await context.bot.restrict_chat_member(
                chat_id=group_config.group_id,
                user_id=caller.id,
                permissions=RESTRICTED_PERMISSIONS,
            )
            db.mark_user_restricted(caller.id, group_config.group_id, warning_kind="guest_bot")
            await context.bot.send_message(
                chat_id=group_config.group_id,
                message_thread_id=group_config.warning_topic_id,
                text=GUEST_BOT_RESTRICTION.format(
                    user_mention=user_mention,
                    message_count=record.message_count,
                    rules_link=group_config.rules_link,
                ),
                parse_mode="Markdown",
            )
        except Exception:
            logger.error("Failed to restrict guest bot caller %s", caller.id, exc_info=True)
    else:
        db.increment_message_count(caller.id, group_config.group_id, warning_kind="guest_bot")

    raise ApplicationHandlerStop
