"""Guest bot message moderation for Telegram Guest Mode."""

import logging

from telegram import Message, Update, User
from telegram.error import TelegramError
from telegram.ext import ApplicationHandlerStop, ContextTypes, filters

from bot.constants import (
    GUEST_BOT_RESTRICTION,
    GUEST_BOT_WARNING,
    RESTRICTED_PERMISSIONS,
)
from bot.database.service import get_database
from bot.group_config import get_group_config_for_update
from bot.services.restriction_lock import restriction_lock
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
    return username.lower() in whitelist


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
    except TelegramError:
        logger.error("Failed to delete guest bot message", exc_info=True)

    if not isinstance(caller, User):
        raise ApplicationHandlerStop
    if is_user_admin_or_trusted(context, group_config.group_id, caller.id):
        raise ApplicationHandlerStop

    db = get_database()
    if db.is_user_restricted_by_bot(caller.id, group_config.group_id, warning_kind="guest_bot"):
        raise ApplicationHandlerStop

    record = db.get_or_create_user_warning(caller.id, group_config.group_id, warning_kind="guest_bot")
    user_mention = get_user_mention(caller)

    if record.message_count >= group_config.warning_threshold:
        should_stop = False
        final_count = record.message_count
        try:
            async with restriction_lock(group_config.group_id, caller.id):
                if db.is_user_restricted_by_bot(caller.id, group_config.group_id, warning_kind="guest_bot"):
                    should_stop = True
                else:
                    fresh = db.get_or_create_user_warning(caller.id, group_config.group_id, warning_kind="guest_bot")
                    if fresh.message_count != group_config.warning_threshold:
                        should_stop = True
                    else:
                        try:
                            await context.bot.restrict_chat_member(
                                chat_id=group_config.group_id,
                                user_id=caller.id,
                                permissions=RESTRICTED_PERMISSIONS,
                            )
                            db.mark_user_restricted(caller.id, group_config.group_id, warning_kind="guest_bot")
                            final_count = fresh.message_count
                        except TelegramError as e:
                            logger.error("Failed to restrict guest bot caller %s: %s", caller.id, e, exc_info=True)
                            should_stop = True
                            db.increment_message_count(caller.id, group_config.group_id, warning_kind="guest_bot")
        except TelegramError:
            logger.error("Failed to restrict guest bot caller %s (lock level)", caller.id, exc_info=True)
            should_stop = True
        else:
            if should_stop:
                raise ApplicationHandlerStop
            try:
                await context.bot.send_message(
                    chat_id=group_config.group_id,
                    message_thread_id=group_config.warning_topic_id,
                    text=GUEST_BOT_RESTRICTION.format(
                        user_mention=user_mention,
                        message_count=final_count,
                        rules_link=group_config.rules_link,
                    ),
                    parse_mode="Markdown",
                )
            except TelegramError:
                logger.error("Failed to send guest bot restriction notice for user %s", caller.id, exc_info=True)
    elif record.message_count == 1:
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
        except TelegramError:
            logger.error("Failed to send guest bot warning for user %s", caller.id, exc_info=True)
        db.increment_message_count(caller.id, group_config.group_id, warning_kind="guest_bot")
    else:
        db.increment_message_count(caller.id, group_config.group_id, warning_kind="guest_bot")

    raise ApplicationHandlerStop
