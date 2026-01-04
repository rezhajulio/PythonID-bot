"""
Verification command handler for the PythonID bot.

This module handles the /verify and /unverify commands which allow admins to
manage the photo verification whitelist for users whose profile pictures are
hidden due to Telegram privacy settings.
"""

import logging

from telegram import Bot, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from bot.config import Settings, get_settings
from bot.constants import VERIFICATION_CLEARANCE_MESSAGE
from bot.database.service import DatabaseService, get_database
from bot.services.telegram_utils import get_user_mention_by_id, unrestrict_user

logger = logging.getLogger(__name__)


async def verify_user(
    bot: Bot, db: DatabaseService, settings: Settings, target_user_id: int, admin_user_id: int
) -> str:
    """
    Verify a user by adding them to the photo verification whitelist.

    This function handles the core verification logic: adds user to whitelist,
    unrestricts them, deletes warnings, and sends clearance notification if needed.

    Args:
        bot: Telegram bot instance.
        db: Database service instance.
        settings: Bot settings instance.
        target_user_id: ID of the user to verify.
        admin_user_id: ID of the admin performing the verification.

    Returns:
        Success message string.

    Raises:
        ValueError: If user is already whitelisted.
    """
    db.add_photo_verification_whitelist(
        user_id=target_user_id,
        verified_by_admin_id=admin_user_id,
    )

    # Unrestrict user if they are restricted
    try:
        await unrestrict_user(bot, settings.group_id, target_user_id)
        logger.info(f"Unrestricted user {target_user_id} during verification")
    except BadRequest as e:
        # User might not be restricted or not in group - that's okay
        logger.info(f"Could not unrestrict user {target_user_id}: {e}")

    # Delete all warning records for this user
    deleted_count = db.delete_user_warnings(target_user_id, settings.group_id)

    # Send notification to warning topic if user had previous warnings
    if deleted_count > 0:
        # Get user info for proper mention
        user_info = await bot.get_chat(target_user_id)
        user_mention = get_user_mention_by_id(target_user_id, user_info.full_name)

        # Send clearance message to warning topic
        clearance_message = VERIFICATION_CLEARANCE_MESSAGE.format(
            user_mention=user_mention
        )
        await bot.send_message(
            chat_id=settings.group_id,
            message_thread_id=settings.warning_topic_id,
            text=clearance_message,
            parse_mode="Markdown"
        )
        logger.info(f"Sent clearance notification to warning topic for user {target_user_id}")
        logger.info(f"Deleted {deleted_count} warning record(s) for user {target_user_id}")

    return (
        f"✅ User dengan ID {target_user_id} telah diverifikasi:\n"
        f"• Ditambahkan ke whitelist foto profil\n"
        f"• Pembatasan dicabut (jika ada)\n"
        f"• Riwayat warning dihapus\n\n"
        f"User ini tidak akan dicek foto profil lagi."
    )


async def unverify_user(
    db: DatabaseService, target_user_id: int, admin_user_id: int
) -> str:
    """
    Unverify a user by removing them from the photo verification whitelist.

    Args:
        db: Database service instance.
        target_user_id: ID of the user to unverify.
        admin_user_id: ID of the admin performing the unverification.

    Returns:
        Success message string.

    Raises:
        ValueError: If user is not in whitelist.
    """
    db.remove_photo_verification_whitelist(user_id=target_user_id)
    logger.info(
        f"Admin {admin_user_id} removed user {target_user_id} from photo verification whitelist"
    )
    return f"✅ User dengan ID {target_user_id} telah dihapus dari whitelist verifikasi foto."


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
        settings = get_settings()
        message = await verify_user(context.bot, db, settings, target_user_id, admin_user_id)
        await update.message.reply_text(message)
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
        message = await unverify_user(db, target_user_id, admin_user_id)
        await update.message.reply_text(message)
    except ValueError as e:
        await update.message.reply_text(f"ℹ️ User dengan ID {target_user_id} tidak ada di whitelist.")
        logger.info(
            f"Admin {admin_user_id} tried to remove {target_user_id} but not in whitelist: {e}"
        )


async def handle_verify_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle callback query for verify button.

    Processes the inline button click to verify a user and updates the message
    with the result.

    Args:
        update: Telegram update containing the callback query.
        context: Bot context with helper methods.
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
            f"attempted to use verify callback"
        )
        return

    # Extract user_id from callback_data
    try:
        target_user_id = int(query.data.split(":")[1])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Data callback tidak valid.")
        logger.error(f"Invalid callback_data format: {query.data}")
        return

    db = get_database()

    try:
        settings = get_settings()
        message = await verify_user(context.bot, db, settings, target_user_id, admin_user_id)
        await query.edit_message_text(message)
        logger.info(
            f"Admin {admin_user_id} ({query.from_user.full_name}) "
            f"verified user {target_user_id} via callback"
        )
    except ValueError as e:
        await query.edit_message_text(f"ℹ️ User dengan ID {target_user_id} sudah ada di whitelist.")
        logger.info(
            f"Admin {admin_user_id} tried to verify {target_user_id} via callback but already exists: {e}"
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Terjadi kesalahan: {str(e)}")
        logger.error(f"Error during verify callback: {e}", exc_info=True)


async def handle_unverify_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle callback query for unverify button.

    Processes the inline button click to unverify a user and updates the message
    with the result.

    Args:
        update: Telegram update containing the callback query.
        context: Bot context with helper methods.
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
            f"attempted to use unverify callback"
        )
        return

    # Extract user_id from callback_data
    try:
        target_user_id = int(query.data.split(":")[1])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Data callback tidak valid.")
        logger.error(f"Invalid callback_data format: {query.data}")
        return

    db = get_database()

    try:
        message = await unverify_user(db, target_user_id, admin_user_id)
        await query.edit_message_text(message)
        logger.info(
            f"Admin {admin_user_id} ({query.from_user.full_name}) "
            f"unverified user {target_user_id} via callback"
        )
    except ValueError as e:
        await query.edit_message_text(f"ℹ️ User dengan ID {target_user_id} tidak ada di whitelist.")
        logger.info(
            f"Admin {admin_user_id} tried to unverify {target_user_id} via callback but not in whitelist: {e}"
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Terjadi kesalahan: {str(e)}")
        logger.error(f"Error during unverify callback: {e}", exc_info=True)
