"""
DM (Direct Message) handler for the PythonID bot.

This module handles private messages to the bot, primarily for the
unrestriction flow. When a restricted user DMs the bot:
1. Check if user is in any monitored group
2. Check if user has an active pending captcha (redirect to group)
3. Check if user's profile is complete
4. If profile-restricted by bot and profile complete, unrestrict them
   across all monitored groups where they are restricted
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
    DM_UNRESTRICTION_NOTIFICATION,
    DM_UNRESTRICTION_SUCCESS_MESSAGE,
    MISSING_ITEMS_SEPARATOR,
)
from bot.database.service import get_database
from bot.group_config import get_group_registry
from bot.services.telegram_utils import get_user_mention, get_user_status, unrestrict_user
from bot.services.user_checker import check_user_profile

logger = logging.getLogger(__name__)


async def handle_dm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle direct messages to the bot for unrestriction flow.

    This handler processes DMs (including /start) and:
    1. Checks if user is a member of any monitored group
    2. Checks if user has an active pending captcha (redirect to group)
    3. Checks if user's profile is complete (photo + username)
    4. If user was restricted by the bot and now has complete profile,
       removes the restriction in all groups where restricted

    Args:
        update: Telegram update containing the message.
        context: Bot context with helper methods.
    """
    # Skip if no message or sender
    if not update.message or not update.message.from_user:
        logger.info("Skipping DM handler - no message or sender")
        return

    # Only handle private chats
    if update.effective_chat and update.effective_chat.type != "private":
        logger.info(f"Skipping non-private chat type: {update.effective_chat.type}")
        return

    user = update.message.from_user
    settings = get_settings()
    registry = get_group_registry()
    db = get_database()

    logger.info(f"DM handler called for user_id={user.id} ({user.full_name})")

    # Check user's membership across all monitored groups
    member_groups = []
    for gc in registry.all_groups():
        logger.info(f"Checking user status in group_id={gc.group_id} for user_id={user.id}")
        user_status = await get_user_status(context.bot, gc.group_id, user.id)
        if user_status is not None and user_status not in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
            member_groups.append((gc, user_status))

    # User not in any monitored group
    if not member_groups:
        await update.message.reply_text(DM_NOT_IN_GROUP_MESSAGE)
        logger.info(f"DM from user {user.id} ({user.full_name}) - not in any monitored group")
        return

    # Check if user has an active pending captcha in any group
    for gc, _ in member_groups:
        logger.info(f"Checking for pending captcha for user_id={user.id} in group_id={gc.group_id}")
        pending_captcha = db.get_pending_captcha(user.id, gc.group_id)
        if pending_captcha:
            await update.message.reply_text(CAPTCHA_PENDING_DM_MESSAGE)
            logger.info(
                f"DM from user {user.id} ({user.full_name}) - has pending captcha (group_id={gc.group_id})"
            )
            return

    # Check if user's profile is complete
    logger.info(f"Checking user profile completeness for user_id={user.id} ({user.full_name})")
    result = await check_user_profile(context.bot, user)

    # Profile still incomplete - tell them what's missing
    if not result.is_complete:
        missing = result.get_missing_items()
        missing_text = MISSING_ITEMS_SEPARATOR.join(missing)
        reply_message = DM_INCOMPLETE_PROFILE_MESSAGE.format(
            missing_text=missing_text,
            rules_link=settings.rules_link,
        )
        await update.message.reply_text(reply_message, parse_mode="Markdown")
        logger.info(
            f"DM from user {user.id} ({user.full_name}) - missing: {missing_text}"
        )
        return

    # Find all groups where user is restricted by bot
    restricted_groups = []
    for gc, user_status in member_groups:
        logger.info(f"Checking bot restriction status for user_id={user.id} in group_id={gc.group_id}")
        if db.is_user_restricted_by_bot(user.id, gc.group_id):
            restricted_groups.append((gc, user_status))

    # User not restricted by bot in any group
    if not restricted_groups:
        await update.message.reply_text(DM_NO_RESTRICTION_MESSAGE)
        logger.info(
            f"DM from user {user.id} ({user.full_name}) - no bot restriction in any group"
        )
        return

    # Unrestrict user from all groups where restricted by bot
    unrestricted_any = False
    all_already_unrestricted = True

    for gc, user_status in restricted_groups:
        # User was restricted by bot but is no longer restricted on Telegram
        # (e.g., admin already unrestricted them) - just clear our record
        if user_status != ChatMemberStatus.RESTRICTED:
            db.mark_user_unrestricted(user.id, gc.group_id)
            logger.info(
                f"User {user.id} ({user.full_name}) already unrestricted in group {gc.group_id} - clearing record"
            )
            continue

        all_already_unrestricted = False

        # Remove restriction
        logger.info(f"Unrestricting user_id={user.id} ({user.full_name}) in group_id={gc.group_id}")
        try:
            await unrestrict_user(context.bot, gc.group_id, user.id)
            db.mark_user_unrestricted(user.id, gc.group_id)
            unrestricted_any = True

            # Send notification to warning topic
            user_mention = get_user_mention(user)
            notification_message = DM_UNRESTRICTION_NOTIFICATION.format(
                user_mention=user_mention
            )
            await context.bot.send_message(
                chat_id=gc.group_id,
                message_thread_id=gc.warning_topic_id,
                text=notification_message,
                parse_mode="Markdown",
            )
            logger.info(
                f"Unrestricted user {user.id} ({user.full_name}) via DM (group_id={gc.group_id})"
            )
        except Exception:
            logger.error(
                f"Failed to unrestrict user {user.id} ({user.full_name}) via DM (group_id={gc.group_id})",
                exc_info=True,
            )

    if unrestricted_any:
        await update.message.reply_text(DM_UNRESTRICTION_SUCCESS_MESSAGE)
    elif all_already_unrestricted:
        await update.message.reply_text(DM_ALREADY_UNRESTRICTED_MESSAGE)
    else:
        # All unrestriction attempts failed
        raise RuntimeError(
            f"Failed to unrestrict user {user.id} in any group"
        )
