"""
DM (Direct Message) handler for the PythonID bot.

This module handles private messages to the bot, primarily for the
unrestriction flow. When a restricted user DMs the bot:
1. Check if user is in the group
2. Check if user has an active pending captcha (redirect to group)
3. Check if user's profile is complete
4. If profile-restricted by bot and profile complete, unrestrict them
"""

import logging

from telegram import Update
from telegram.constants import ChatMemberStatus
from telegram.ext import ContextTypes

from bot.config import get_settings
from bot.constants import (
    CAPTCHA_PENDING_DM_MESSAGE,
    DM_ALREADY_UNRESTRICTED_MESSAGE,
    DM_INCOMPLETE_PROFILE_MESSAGE,
    DM_NOT_IN_GROUP_MESSAGE,
    DM_NO_RESTRICTION_MESSAGE,
    DM_UNRESTRICTION_SUCCESS_MESSAGE,
)
from bot.database.service import get_database
from bot.services.telegram_utils import get_user_status, unrestrict_user
from bot.services.user_checker import check_user_profile

logger = logging.getLogger(__name__)


async def handle_dm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle direct messages to the bot for unrestriction flow.

    This handler processes DMs (including /start) and:
    1. Checks if user is a member of the monitored group
    2. Checks if user has an active pending captcha (redirect to group)
    3. Checks if user's profile is complete (photo + username)
    4. If user was restricted by the bot and now has complete profile,
       removes the restriction using the group's default permissions

    Args:
        update: Telegram update containing the message.
        context: Bot context with helper methods.
    """
    # Skip if no message or sender
    if not update.message or not update.message.from_user:
        return

    # Only handle private chats
    if update.effective_chat and update.effective_chat.type != "private":
        return

    user = update.message.from_user
    settings = get_settings()

    # Check user's status in the group
    user_status = await get_user_status(context.bot, settings.group_id, user.id)

    # User not in group (or we can't check)
    if user_status is None or user_status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        await update.message.reply_text(DM_NOT_IN_GROUP_MESSAGE)
        logger.info(
            f"DM from user {user.id} ({user.full_name}) - not in group {settings.group_id}"
        )
        return

    db = get_database()

    # Check if user has an active pending captcha
    pending_captcha = db.get_pending_captcha(user.id, settings.group_id)
    if pending_captcha:
        await update.message.reply_text(CAPTCHA_PENDING_DM_MESSAGE)
        logger.info(
            f"DM from user {user.id} ({user.full_name}) - has pending captcha (group_id={settings.group_id})"
        )
        return

    # Check if user's profile is complete
    result = await check_user_profile(context.bot, user)

    # Profile still incomplete - tell them what's missing
    if not result.is_complete:
        missing = result.get_missing_items()
        missing_text = " dan ".join(missing)
        reply_message = DM_INCOMPLETE_PROFILE_MESSAGE.format(
            missing_text=missing_text,
            rules_link=settings.rules_link,
        )
        await update.message.reply_text(reply_message, parse_mode="Markdown")
        logger.info(
            f"DM from user {user.id} ({user.full_name}) - missing: {missing_text}"
        )
        return

    # Check if user was restricted by this bot (not by admin)
    if not db.is_user_restricted_by_bot(user.id, settings.group_id):
        await update.message.reply_text(DM_NO_RESTRICTION_MESSAGE)
        logger.info(
            f"DM from user {user.id} ({user.full_name}) - no bot restriction (group_id={settings.group_id})"
        )
        return

    # User was restricted by bot but is no longer restricted on Telegram
    # (e.g., admin already unrestricted them) - just clear our record
    if user_status != ChatMemberStatus.RESTRICTED:
        db.mark_user_unrestricted(user.id, settings.group_id)
        await update.message.reply_text(DM_ALREADY_UNRESTRICTED_MESSAGE)
        logger.info(
            f"User {user.id} ({user.full_name}) already unrestricted - clearing record (group_id={settings.group_id})"
        )
        return

    # Remove restriction
    await unrestrict_user(context.bot, settings.group_id, user.id)

    # Clear our database record so we don't try to unrestrict again
    db.mark_user_unrestricted(user.id, settings.group_id)

    await update.message.reply_text(DM_UNRESTRICTION_SUCCESS_MESSAGE)
    logger.info(
        f"Unrestricted user {user.id} ({user.full_name}) via DM (group_id={settings.group_id})"
    )
