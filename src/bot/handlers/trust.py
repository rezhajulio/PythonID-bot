"""Trusted-user command handlers for anti-spam bypass management.

Trust adds a user to the anti-spam bypass list and clears their probation.
It does NOT unrestrict the user — use the separate "Buka pembatasan bot"
action for that. This separation prevents trust from lifting manual
admin restrictions as a side effect.

Commands /trust, /untrust, /trusted are DM-only and require admin status.
Callback buttons (trust/untrust) are group-scoped: they encode group_id
and verify the caller is an admin of that specific group.
"""

import logging
from datetime import UTC

from telegram import Update
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from bot.constants import (
    TRUST_ADDED_MESSAGE,
    TRUST_ALREADY_EXISTS_MESSAGE,
    TRUST_CALLBACK_INVALID_MESSAGE,
    TRUST_DM_ONLY_MESSAGE,
    TRUST_LIST_EMPTY_MESSAGE,
    TRUST_LIST_HEADER,
    TRUST_NO_GROUP_PERMISSION_MESSAGE,
    TRUST_NO_PERMISSION_MESSAGE,
    TRUST_REMOVED_MESSAGE,
    TRUST_USER_ID_INVALID_MESSAGE,
    TRUST_USER_ID_REQUIRED_MESSAGE,
    TRUST_USER_NOT_FOUND_MESSAGE,
)
from bot.database.service import DatabaseService, get_database
from bot.group_config import GroupRegistry, get_group_registry
from bot.services.telegram_utils import (
    extract_forwarded_user,
    is_user_admin_in_group,
)

logger = logging.getLogger(__name__)


def _add_trusted_cache(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    context.bot_data.setdefault("trusted_user_ids", set()).add(user_id)


def _remove_trusted_cache(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    context.bot_data.setdefault("trusted_user_ids", set()).discard(user_id)


def _format_person(full_name: str, user_id: int) -> str:
    """Return a markdown-safe display for a stored person."""
    if full_name:
        return escape_markdown(full_name, version=1)
    return f"User {user_id}"


def _format_person_with_username(full_name: str, username: str | None, user_id: int) -> str:
    display = _format_person(full_name, user_id)
    if username:
        display += f" (@{escape_markdown(username, version=1)})"
    return display


def _resolve_target_user_id(
    update: Update, args: list[str]
) -> tuple[int | None, str | None]:
    """Resolve the target user ID from CLI args or a forwarded message."""
    if args:
        try:
            return int(args[0]), None
        except ValueError:
            return None, TRUST_USER_ID_INVALID_MESSAGE

    if update.message:
        forwarded = extract_forwarded_user(update.message)
        if forwarded:
            return forwarded[0], None

    return None, TRUST_USER_ID_REQUIRED_MESSAGE


async def trust_user(
    db: DatabaseService,
    registry: GroupRegistry,
    target_user_id: int,
    admin_user_id: int,
    target_user_full_name: str = "",
    target_username: str | None = None,
    admin_full_name: str = "",
    admin_username: str | None = None,
    group_id: int | None = None,
) -> int:
    """Add a trusted user and clear probation.

    Trust does NOT unrestrict the user. Unrestriction is a separate
    action ("Buka pembatasan bot") so that trusting a user doesn't
    inadvertently lift manual admin restrictions.

    If ``group_id`` is provided, probation is cleared only in that group.
    Otherwise, probation is cleared in all monitored groups (legacy behavior
    for the /trust command).

    Returns:
        int: Number of groups where probation was cleared.
    """
    db.add_trusted_user(
        user_id=target_user_id,
        trusted_by_admin_id=admin_user_id,
        user_full_name=target_user_full_name,
        username=target_username,
        admin_full_name=admin_full_name,
        admin_username=admin_username,
    )

    cleared_probation = 0
    groups_to_check = (
        [registry.get(group_id)] if group_id is not None else registry.all_groups()
    )
    for group_config in groups_to_check:
        if group_config is None:
            continue
        try:
            if db.get_new_user_probation(target_user_id, group_config.group_id):
                db.clear_new_user_probation(target_user_id, group_config.group_id)
                cleared_probation += 1
        except Exception:
            logger.warning(
                f"Probation cleanup failed for user {target_user_id} in group {group_config.group_id}",
                exc_info=True,
            )

    return cleared_probation


async def handle_trust_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /trust command in bot DM."""
    if not update.message or not update.message.from_user:
        return

    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_text(TRUST_DM_ONLY_MESSAGE)
        return

    admin_user_id = update.message.from_user.id
    admin_ids = context.bot_data.get("admin_ids", [])
    if admin_user_id not in admin_ids:
        await update.message.reply_text(TRUST_NO_PERMISSION_MESSAGE)
        return

    target_user_id, error_message = _resolve_target_user_id(update, context.args)
    if error_message is not None:
        await update.message.reply_text(error_message)
        return

    target_full_name = ""
    target_username = None
    if update.message.forward_from:
        target_full_name = update.message.forward_from.full_name
        target_username = update.message.forward_from.username

    db = get_database()
    registry = get_group_registry()

    try:
        cleared_count = await trust_user(
            db, registry, target_user_id, admin_user_id,
            target_user_full_name=target_full_name,
            target_username=target_username,
            admin_full_name=update.message.from_user.full_name,
            admin_username=update.message.from_user.username,
        )
        _add_trusted_cache(context, target_user_id)
        await update.message.reply_text(
            TRUST_ADDED_MESSAGE.format(
                user_id=target_user_id,
                probation_clear_count=cleared_count,
            ),
            parse_mode="Markdown",
        )
    except ValueError:
        await update.message.reply_text(
            TRUST_ALREADY_EXISTS_MESSAGE.format(user_id=target_user_id),
            parse_mode="Markdown",
        )


async def handle_untrust_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /untrust command in bot DM."""
    if not update.message or not update.message.from_user:
        return

    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_text(TRUST_DM_ONLY_MESSAGE)
        return

    admin_user_id = update.message.from_user.id
    admin_ids = context.bot_data.get("admin_ids", [])
    if admin_user_id not in admin_ids:
        await update.message.reply_text(TRUST_NO_PERMISSION_MESSAGE)
        return

    target_user_id, error_message = _resolve_target_user_id(update, context.args)
    if error_message is not None:
        await update.message.reply_text(error_message)
        return

    db = get_database()

    try:
        db.remove_trusted_user(user_id=target_user_id)
        _remove_trusted_cache(context, target_user_id)
        await update.message.reply_text(
            TRUST_REMOVED_MESSAGE.format(user_id=target_user_id),
            parse_mode="Markdown",
        )
    except ValueError:
        await update.message.reply_text(
            TRUST_USER_NOT_FOUND_MESSAGE.format(user_id=target_user_id),
            parse_mode="Markdown",
        )


async def handle_trusted_list_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /trusted command in bot DM."""
    if not update.message or not update.message.from_user:
        return

    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_text(TRUST_DM_ONLY_MESSAGE)
        return

    admin_user_id = update.message.from_user.id
    admin_ids = context.bot_data.get("admin_ids", [])
    if admin_user_id not in admin_ids:
        await update.message.reply_text(TRUST_NO_PERMISSION_MESSAGE)
        return

    db = get_database()
    trusted_users = db.get_trusted_users()

    if not trusted_users:
        await update.message.reply_text(TRUST_LIST_EMPTY_MESSAGE)
        return

    trusted_lines = []
    for record in trusted_users:
        trusted_at = record.trusted_at
        if trusted_at.tzinfo is None:
            trusted_at = trusted_at.replace(tzinfo=UTC)
        trusted_at_display = trusted_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")

        user_display = _format_person_with_username(
            record.user_full_name, record.username, record.user_id
        )
        admin_display = _format_person_with_username(
            record.admin_full_name, record.admin_username, record.trusted_by_admin_id
        )

        trusted_lines.append(
            f"• {user_display} (`{record.user_id}`) — oleh {admin_display} "
            f"(`{record.trusted_by_admin_id}`) pada `{trusted_at_display}`"
        )

    await update.message.reply_text(
        TRUST_LIST_HEADER.format(trusted_lines="\n".join(trusted_lines)),
        parse_mode="Markdown",
    )


async def handle_trust_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle trust callback button (group-scoped).

    Callback data format: trust:{group_id}:{user_id}
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
        await query.edit_message_text(TRUST_CALLBACK_INVALID_MESSAGE)
        return

    admin_user_id = query.from_user.id
    if not is_user_admin_in_group(context, group_id, admin_user_id):
        await query.edit_message_text(TRUST_NO_GROUP_PERMISSION_MESSAGE)
        return

    db = get_database()
    registry = get_group_registry()

    try:
        cleared_count = await trust_user(
            db, registry, target_user_id, admin_user_id,
            admin_full_name=query.from_user.full_name,
            admin_username=query.from_user.username,
            group_id=group_id,
        )
        _add_trusted_cache(context, target_user_id)
        await query.edit_message_text(
            TRUST_ADDED_MESSAGE.format(
                user_id=target_user_id,
                probation_clear_count=cleared_count,
            ),
            parse_mode="Markdown",
        )
    except ValueError:
        await query.edit_message_text(
            TRUST_ALREADY_EXISTS_MESSAGE.format(user_id=target_user_id),
            parse_mode="Markdown",
        )


async def handle_untrust_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle untrust callback button (group-scoped).

    Callback data format: untrust:{group_id}:{user_id}
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
        await query.edit_message_text(TRUST_CALLBACK_INVALID_MESSAGE)
        return

    admin_user_id = query.from_user.id
    if not is_user_admin_in_group(context, group_id, admin_user_id):
        await query.edit_message_text(TRUST_NO_GROUP_PERMISSION_MESSAGE)
        return

    db = get_database()

    try:
        db.remove_trusted_user(user_id=target_user_id)
        _remove_trusted_cache(context, target_user_id)
        await query.edit_message_text(
            TRUST_REMOVED_MESSAGE.format(user_id=target_user_id),
            parse_mode="Markdown",
        )
    except ValueError:
        await query.edit_message_text(
            TRUST_USER_NOT_FOUND_MESSAGE.format(user_id=target_user_id),
            parse_mode="Markdown",
        )
