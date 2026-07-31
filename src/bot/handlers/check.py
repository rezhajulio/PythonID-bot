"""
Admin check handler for the PythonID bot.

This module handles admin commands to manually check user profiles:
1. /check <user_id> - Check a user's profile status
2. Forwarded message - Check profile and show action buttons
3. Group selector callback - Pick which group to act on
4. Warn button callback - Send warning to user in the selected group

All actions are scoped to a single group. Callbacks encode the group_id
so that admin authorization can be checked per-group.
"""

import logging

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TimedOut
from telegram.ext import ContextTypes

from bot.constants import (
    ADMIN_CHECK_ACTION_COMPLETE,
    ADMIN_CHECK_ACTION_INCOMPLETE,
    ADMIN_CHECK_GROUP_NONE,
    ADMIN_CHECK_GROUP_PROMPT,
    ADMIN_CHECK_PROMPT,
    ADMIN_WARN_SENT_MESSAGE,
    ADMIN_WARN_USER_MESSAGE,
    CHECK_TRUST_BUTTON_LABEL,
    CHECK_UNRESTRICT_BUTTON_LABEL,
    CHECK_UNTRUST_BUTTON_LABEL,
    CHECK_UNVERIFY_BUTTON_LABEL,
    CHECK_VERIFY_BUTTON_LABEL,
    CHECK_WARN_BUTTON_LABEL,
    MISSING_ITEMS_SEPARATOR,
)
from bot.database.service import get_database
from bot.group_config import get_group_registry
from bot.services.telegram_utils import (
    extract_forwarded_user,
    get_admin_groups,
    get_user_mention,
    get_user_mention_by_id,
    is_user_admin_in_group,
    require_admin_dm_target,
    send_message_with_retry,
)
from bot.services.user_checker import check_user_profile

logger = logging.getLogger(__name__)


async def _build_profile_status(
    bot: Bot, user_id: int, user_name: str
) -> tuple[str, str, bool, bool, bool, bool]:
    """
    Check a user's profile and return status info.

    Returns:
        Tuple of (user_mention, photo_emoji, has_photo, has_username,
                  is_whitelisted, is_trusted).
    """
    try:
        chat = await bot.get_chat(user_id)
        result = await check_user_profile(bot, chat)  # type: ignore
    except Exception as e:
        logger.error(f"Failed to check profile for user {user_id}: {e}")
        raise

    user_mention = get_user_mention_by_id(user_id, user_name)
    db = get_database()
    is_whitelisted = db.is_user_photo_whitelisted(user_id)
    is_trusted = db.is_user_trusted(user_id) is True

    return user_mention, "✅" if result.has_profile_photo else "❌", result.has_profile_photo, result.has_username, is_whitelisted, is_trusted


def _build_group_selector_keyboard(
    admin_group_ids: list[int], user_id: int
) -> InlineKeyboardMarkup:
    """Build the group selector keyboard."""
    buttons = []
    for gid in admin_group_ids:
        buttons.append(
            InlineKeyboardButton(
                text=f"📋 Grup {gid}",
                callback_data=f"checkgrp:{gid}:{user_id}",
            )
        )
    return InlineKeyboardMarkup([[b] for b in buttons])


def _build_action_keyboard(
    group_id: int,
    user_id: int,
    is_complete: bool,
    is_whitelisted: bool,
    is_trusted: bool,
    missing_code: str = "",
) -> InlineKeyboardMarkup:
    """
    Build the action keyboard for a specific group.

    Callback data format: action:{group_id}:{user_id}[:missing_code]
    """
    buttons: list[InlineKeyboardButton] = []

    if not is_complete:
        buttons.append(
            InlineKeyboardButton(
                CHECK_WARN_BUTTON_LABEL,
                callback_data=f"warn:{group_id}:{user_id}:{missing_code}",
            )
        )

    if not is_complete or is_whitelisted:
        if is_whitelisted:
            buttons.append(
                InlineKeyboardButton(
                    CHECK_UNVERIFY_BUTTON_LABEL,
                    callback_data=f"unverify:{group_id}:{user_id}",
                )
            )
        else:
            buttons.append(
                InlineKeyboardButton(
                    CHECK_VERIFY_BUTTON_LABEL,
                    callback_data=f"verify:{group_id}:{user_id}",
                )
            )

    if is_trusted:
        buttons.append(
            InlineKeyboardButton(
                CHECK_UNTRUST_BUTTON_LABEL,
                callback_data=f"untrust:{group_id}:{user_id}",
            )
        )
    else:
        buttons.append(
            InlineKeyboardButton(
                CHECK_TRUST_BUTTON_LABEL,
                callback_data=f"trust:{group_id}:{user_id}",
            )
        )

    buttons.append(
        InlineKeyboardButton(
            CHECK_UNRESTRICT_BUTTON_LABEL,
            callback_data=f"unrestrict:{group_id}:{user_id}",
        )
    )

    # Split into rows of max 2 buttons for mobile readability
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)


async def _show_check_result(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    target_user_id: int,
    user_name: str,
) -> None:
    """
    Check a user's profile and show the result with group selector or actions.

    If the admin is admin in only one group, shows actions directly.
    If admin in multiple groups, shows a group selector first.
    """
    admin_user_id = update.message.from_user.id if update.message else update.callback_query.from_user.id  # type: ignore[union-attr]
    reply_func = update.message.reply_text if update.message else update.callback_query.edit_message_text  # type: ignore[union-attr]

    user_mention, photo_status, has_photo, has_username, is_whitelisted, is_trusted = (
        await _build_profile_status(context.bot, target_user_id, user_name)
    )
    username_status = "✅" if has_username else "❌"
    is_complete = has_photo and has_username

    admin_group_ids = get_admin_groups(context, admin_user_id)

    if not admin_group_ids:
        await reply_func(ADMIN_CHECK_GROUP_NONE)
        return

    if len(admin_group_ids) == 1:
        group_id = admin_group_ids[0]
        missing_code = ""
        if not has_photo:
            missing_code += "p"
        if not has_username:
            missing_code += "u"

        action_prompt = ADMIN_CHECK_ACTION_COMPLETE if is_complete else ADMIN_CHECK_ACTION_INCOMPLETE
        message = ADMIN_CHECK_PROMPT.format(
            user_mention=user_mention,
            user_id=target_user_id,
            photo_status=photo_status,
            username_status=username_status,
            action_prompt=action_prompt,
        )
        keyboard = _build_action_keyboard(
            group_id, target_user_id, is_complete, is_whitelisted, is_trusted, missing_code
        )
        await reply_func(message, reply_markup=keyboard, parse_mode="Markdown")
    else:
        message = ADMIN_CHECK_GROUP_PROMPT.format(
            user_mention=user_mention,
            user_id=target_user_id,
            photo_status=photo_status,
            username_status=username_status,
        )
        keyboard = _build_group_selector_keyboard(admin_group_ids, target_user_id)
        await reply_func(message, reply_markup=keyboard, parse_mode="Markdown")


async def handle_check_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle /check command to manually check a user's profile.

    Usage: /check USER_ID (e.g., /check 123456789)

    Only works in bot DMs for admins.
    """
    target_user_id = await require_admin_dm_target(
        update,
        context,
        "❌ Penggunaan: /check USER_ID",
        "/check command",
    )
    if target_user_id is None:
        return

    admin_user_id = update.message.from_user.id

    try:
        chat = await context.bot.get_chat(target_user_id)
        user_name = chat.full_name or f"User {target_user_id}"

        await _show_check_result(update, context, target_user_id, user_name)

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

    forwarded_info = extract_forwarded_user(update.message)
    if not forwarded_info:
        await update.message.reply_text(
            "❌ Tidak dapat mengekstrak informasi user dari pesan yang diteruskan.\n"
            "Pastikan user tidak menyembunyikan status forward di pengaturan privasi."
        )
        return

    user_id, user_name = forwarded_info

    try:
        await _show_check_result(update, context, user_id, user_name)

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


async def handle_check_group_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle callback query for group selection in /check.

    Shows the action keyboard for the selected group.
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

    try:
        chat = await context.bot.get_chat(target_user_id)
        user_name = chat.full_name or f"User {target_user_id}"

        user_mention, photo_status, has_photo, has_username, is_whitelisted, is_trusted = (
            await _build_profile_status(context.bot, target_user_id, user_name)
        )
        username_status = "✅" if has_username else "❌"
        is_complete = has_photo and has_username

        missing_code = ""
        if not has_photo:
            missing_code += "p"
        if not has_username:
            missing_code += "u"

        action_prompt = ADMIN_CHECK_ACTION_COMPLETE if is_complete else ADMIN_CHECK_ACTION_INCOMPLETE
        message = ADMIN_CHECK_PROMPT.format(
            user_mention=user_mention,
            user_id=target_user_id,
            photo_status=photo_status,
            username_status=username_status,
            action_prompt=action_prompt,
        )
        keyboard = _build_action_keyboard(
            group_id, target_user_id, is_complete, is_whitelisted, is_trusted, missing_code
        )
        await query.edit_message_text(message, reply_markup=keyboard, parse_mode="Markdown")
    except Exception as e:
        await query.edit_message_text(f"❌ Gagal memeriksa user: {e}")
        logger.error(f"Error in check group callback: {e}", exc_info=True)


def _parse_warn_callback_data(data: str) -> tuple[int, int, str] | None:
    """Parse warn callback data (warn:<group_id>:<user_id>:<missing_code>)."""
    try:
        parts = data.split(":")
        group_id = int(parts[1])
        user_id = int(parts[2])
        missing_code = parts[3] if len(parts) > 3 else ""
        return (group_id, user_id, missing_code)
    except (IndexError, ValueError):
        return None


async def handle_warn_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle callback query for warn button.

    Sends a warning message to the user in the selected group only.
    """
    query = update.callback_query
    if not query or not query.from_user or not query.data:
        return

    await query.answer()

    parsed = _parse_warn_callback_data(query.data)
    if parsed is None:
        await query.edit_message_text("❌ Data callback tidak valid.")
        logger.error(f"Invalid callback_data format: {query.data}")
        return
    group_id, target_user_id, missing_code = parsed

    admin_user_id = query.from_user.id
    if not is_user_admin_in_group(context, group_id, admin_user_id):
        await query.edit_message_text("❌ Kamu bukan admin di grup ini.")
        return

    missing_items = []
    if "p" in missing_code:
        missing_items.append("foto profil publik")
    if "u" in missing_code:
        missing_items.append("username")
    missing_text = MISSING_ITEMS_SEPARATOR.join(missing_items) if missing_items else "profil"

    registry = get_group_registry()
    group_config = registry.get(group_id)

    if group_config is None:
        await query.edit_message_text("❌ Grup tidak ditemukan di registry.")
        return

    try:
        chat = await context.bot.get_chat(target_user_id)
        user_mention = get_user_mention(chat)

        warn_message = ADMIN_WARN_USER_MESSAGE.format(
            user_mention=user_mention,
            missing_text=missing_text,
            rules_link=group_config.rules_link,
        )
        ok = await send_message_with_retry(
            context.bot,
            chat_id=group_config.group_id,
            message_thread_id=group_config.warning_topic_id,
            text=warn_message,
            parse_mode="Markdown",
        )

        if ok:
            success_message = ADMIN_WARN_SENT_MESSAGE.format(user_mention=user_mention)
            await query.edit_message_text(success_message, parse_mode="Markdown")
            logger.info(
                f"Admin {admin_user_id} sent warning to user {target_user_id} in group {group_id}"
            )
        else:
            await query.edit_message_text("❌ Gagal mengirim peringatan ke grup.")

    except TimedOut:
        await query.edit_message_text("⏳ Request timeout. Silakan coba lagi.")
        logger.warning(f"Timeout sending warning to user {target_user_id}")
    except Exception as e:
        await query.edit_message_text(f"❌ Gagal mengirim peringatan: {e}")
        logger.error(f"Error sending warning to user {target_user_id}: {e}", exc_info=True)
