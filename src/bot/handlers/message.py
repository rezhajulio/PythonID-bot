"""
Group message handler for the PythonID bot.

This module handles messages in the monitored group, checking if users
have complete profiles (photo + username). It implements two modes:
1. Warning mode (default): Just sends warnings to the warning topic
2. Restriction mode: Progressive enforcement with muting after threshold
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes
from telegram.helpers import mention_markdown

from bot.config import get_settings
from bot.constants import (
    MISSING_ITEMS_SEPARATOR,
    RESTRICTED_PERMISSIONS,
    RESTRICTION_MESSAGE_AFTER_MESSAGES,
    WARNING_MESSAGE_NO_RESTRICTION,
    WARNING_MESSAGE_WITH_THRESHOLD,
    format_threshold_display,
)
from bot.database.service import get_database
from bot.services.bot_info import BotInfoCache
from bot.services.user_checker import check_user_profile

logger = logging.getLogger(__name__)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle incoming group messages and check user profiles.

    This handler:
    1. Filters to only process messages in the configured group
    2. Ignores bot messages
    3. Checks if user has profile photo and username
    4. If incomplete, either warns or applies progressive restriction

    Args:
        update: Telegram update containing the message.
        context: Bot context with helper methods.
    """
    # Skip if no message or sender
    if not update.message or not update.message.from_user:
        return

    settings = get_settings()

    # Only process messages from the configured group
    if update.effective_chat and update.effective_chat.id != settings.group_id:
        return

    user = update.message.from_user

    # Ignore messages from bots
    if user.is_bot:
        return

    # Check if user has complete profile (photo + username)
    result = await check_user_profile(context.bot, user)

    # User has complete profile, nothing to do
    if result.is_complete:
        return

    # Build warning message components
    missing = result.get_missing_items()
    missing_text = MISSING_ITEMS_SEPARATOR.join(missing)
    user_mention = (
        f"@{user.username}"
        if user.username
        else mention_markdown(user.id, user.full_name, version=2)
    )

    # Warning mode: just send warning, don't restrict
    if not settings.restrict_failed_users:
        threshold_display = format_threshold_display(
            settings.warning_time_threshold_minutes
        )
        warning_message = WARNING_MESSAGE_NO_RESTRICTION.format(
            user_mention=user_mention,
            missing_text=missing_text,
            threshold_display=threshold_display,
            rules_link=settings.rules_link,
        )
        await context.bot.send_message(
            chat_id=settings.group_id,
            message_thread_id=settings.warning_topic_id,
            text=warning_message,
            parse_mode="Markdown",
        )
        logger.info(
            f"Warned user {user.id} ({user.full_name}) for missing: {missing_text} (group_id={settings.group_id})"
        )
        return

    # Progressive restriction mode: track messages and restrict at threshold
    db = get_database()
    record = db.get_or_create_user_warning(user.id, settings.group_id)

    # First message: send warning with threshold info
    if record.message_count == 1:
        threshold_display = format_threshold_display(
            settings.warning_time_threshold_minutes
        )
        warning_message = WARNING_MESSAGE_WITH_THRESHOLD.format(
            user_mention=user_mention,
            missing_text=missing_text,
            warning_threshold=settings.warning_threshold,
            threshold_display=threshold_display,
            rules_link=settings.rules_link,
        )
        await context.bot.send_message(
            chat_id=settings.group_id,
            message_thread_id=settings.warning_topic_id,
            text=warning_message,
            parse_mode="Markdown",
        )
        logger.info(
            f"First warning for user {user.id} ({user.full_name}) for missing: {missing_text} (group_id={settings.group_id})"
        )

    # Threshold reached: restrict user
    if record.message_count >= settings.warning_threshold:
        # Apply restriction (mute user)
        await context.bot.restrict_chat_member(
            chat_id=settings.group_id,
            user_id=user.id,
            permissions=RESTRICTED_PERMISSIONS,
        )
        db.mark_user_restricted(user.id, settings.group_id)

        # Get bot username for DM link (cached to avoid repeated API calls)
        bot_username = await BotInfoCache.get_username(context.bot)
        dm_link = f"https://t.me/{bot_username}"

        # Send restriction notice with DM link for appeal
        restriction_message = RESTRICTION_MESSAGE_AFTER_MESSAGES.format(
            user_mention=user_mention,
            message_count=record.message_count,
            missing_text=missing_text,
            rules_link=settings.rules_link,
            dm_link=dm_link,
        )
        await context.bot.send_message(
            chat_id=settings.group_id,
            message_thread_id=settings.warning_topic_id,
            text=restriction_message,
            parse_mode="Markdown",
        )
        logger.info(
            f"Restricted user {user.id} ({user.full_name}) after {record.message_count} messages (group_id={settings.group_id})"
        )
    else:
        # Not at threshold yet: silently increment count (no spam)
        db.increment_message_count(user.id, settings.group_id)
        logger.debug(
            f"Silent increment for user {user.id} ({user.full_name}), "
            f"count: {record.message_count + 1}"
        )
