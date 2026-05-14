"""Trusted-user command handlers for anti-spam bypass management."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.constants import (
    TRUST_ADDED_MESSAGE,
    TRUST_ALREADY_EXISTS_MESSAGE,
    TRUST_LIST_EMPTY_MESSAGE,
    TRUST_LIST_HEADER,
    TRUST_REMOVED_MESSAGE,
    TRUST_USER_ID_INVALID_MESSAGE,
    TRUST_USER_ID_REQUIRED_MESSAGE,
    TRUST_USER_NOT_FOUND_MESSAGE,
)
from bot.database.service import DatabaseService, get_database
from bot.group_config import GroupRegistry, get_group_registry
from bot.services.telegram_utils import extract_forwarded_user, unrestrict_user

logger = logging.getLogger(__name__)


def _add_trusted_cache(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    trusted_ids = set(context.bot_data.get("trusted_user_ids", []))
    trusted_ids.add(user_id)
    context.bot_data["trusted_user_ids"] = list(trusted_ids)


def _remove_trusted_cache(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    trusted_ids = set(context.bot_data.get("trusted_user_ids", []))
    trusted_ids.discard(user_id)
    context.bot_data["trusted_user_ids"] = list(trusted_ids)


def _resolve_target_user_id(update: Update, args: list[str]) -> int:
    if args:
        try:
            return int(args[0])
        except ValueError as exc:
            raise ValueError(TRUST_USER_ID_INVALID_MESSAGE) from exc

    if update.message:
        forwarded = extract_forwarded_user(update.message)
        if forwarded:
            return forwarded[0]

    raise ValueError(TRUST_USER_ID_REQUIRED_MESSAGE)


async def trust_user(
    bot: object,
    db: DatabaseService,
    registry: GroupRegistry,
    target_user_id: int,
    admin_user_id: int,
) -> tuple[int, int]:
    """Add trusted user and apply cleanup side effects.

    Returns:
        tuple[int, int]: (probation_clear_count, unrestrict_attempt_count)
    """
    db.add_trusted_user(
        user_id=target_user_id,
        trusted_by_admin_id=admin_user_id,
    )

    cleared_probation = 0
    unrestricted_groups = 0
    for group_config in registry.all_groups():
        try:
            if db.get_new_user_probation(target_user_id, group_config.group_id):
                db.clear_new_user_probation(target_user_id, group_config.group_id)
                cleared_probation += 1

            await unrestrict_user(bot, group_config.group_id, target_user_id)
            unrestricted_groups += 1
        except Exception:
            logger.warning(
                f"Trust side effects failed for user {target_user_id} in group {group_config.group_id}",
                exc_info=True,
            )
            continue

    return cleared_probation, unrestricted_groups


async def untrust_user(
    db: DatabaseService,
    target_user_id: int,
) -> None:
    """Remove trusted user entry."""
    db.remove_trusted_user(user_id=target_user_id)


async def handle_trust_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /trust command in bot DM."""
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
        return

    try:
        target_user_id = _resolve_target_user_id(update, context.args)
    except ValueError as e:
        await update.message.reply_text(str(e))
        return

    db = get_database()
    registry = get_group_registry()

    try:
        cleared_count, unrestricted_count = await trust_user(
            context.bot, db, registry, target_user_id, admin_user_id
        )
        _add_trusted_cache(context, target_user_id)
        await update.message.reply_text(
            TRUST_ADDED_MESSAGE.format(
                user_id=target_user_id,
                probation_clear_count=cleared_count,
                unrestrict_count=unrestricted_count,
            )
        )
    except ValueError:
        await update.message.reply_text(
            TRUST_ALREADY_EXISTS_MESSAGE.format(user_id=target_user_id)
        )


async def handle_untrust_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /untrust command in bot DM."""
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
        return

    try:
        target_user_id = _resolve_target_user_id(update, context.args)
    except ValueError as e:
        await update.message.reply_text(str(e))
        return

    db = get_database()

    try:
        await untrust_user(db, target_user_id)
        _remove_trusted_cache(context, target_user_id)
        await update.message.reply_text(
            TRUST_REMOVED_MESSAGE.format(user_id=target_user_id)
        )
    except ValueError:
        await update.message.reply_text(
            TRUST_USER_NOT_FOUND_MESSAGE.format(user_id=target_user_id)
        )


async def handle_trusted_list_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /trusted command in bot DM."""
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
        return

    db = get_database()
    trusted_ids = sorted(db.get_trusted_user_ids())

    if not trusted_ids:
        await update.message.reply_text(TRUST_LIST_EMPTY_MESSAGE)
        return

    trusted_lines = "\n".join(f"• `{user_id}`" for user_id in trusted_ids)
    await update.message.reply_text(
        TRUST_LIST_HEADER.format(trusted_lines=trusted_lines),
        parse_mode="Markdown",
    )


async def handle_trust_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle trust callback button."""
    query = update.callback_query
    if not query or not query.from_user or not query.data:
        return

    await query.answer()

    admin_user_id = query.from_user.id
    admin_ids = context.bot_data.get("admin_ids", [])
    if admin_user_id not in admin_ids:
        await query.edit_message_text("❌ Kamu tidak memiliki izin untuk menggunakan perintah ini.")
        return

    try:
        target_user_id = int(query.data.split(":")[1])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Data callback tidak valid.")
        return

    db = get_database()
    registry = get_group_registry()

    try:
        cleared_count, unrestricted_count = await trust_user(
            context.bot, db, registry, target_user_id, admin_user_id
        )
        _add_trusted_cache(context, target_user_id)
        await query.edit_message_text(
            TRUST_ADDED_MESSAGE.format(
                user_id=target_user_id,
                probation_clear_count=cleared_count,
                unrestrict_count=unrestricted_count,
            )
        )
    except ValueError:
        await query.edit_message_text(
            TRUST_ALREADY_EXISTS_MESSAGE.format(user_id=target_user_id)
        )


async def handle_untrust_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle untrust callback button."""
    query = update.callback_query
    if not query or not query.from_user or not query.data:
        return

    await query.answer()

    admin_user_id = query.from_user.id
    admin_ids = context.bot_data.get("admin_ids", [])
    if admin_user_id not in admin_ids:
        await query.edit_message_text("❌ Kamu tidak memiliki izin untuk menggunakan perintah ini.")
        return

    try:
        target_user_id = int(query.data.split(":")[1])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Data callback tidak valid.")
        return

    db = get_database()

    try:
        await untrust_user(db, target_user_id)
        _remove_trusted_cache(context, target_user_id)
        await query.edit_message_text(
            TRUST_REMOVED_MESSAGE.format(user_id=target_user_id)
        )
    except ValueError:
        await query.edit_message_text(
            TRUST_USER_NOT_FOUND_MESSAGE.format(user_id=target_user_id)
        )
