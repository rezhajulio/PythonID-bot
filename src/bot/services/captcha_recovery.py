"""
Captcha recovery service for the PythonID bot.

This module handles recovery of lost captcha timeout jobs on bot restart.
Since JobQueue is in-memory, pending verifications need to be recovered
from the database to prevent users from being stuck in restricted state.
"""

import logging
from datetime import UTC, datetime

from telegram import Bot
from telegram.ext import Application
from telegram.helpers import mention_markdown

from bot.config import get_settings
from bot.constants import CAPTCHA_TIMEOUT_MESSAGE
from bot.database.service import get_database
from bot.handlers.captcha import captcha_timeout_callback, get_captcha_job_name
from bot.services.bot_info import BotInfoCache

logger = logging.getLogger(__name__)


async def handle_captcha_expiration(
    bot: Bot,
    user_id: int,
    group_id: int,
    chat_id: int,
    message_id: int,
    user_full_name: str,
) -> None:
    """
    Handle captcha expiration for a user.

    Edits the challenge message to show timeout, removes from database.
    This is shared between live timeouts and recovery on restart.

    Args:
        bot: The bot instance.
        user_id: The user ID.
        group_id: The group ID.
        chat_id: The chat ID where the message was sent.
        message_id: The message ID of the captcha challenge.
        user_full_name: The user's full name.
    """
    db = get_database()
    pending = db.get_pending_captcha(user_id, group_id)
    if not pending:
        logger.debug(f"No pending captcha for user {user_id}, already verified")
        return

    db.remove_pending_captcha(user_id, group_id)

    # Create UserWarning to track this bot-applied restriction
    # Allows DM handler to unrestrict user later when profile is complete
    warning = db.get_or_create_user_warning(user_id, group_id)
    if not warning.is_restricted:
        db.mark_user_restricted(user_id, group_id)

    bot_username = await BotInfoCache.get_username(bot)
    dm_link = f"[hubungi robot](https://t.me/{bot_username})"
    user_mention = mention_markdown(user_id, user_full_name)

    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=CAPTCHA_TIMEOUT_MESSAGE.format(
                user_mention=user_mention,
                dm_link=dm_link,
            ),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Failed to edit captcha timeout message: {e}")

    logger.info(f"User {user_id} captcha timeout - kept restricted")


async def recover_pending_captchas(application: Application) -> None:
    """
    Recover pending captcha verifications on bot startup.

    Queries the database for all pending captcha records and:
    1. If timeout has already passed: immediately expire them
    2. If timeout hasn't passed yet: reschedule the timeout job

    This prevents users from being stuck in restricted state after bot restart.

    Args:
        application: The Application instance with bot and job_queue.
    """
    settings = get_settings()
    db = get_database()

    pending_records = db.get_all_pending_captchas()

    if not pending_records:
        logger.info("No pending captcha verifications to recover")
        return

    logger.info(f"Recovering {len(pending_records)} pending captcha verification(s)")

    now = datetime.now(UTC)

    for record in pending_records:
        try:
            # Make created_at timezone-aware (SQLite stores without timezone)
            created_at_utc = record.created_at.replace(tzinfo=UTC)
            elapsed_seconds = (now - created_at_utc).total_seconds()
            remaining_seconds = settings.captcha_timeout_seconds - elapsed_seconds

            if remaining_seconds <= 0:
                # Timeout has already passed, expire immediately
                logger.info(
                    f"Expiring captcha for user {record.user_id} "
                    f"(timeout passed {abs(remaining_seconds):.0f}s ago)"
                )

                await handle_captcha_expiration(
                    bot=application.bot,
                    user_id=record.user_id,
                    group_id=record.group_id,
                    chat_id=record.chat_id,
                    message_id=record.message_id,
                    user_full_name=record.user_full_name,
                )
            else:
                # Timeout hasn't passed yet, reschedule the job
                logger.info(
                    f"Rescheduling captcha timeout for user {record.user_id} "
                    f"(remaining: {remaining_seconds:.0f}s)"
                )

                job_name = get_captcha_job_name(record.group_id, record.user_id)

                application.job_queue.run_once(
                    captcha_timeout_callback,
                    when=remaining_seconds,
                    name=job_name,
                    data={
                        "user_id": record.user_id,
                        "group_id": record.group_id,
                        "chat_id": record.chat_id,
                        "message_id": record.message_id,
                        "user_full_name": record.user_full_name,
                    },
                )
        except Exception as e:
            logger.error(
                f"Failed to recover captcha for user {record.user_id}: {e}",
                exc_info=True,
            )
            continue

    logger.info("Captcha recovery complete")
