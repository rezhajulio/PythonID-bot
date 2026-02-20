"""
Scheduler service for automated bot tasks.

This module manages periodic tasks like auto-restricting users who exceed
time thresholds for profile completion. Iterates per-group since each
group may have different threshold settings.
"""

import logging

from telegram.constants import ChatMemberStatus
from telegram.ext import ContextTypes


from bot.constants import (
    RESTRICTED_PERMISSIONS,
    RESTRICTION_MESSAGE_AFTER_TIME,
    format_threshold_display,
)
from bot.database.service import get_database
from bot.group_config import get_group_registry
from bot.services.bot_info import BotInfoCache
from bot.services.telegram_utils import get_user_mention, get_user_status

logger = logging.getLogger(__name__)


async def auto_restrict_expired_warnings(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Periodically check and restrict users who exceeded time threshold.

    Iterates per-group since each group may have different
    warning_time_threshold_minutes. Finds all active warnings past the
    configured threshold and applies restrictions (mutes) to those users.

    Args:
        context: Telegram job context for sending messages.
    """
    logger.info("Starting auto-restriction job")
    registry = get_group_registry()
    db = get_database()

    # Get bot username once for all DM links
    bot = context.bot
    bot_username = await BotInfoCache.get_username(bot)
    dm_link = f"https://t.me/{bot_username}"

    for group_config in registry.all_groups():
        # Get warnings that exceeded time threshold for this group
        expired_warnings = db.get_warnings_past_time_threshold_for_group(
            group_config.group_id, group_config.warning_time_threshold_timedelta
        )

        if not expired_warnings:
            logger.info(f"No expired warnings for group {group_config.group_id}")
            continue

        logger.info(f"Processing {len(expired_warnings)} expired warnings for group {group_config.group_id}")

        for warning in expired_warnings:
            try:
                logger.info(f"Checking status for user_id={warning.user_id}")
                # Check if user is kicked
                user_status = await get_user_status(bot, group_config.group_id, warning.user_id)

                # Skip if user is kicked (can't rejoin without admin re-invite)
                if user_status == ChatMemberStatus.BANNED:
                    db.delete_user_warnings(warning.user_id, warning.group_id)
                    logger.info(
                        f"Skipped auto-restriction for user {warning.user_id} - user kicked (group_id={group_config.group_id})"
                    )
                    continue

                logger.info(f"Applying restriction to user_id={warning.user_id}")
                # Apply restriction (even if user left, they'll be restricted when they rejoin)
                await bot.restrict_chat_member(
                    chat_id=group_config.group_id,
                    user_id=warning.user_id,
                    permissions=RESTRICTED_PERMISSIONS,
                )
                db.mark_user_restricted(warning.user_id, group_config.group_id)

                # Get user info for proper mention
                try:
                    user_member = await bot.get_chat_member(
                        chat_id=group_config.group_id,
                        user_id=warning.user_id,
                    )
                    user = user_member.user
                    user_mention = get_user_mention(user)
                except Exception:
                    # Fallback to user ID if we can't get user info
                    user_mention = f"User {warning.user_id}"

                # Send notification to warning topic
                threshold_display = format_threshold_display(
                    group_config.warning_time_threshold_minutes
                )
                restriction_message = RESTRICTION_MESSAGE_AFTER_TIME.format(
                    user_mention=user_mention,
                    threshold_display=threshold_display,
                    rules_link=group_config.rules_link,
                    dm_link=dm_link,
                )
                await bot.send_message(
                    chat_id=group_config.group_id,
                    message_thread_id=group_config.warning_topic_id,
                    text=restriction_message,
                    parse_mode="Markdown",
                )

                logger.info(
                    f"Auto-restricted user {warning.user_id} after {group_config.warning_time_threshold_minutes} minutes (group_id={group_config.group_id})"
                )
            except Exception as e:
                logger.error(
                    f"Error auto-restricting user {warning.user_id} in group {group_config.group_id}: {e}", exc_info=True
                )
