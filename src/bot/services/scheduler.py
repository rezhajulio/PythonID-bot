"""
Scheduler service for automated bot tasks.

This module manages periodic tasks like auto-restricting users who exceed
time thresholds for profile completion. Iterates per-group since each
group may have different threshold settings.
"""

import logging
import time

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
from bot.services.restriction_lock import restriction_lock
from bot.services.telegram_utils import (
    get_user_mention,
    get_user_status,
    restrict_chat_member_with_retry,
    send_message_with_retry,
)
from bot.services.user_checker import check_user_profile

logger = logging.getLogger(__name__)


async def auto_restrict_expired_warnings(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Periodically check and restrict users who exceeded time threshold.

    Iterates per-group since each group may have different
    warning_time_threshold_minutes. Finds all active warnings past the
    configured threshold and applies restrictions (mutes) to those users.

    Before restricting, rechecks the user's profile to avoid restricting
    users who have already fixed their profile since the last warning.

    Args:
        context: Telegram job context for sending messages.
    """
    logger.info("Starting auto-restriction job")
    registry = get_group_registry()
    db = get_database()

    bot = context.bot
    bot_username = await BotInfoCache.get_username(bot)

    for group_config in registry.all_groups():
        try:
            expired_warnings = db.get_warnings_past_time_threshold_for_group(
                group_config.group_id, group_config.warning_time_threshold_timedelta
            )
        except Exception as e:
            logger.error(
                f"Error querying expired warnings for group {group_config.group_id}: {e}",
                exc_info=True,
            )
            continue

        if not expired_warnings:
            logger.info(f"No expired warnings for group {group_config.group_id}")
            continue

        logger.info(f"Processing {len(expired_warnings)} expired warnings for group {group_config.group_id}")

        for warning in expired_warnings:
            try:
                logger.info(f"Checking status for user_id={warning.user_id}")
                user_status = await get_user_status(bot, group_config.group_id, warning.user_id)

                if user_status == ChatMemberStatus.BANNED:
                    db.delete_user_warnings(warning.user_id, warning.group_id)
                    logger.info(
                        f"Skipped auto-restriction for user {warning.user_id} - user kicked (group_id={group_config.group_id})"
                    )
                    continue

                # Recheck profile before restricting — user may have fixed it
                # since the last warning. Skip restriction if profile is now complete.
                # Also fetch user info for the mention here to avoid a second API call.
                user_mention = f"User {warning.user_id}"
                try:
                    user_member = await bot.get_chat_member(
                        chat_id=group_config.group_id,
                        user_id=warning.user_id,
                    )
                    user_mention = get_user_mention(user_member.user)

                    profile_result = await check_user_profile(bot, user_member.user)
                    if profile_result.is_complete:
                        db.delete_user_warnings(warning.user_id, warning.group_id)
                        logger.info(
                            f"Skipped auto-restriction for user {warning.user_id} "
                            f"- profile now complete (group_id={group_config.group_id})"
                        )
                        continue
                except Exception:
                    logger.warning(
                        f"Profile recheck failed for user {warning.user_id}, "
                        f"proceeding with restriction",
                        exc_info=True,
                    )

                logger.info(f"Applying restriction to user_id={warning.user_id}")
                async with restriction_lock(group_config.group_id, warning.user_id):
                    ok = await restrict_chat_member_with_retry(
                        bot,
                        chat_id=group_config.group_id,
                        user_id=warning.user_id,
                        permissions=RESTRICTED_PERMISSIONS,
                    )
                    if not ok:
                        logger.error(
                            f"Gave up restricting user {warning.user_id} after RetryAfter"
                        )
                        continue
                    db.mark_user_restricted(warning.user_id, warning.group_id)

                threshold_display = format_threshold_display(
                    group_config.warning_time_threshold_minutes
                )
                dm_link = f"https://t.me/{bot_username}?start=verify_{group_config.group_id}"
                restriction_message = RESTRICTION_MESSAGE_AFTER_TIME.format(
                    user_mention=user_mention,
                    threshold_display=threshold_display,
                    rules_link=group_config.rules_link,
                    dm_link=dm_link,
                )
                await send_message_with_retry(
                    bot,
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
    context.bot_data["last_auto_restrict"] = time.time()
