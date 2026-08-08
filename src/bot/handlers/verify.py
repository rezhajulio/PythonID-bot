"""
Verification command handler for the PythonID bot.

This module handles the /verify and /unverify commands which allow admins to
manage the photo verification whitelist for users whose profile pictures are
hidden due to Telegram privacy settings.

Verify adds the user to the photo whitelist and clears warnings in the
specified group. It also lifts bot-applied restrictions in that group if
the user's profile is otherwise complete (username present). It does NOT
broadcast to all groups — each action is scoped to one group.
"""

import logging

from telegram import Bot, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from bot.constants import (
    UNRESTRICT_FAILED_MESSAGE,
    UNRESTRICT_NOT_NEEDED_MESSAGE,
    UNRESTRICT_SUCCESS_MESSAGE,
    UNVERIFY_SUCCESS_MESSAGE,
    VERIFY_SUCCESS_MESSAGE,
    VERIFY_SUCCESS_WITH_UNRESTRICT_MESSAGE,
    VERIFICATION_CLEARANCE_MESSAGE,
)
from bot.database.service import DatabaseService, get_database
from bot.group_config import GroupRegistry, get_group_registry
from bot.services.restriction_lock import restriction_lock
from bot.services.telegram_utils import (
    get_user_mention,
    is_user_admin_in_group,
    require_admin_dm_target,
    send_message_with_retry,
    unrestrict_user,
)

logger = logging.getLogger(__name__)


async def verify_user_in_group(
    bot: Bot,
    db: DatabaseService,
    registry: GroupRegistry,
    target_user_id: int,
    admin_user_id: int,
    group_id: int,
) -> str:
    """
    Verify a user in a specific group: add to photo whitelist, clear
    warnings, and lift bot-applied restriction if username is present.

    Args:
        bot: Telegram bot instance.
        db: Database service instance.
        registry: Group registry.
        target_user_id: ID of the user to verify.
        admin_user_id: ID of the admin performing the verification.
        group_id: The group to scope the action to.

    Returns:
        Success message string.
    """
    group_config = registry.get(group_id)
    if group_config is None:
        return f"❌ Grup {group_id} tidak ditemukan."

    try:
        db.add_photo_verification_whitelist(
            user_id=target_user_id,
            verified_by_admin_id=admin_user_id,
        )
    except ValueError:
        pass

    did_unrestrict = False
    unrestrict_failed = False
    deleted_count = 0

    async with restriction_lock(group_id, target_user_id):
        was_restricted = db.is_user_restricted_by_bot_any_kind(target_user_id, group_id)

        if was_restricted:
            try:
                await unrestrict_user(bot, group_id, target_user_id)
                db.mark_all_bot_restrictions_unrestricted(target_user_id, group_id)
                did_unrestrict = True
                logger.info(
                    f"Unrestricted user {target_user_id} in group {group_id} during verification"
                )
            except (TelegramError, RuntimeError) as e:
                logger.info(
                    f"Could not unrestrict user {target_user_id} in group {group_id}: {e}"
                )
                unrestrict_failed = True
            else:
                deleted_count = db.delete_user_warnings(target_user_id, group_id)
                deleted_count += db.delete_user_warnings(
                    target_user_id, group_id, warning_kind="guest_bot"
                )
        else:
            deleted_count = db.delete_user_warnings(target_user_id, group_id)
            deleted_count += db.delete_user_warnings(
                target_user_id, group_id, warning_kind="guest_bot"
            )

    if unrestrict_failed:
        return UNRESTRICT_FAILED_MESSAGE.format(
            user_id=target_user_id, group_id=group_id
        )

    if deleted_count > 0 or did_unrestrict:
        try:
            user_info = await bot.get_chat(target_user_id)
            user_mention = get_user_mention(user_info)
            clearance_message = VERIFICATION_CLEARANCE_MESSAGE.format(
                user_mention=user_mention
            )
            await send_message_with_retry(
                bot,
                chat_id=group_id,
                message_thread_id=group_config.warning_topic_id,
                text=clearance_message,
                parse_mode="Markdown",
            )
        except Exception:
            logger.warning(
                f"Failed to send clearance notification for user {target_user_id} in group {group_id}",
                exc_info=True,
            )

    if did_unrestrict:
        return VERIFY_SUCCESS_WITH_UNRESTRICT_MESSAGE.format(
            user_id=target_user_id, group_id=group_id
        )
    return VERIFY_SUCCESS_MESSAGE.format(
        user_id=target_user_id, group_id=group_id
    )


async def unverify_user(
    db: DatabaseService, target_user_id: int
) -> str:
    """
    Remove a user from the photo verification whitelist.

    Args:
        db: Database service instance.
        target_user_id: ID of the user to unverify.

    Returns:
        Success message string.
    """
    db.remove_photo_verification_whitelist(user_id=target_user_id)
    return UNVERIFY_SUCCESS_MESSAGE.format(target_user_id=target_user_id)


async def unrestrict_user_in_group(
    bot: Bot,
    db: DatabaseService,
    target_user_id: int,
    group_id: int,
) -> str:
    """
    Lift a bot-applied restriction for a user in a specific group.

    Only lifts restrictions that were applied by this bot (restricted_by_bot=True).
    Does not lift manual admin restrictions.

    Args:
        bot: Telegram bot instance.
        db: Database service instance.
        target_user_id: ID of the user to unrestrict.
        group_id: The group to unrestrict in.

    Returns:
        Success or error message string.
    """
    try:
        async with restriction_lock(group_id, target_user_id):
            if not db.is_user_restricted_by_bot_any_kind(target_user_id, group_id):
                return UNRESTRICT_NOT_NEEDED_MESSAGE.format(
                    user_id=target_user_id, group_id=group_id
                )
            await unrestrict_user(bot, group_id, target_user_id)
            db.mark_all_bot_restrictions_unrestricted(target_user_id, group_id)
        logger.info(
            f"Admin unrestricting user {target_user_id} in group {group_id}"
        )
        return UNRESTRICT_SUCCESS_MESSAGE.format(
            user_id=target_user_id, group_id=group_id
        )
    except Exception as e:
        logger.error(
            f"Failed to unrestrict user {target_user_id} in group {group_id}: {e}",
            exc_info=True,
        )
        return UNRESTRICT_FAILED_MESSAGE.format(
            user_id=target_user_id, group_id=group_id
        )


async def handle_verify_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /verify command to whitelist users for profile picture verification.

    Usage: /verify USER_ID (e.g., /verify 123456789)

    Adds the user to the photo whitelist. If the admin is admin in only one
    group, also clears warnings and lifts bot restrictions there. If admin
    in multiple groups, only adds to whitelist (use /check for per-group actions).
    """
    target_user_id = await require_admin_dm_target(
        update,
        context,
        "❌ Penggunaan: /verify USER_ID",
        "/verify command",
    )
    if target_user_id is None:
        return

    admin_user_id = update.message.from_user.id
    db = get_database()

    try:
        from bot.services.telegram_utils import get_admin_groups

        admin_group_ids = get_admin_groups(context, admin_user_id)

        if len(admin_group_ids) == 1:
            registry = get_group_registry()
            message = await verify_user_in_group(
                context.bot, db, registry, target_user_id, admin_user_id, admin_group_ids[0]
            )
        else:
            db.add_photo_verification_whitelist(
                user_id=target_user_id,
                verified_by_admin_id=admin_user_id,
            )
            message = (
                f"✅ User dengan ID {target_user_id} ditambahkan ke whitelist foto profil.\n"
                f"Gunakan /check untuk mengelola per grup."
            )

        await update.message.reply_text(message)
        logger.info(
            f"Admin {admin_user_id} ({update.message.from_user.full_name}) "
            f"whitelisted user {target_user_id} for photo verification"
        )
    except ValueError:
        await update.message.reply_text(
            f"ℹ️ User dengan ID {target_user_id} sudah ada di whitelist."
        )


async def handle_unverify_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /unverify command to remove users from photo verification whitelist.

    Usage: /unverify USER_ID (e.g., /unverify 123456789)
    """
    target_user_id = await require_admin_dm_target(
        update,
        context,
        "❌ Penggunaan: /unverify USER_ID",
        "/unverify command",
    )
    if target_user_id is None:
        return

    db = get_database()

    try:
        message = await unverify_user(db, target_user_id)
        await update.message.reply_text(message)
    except ValueError:
        await update.message.reply_text(
            f"ℹ️ User dengan ID {target_user_id} tidak ada di whitelist."
        )


async def handle_verify_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle callback query for verify button (group-scoped).

    Callback data format: verify:{group_id}:{user_id}
    """
    query = update.callback_query
    if not query or not query.from_user or not query.data:
        return

    await query.answer()

    parts = query.data.split(":")
    try:
        group_id = int(parts[1])
        target_user_id = int(parts[2])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Data callback tidak valid.")
        return

    admin_user_id = query.from_user.id
    if not is_user_admin_in_group(context, group_id, admin_user_id):
        await query.edit_message_text("❌ Kamu bukan admin di grup ini.")
        return

    db = get_database()

    try:
        registry = get_group_registry()
        message = await verify_user_in_group(
            context.bot, db, registry, target_user_id, admin_user_id, group_id
        )
        await query.edit_message_text(message, parse_mode="Markdown")
        logger.info(
            f"Admin {admin_user_id} ({query.from_user.full_name}) "
            f"verified user {target_user_id} in group {group_id} via callback"
        )
    except ValueError:
        await query.edit_message_text(
            f"ℹ️ User dengan ID {target_user_id} sudah ada di whitelist."
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Terjadi kesalahan: {e}")
        logger.error(f"Error during verify callback: {e}", exc_info=True)


async def handle_unverify_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle callback query for unverify button (group-scoped).

    Callback data format: unverify:{group_id}:{user_id}
    """
    query = update.callback_query
    if not query or not query.from_user or not query.data:
        return

    await query.answer()

    parts = query.data.split(":")
    try:
        group_id = int(parts[1])
        target_user_id = int(parts[2])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Data callback tidak valid.")
        return

    admin_user_id = query.from_user.id
    if not is_user_admin_in_group(context, group_id, admin_user_id):
        await query.edit_message_text("❌ Kamu bukan admin di grup ini.")
        return

    db = get_database()

    try:
        message = await unverify_user(db, target_user_id)
        await query.edit_message_text(message)
        logger.info(
            f"Admin {admin_user_id} ({query.from_user.full_name}) "
            f"unverified user {target_user_id} via callback"
        )
    except ValueError:
        await query.edit_message_text(
            f"ℹ️ User dengan ID {target_user_id} tidak ada di whitelist."
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Terjadi kesalahan: {e}")
        logger.error(f"Error during unverify callback: {e}", exc_info=True)


async def handle_unrestrict_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle callback query for unrestrict button (group-scoped).

    Only lifts bot-applied restrictions, not manual admin restrictions.

    Callback data format: unrestrict:{group_id}:{user_id}
    """
    query = update.callback_query
    if not query or not query.from_user or not query.data:
        return

    await query.answer()

    parts = query.data.split(":")
    try:
        group_id = int(parts[1])
        target_user_id = int(parts[2])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Data callback tidak valid.")
        return

    admin_user_id = query.from_user.id
    if not is_user_admin_in_group(context, group_id, admin_user_id):
        await query.edit_message_text("❌ Kamu bukan admin di grup ini.")
        return

    db = get_database()

    try:
        message = await unrestrict_user_in_group(
            context.bot, db, target_user_id, group_id
        )
        await query.edit_message_text(message, parse_mode="Markdown")
        logger.info(
            f"Admin {admin_user_id} unrestricting user {target_user_id} in group {group_id} via callback"
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Terjadi kesalahan: {e}")
        logger.error(f"Error during unrestrict callback: {e}", exc_info=True)
