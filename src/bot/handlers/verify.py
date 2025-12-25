"""
Verification command handler for the PythonID bot.

This module handles the /verify and /unverify commands which allow admins to
manage the photo verification whitelist for users whose profile pictures are
hidden due to Telegram privacy settings.
"""

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from bot.config import get_settings
from bot.database.service import get_database
from bot.services.telegram_utils import unrestrict_user

logger = logging.getLogger(__name__)


async def handle_verify_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /verify command to whitelist users for profile picture verification.

    Usage: /verify USER_ID (e.g., /verify 123456789)

    This command allows admins to manually verify users whose profile pictures
    are hidden due to Telegram privacy settings. Only works in bot DMs.

    Args:
        update: Telegram update containing the command.
        context: Bot context with helper methods.
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
            f"attempted to use /verify command"
        )
        return

    if context.args and len(context.args) > 0:
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ User ID harus berupa angka.")
            return
    else:
        await update.message.reply_text("❌ Penggunaan: /verify USER_ID")
        return

    db = get_database()

    try:
        db.add_photo_verification_whitelist(
            user_id=target_user_id,
            verified_by_admin_id=admin_user_id,
        )
        
        # Get settings for group_id
        settings = get_settings()

        # Unrestrict user if they are restricted
        try:
            await unrestrict_user(context.bot, settings.group_id, target_user_id)
            logger.info(f"Unrestricted user {target_user_id} during verification")
        except BadRequest as e:
            # User might not be restricted or not in group - that's okay
            logger.debug(f"Could not unrestrict user {target_user_id}: {e}")

        # Delete all warning records for this user
        deleted_count = db.delete_user_warnings(target_user_id, settings.group_id)
        if deleted_count > 0:
            logger.info(f"Deleted {deleted_count} warning record(s) for user {target_user_id}")
        
        await update.message.reply_text(
            f"✅ User dengan ID {target_user_id} telah diverifikasi:\n"
            f"• Ditambahkan ke whitelist foto profil\n"
            f"• Pembatasan dicabut (jika ada)\n"
            f"• Riwayat warning dihapus\n\n"
            f"User ini tidak akan dicek foto profil lagi."
        )
        logger.info(
            f"Admin {admin_user_id} ({update.message.from_user.full_name}) "
            f"whitelisted user {target_user_id} for photo verification"
        )
    except ValueError as e:
        await update.message.reply_text(f"ℹ️ User dengan ID {target_user_id} sudah ada di whitelist.")
        logger.info(
            f"Admin {admin_user_id} tried to whitelist {target_user_id} but already exists: {e}"
        )


async def handle_unverify_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /unverify command to remove users from photo verification whitelist.

    Usage: /unverify USER_ID (e.g., /unverify 123456789)

    This command allows admins to remove users from the photo verification
    whitelist. Only works in bot DMs.

    Args:
        update: Telegram update containing the command.
        context: Bot context with helper methods.
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
            f"attempted to use /unverify command"
        )
        return

    if context.args and len(context.args) > 0:
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ User ID harus berupa angka.")
            return
    else:
        await update.message.reply_text("❌ Penggunaan: /unverify USER_ID")
        return

    db = get_database()

    try:
        db.remove_photo_verification_whitelist(user_id=target_user_id)
        await update.message.reply_text(
            f"✅ User dengan ID {target_user_id} telah dihapus dari whitelist verifikasi foto."
        )
        logger.info(
            f"Admin {admin_user_id} ({update.message.from_user.full_name}) "
            f"removed user {target_user_id} from photo verification whitelist"
        )
    except ValueError as e:
        await update.message.reply_text(f"ℹ️ User dengan ID {target_user_id} tidak ada di whitelist.")
        logger.info(
            f"Admin {admin_user_id} tried to remove {target_user_id} but not in whitelist: {e}"
        )
