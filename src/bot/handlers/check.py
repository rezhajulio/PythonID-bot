"""
Admin check handler for the PythonID bot.

This module handles admin commands to manually check user profiles:
1. /check <user_id> - Check a user's profile status
2. Forwarded message - Check profile and show action buttons
3. Warn button callback - Send warning to user in group
"""

import logging

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TimedOut
from telegram.ext import ContextTypes

from bot.config import get_settings
from bot.constants import (
    ADMIN_CHECK_ACTION_COMPLETE,
    ADMIN_CHECK_ACTION_INCOMPLETE,
    ADMIN_CHECK_PROMPT,
    ADMIN_WARN_SENT_MESSAGE,
    ADMIN_WARN_USER_MESSAGE,
    MISSING_ITEMS_SEPARATOR,
)
from bot.database.service import get_database
from bot.services.telegram_utils import (
    extract_forwarded_user,
    get_user_mention,
    get_user_mention_by_id,
)
from bot.services.user_checker import check_user_profile

logger = logging.getLogger(__name__)


async def _build_check_response(
    bot: Bot, user_id: int, user_name: str
) -> tuple[str, InlineKeyboardMarkup | None]:
    """
    Build the check response message and keyboard.
    
    Args:
        bot: Telegram bot instance.
        user_id: ID of the user to check.
        user_name: Display name of the user.
        
    Returns:
        Tuple of (message text, optional keyboard markup).
    """
    try:
        chat = await bot.get_chat(user_id)
        result = await check_user_profile(bot, chat)  # type: ignore
    except Exception as e:
        logger.error(f"Failed to check profile for user {user_id}: {e}")
        raise

    user_mention = get_user_mention_by_id(user_id, user_name)
    photo_status = "✅" if result.has_profile_photo else "❌"
    username_status = "✅" if result.has_username else "❌"
    
    db = get_database()
    is_whitelisted = db.is_user_photo_whitelisted(user_id)
    
    if result.is_complete:
        action_prompt = ADMIN_CHECK_ACTION_COMPLETE
        if is_whitelisted:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Unverify User", callback_data=f"unverify:{user_id}")]
            ])
        else:
            keyboard = None
    else:
        action_prompt = ADMIN_CHECK_ACTION_INCOMPLETE
        # Store missing items in callback data (photo,username format)
        missing_code = ""
        if not result.has_profile_photo:
            missing_code += "p"
        if not result.has_username:
            missing_code += "u"
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚠️ Warn User", callback_data=f"warn:{user_id}:{missing_code}"),
                InlineKeyboardButton("✅ Verify User", callback_data=f"verify:{user_id}"),
            ]
        ])
    
    message = ADMIN_CHECK_PROMPT.format(
        user_mention=user_mention,
        user_id=user_id,
        photo_status=photo_status,
        username_status=username_status,
        action_prompt=action_prompt,
    )
    
    return message, keyboard


async def handle_check_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /check command to manually check a user's profile.
    
    Usage: /check USER_ID (e.g., /check 123456789)
    
    Only works in bot DMs for admins.
    """
    if not update.message or not update.message.from_user:
        return

    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_text(
            "❌ Perintah ini hanya bisa digunakan di chat pribadi dengan bot."
        )
        return

    admin_user_id = update.message.from_user.id
    admin_ids = context.bot_data.get("admin_ids", [])

    if admin_user_id not in admin_ids:
        await update.message.reply_text("❌ Kamu tidak memiliki izin untuk menggunakan perintah ini.")
        logger.warning(
            f"Non-admin user {admin_user_id} ({update.message.from_user.full_name}) "
            f"attempted to use /check command"
        )
        return

    if not context.args or len(context.args) == 0:
        await update.message.reply_text("❌ Penggunaan: /check USER_ID")
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ User ID harus berupa angka.")
        return

    try:
        # Get user info for display name
        chat = await context.bot.get_chat(target_user_id)
        user_name = chat.full_name or f"User {target_user_id}"
        
        message, keyboard = await _build_check_response(context.bot, target_user_id, user_name)
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode="Markdown")
        
        logger.info(
            f"Admin {admin_user_id} ({update.message.from_user.full_name}) "
            f"checked profile for user {target_user_id}"
        )
    except TimedOut:
        await update.message.reply_text("⏳ Request timeout. Silakan coba lagi.")
        logger.warning(f"Timeout checking user {target_user_id}")
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal memeriksa user: {e}")
        logger.error(f"Error checking user {target_user_id}: {e}", exc_info=True)


async def handle_check_forwarded_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle forwarded messages from admins to check user profile.
    
    When an admin forwards a user's message to the bot in DM, this handler
    checks the user's profile and shows action buttons.
    """
    if not update.message or not update.message.from_user:
        return

    admin_user_id = update.message.from_user.id
    admin_ids = context.bot_data.get("admin_ids", [])

    if admin_user_id not in admin_ids:
        await update.message.reply_text("❌ Kamu tidak memiliki izin untuk menggunakan fitur ini.")
        logger.warning(
            f"Non-admin user {admin_user_id} ({update.message.from_user.full_name}) "
            f"attempted to forward message for check"
        )
        return

    forwarded_info = extract_forwarded_user(update.message)
    if not forwarded_info:
        await update.message.reply_text(
            "❌ Tidak dapat mengekstrak informasi user dari pesan yang diteruskan.\n"
            "Pastikan user tidak menyembunyikan status forward di pengaturan privasi."
        )
        return

    user_id, user_name = forwarded_info

    try:
        message, keyboard = await _build_check_response(context.bot, user_id, user_name)
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode="Markdown")
        
        logger.info(
            f"Admin {admin_user_id} ({update.message.from_user.full_name}) "
            f"forwarded message from user {user_id} for profile check"
        )
    except TimedOut:
        await update.message.reply_text("⏳ Request timeout. Silakan coba lagi.")
        logger.warning(f"Timeout checking forwarded user {user_id}")
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal memeriksa user: {e}")
        logger.error(f"Error checking forwarded user {user_id}: {e}", exc_info=True)


async def handle_warn_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle callback query for warn button.
    
    Sends a warning message to the user in the group.
    """
    query = update.callback_query
    if not query or not query.from_user or not query.data:
        return

    await query.answer()

    admin_user_id = query.from_user.id
    admin_ids = context.bot_data.get("admin_ids", [])

    if admin_user_id not in admin_ids:
        await query.edit_message_text("❌ Kamu tidak memiliki izin untuk menggunakan perintah ini.")
        logger.warning(
            f"Non-admin user {admin_user_id} ({query.from_user.full_name}) "
            f"attempted to use warn callback"
        )
        return

    # Parse callback data: warn:<user_id>:<missing_code>
    try:
        parts = query.data.split(":")
        target_user_id = int(parts[1])
        missing_code = parts[2] if len(parts) > 2 else ""
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Data callback tidak valid.")
        logger.error(f"Invalid callback_data format: {query.data}")
        return

    # Build missing items text
    missing_items = []
    if "p" in missing_code:
        missing_items.append("foto profil publik")
    if "u" in missing_code:
        missing_items.append("username")
    missing_text = MISSING_ITEMS_SEPARATOR.join(missing_items) if missing_items else "profil"

    settings = get_settings()
    
    try:
        # Get user info for mention
        chat = await context.bot.get_chat(target_user_id)
        user_mention = get_user_mention(chat)
        
        # Send warning to group
        warn_message = ADMIN_WARN_USER_MESSAGE.format(
            user_mention=user_mention,
            missing_text=missing_text,
            rules_link=settings.rules_link,
        )
        await context.bot.send_message(
            chat_id=settings.group_id,
            message_thread_id=settings.warning_topic_id,
            text=warn_message,
            parse_mode="Markdown",
        )
        
        # Update the original message
        success_message = ADMIN_WARN_SENT_MESSAGE.format(user_mention=user_mention)
        await query.edit_message_text(success_message, parse_mode="Markdown")
        
        logger.info(
            f"Admin {admin_user_id} ({query.from_user.full_name}) "
            f"sent warning to user {target_user_id} in group"
        )
    except TimedOut:
        await query.edit_message_text("⏳ Request timeout. Silakan coba lagi.")
        logger.warning(f"Timeout sending warning to user {target_user_id}")
    except Exception as e:
        await query.edit_message_text(f"❌ Gagal mengirim peringatan: {e}")
        logger.error(f"Error sending warning to user {target_user_id}: {e}", exc_info=True)
