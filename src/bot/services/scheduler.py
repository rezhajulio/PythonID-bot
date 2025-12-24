"""
Scheduler service for automated bot tasks.

This module manages periodic tasks like auto-restricting users who exceed
time thresholds for profile completion.
"""

import logging
from datetime import UTC, datetime

from telegram.constants import ChatMemberStatus
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes
from telegram.helpers import mention_markdown

from bot.config import get_settings
from bot.constants import (
    RESTRICTED_PERMISSIONS,
    RESTRICTION_MESSAGE_AFTER_TIME,
    format_threshold_display,
)
from bot.database.service import get_database
from bot.services.bot_info import BotInfoCache
from bot.services.telegram_utils import get_user_status

logger = logging.getLogger(__name__)


async def auto_restrict_expired_warnings(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Periodically check and restrict users who exceeded time threshold.

    Finds all active warnings past the configured hours threshold and
    applies restrictions (mutes) to those users.

    Args:
        context: Telegram job context for sending messages.
    """
    settings = get_settings()
    db = get_database()

    # Get warnings that exceeded time threshold
    expired_warnings = db.get_warnings_past_time_threshold(
        settings.warning_time_threshold_minutes
    )

    if not expired_warnings:
        logger.debug("No expired warnings to process")
        return

    logger.info(f"Processing {len(expired_warnings)} expired warnings")

    # Get bot username once for all DM links
    bot = context.bot
    bot_username = await BotInfoCache.get_username(bot)
    dm_link = f"https://t.me/{bot_username}"

    for warning in expired_warnings:
        try:
            # Check if user is kicked
            user_status = await get_user_status(bot, settings.group_id, warning.user_id)
            
            # Skip if user is kicked (can't rejoin without admin re-invite)
            if user_status == ChatMemberStatus.BANNED:
                db.mark_user_unrestricted(warning.user_id, settings.group_id)
                logger.info(
                    f"Skipped auto-restriction for user {warning.user_id} - user kicked (group_id={settings.group_id})"
                )
                continue
            
            # Apply restriction (even if user left, they'll be restricted when they rejoin)
            await bot.restrict_chat_member(
                chat_id=settings.group_id,
                user_id=warning.user_id,
                permissions=RESTRICTED_PERMISSIONS,
            )
            db.mark_user_restricted(warning.user_id, settings.group_id)

            # Get user info for proper mention
            try:
                user_member = await bot.get_chat_member(
                    chat_id=settings.group_id,
                    user_id=warning.user_id,
                )
                user = user_member.user
                user_mention = (
                    f"@{user.username}"
                    if user.username
                    else mention_markdown(user.id, user.full_name)
                )
            except Exception:
                # Fallback to user ID if we can't get user info
                user_mention = f"User {warning.user_id}"

            # Send notification to warning topic
            threshold_display = format_threshold_display(
                settings.warning_time_threshold_minutes
            )
            restriction_message = RESTRICTION_MESSAGE_AFTER_TIME.format(
                user_mention=user_mention,
                threshold_display=threshold_display,
                rules_link=settings.rules_link,
                dm_link=dm_link,
            )
            await bot.send_message(
                chat_id=settings.group_id,
                message_thread_id=settings.warning_topic_id,
                text=restriction_message,
                parse_mode="Markdown",
            )

            logger.info(
                f"Auto-restricted user {warning.user_id} after {settings.warning_time_threshold_minutes} minutes (group_id={settings.group_id})"
            )
        except Exception as e:
            logger.error(
                f"Error auto-restricting user {warning.user_id} in group {settings.group_id}: {e}", exc_info=True
            )
