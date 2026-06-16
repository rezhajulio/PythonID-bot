"""Trusted-user command handlers for anti-spam bypass management.

Note on the trust unrestrict policy:
    Adding a user to the trusted list (via ``/trust`` or the Trust button in
    ``/check``) ALSO unrestricts that user in every monitored group as a side
    effect, including restrictions that may have been applied manually by
    other admins for unrelated reasons. Admins should be aware that trusting
    a user lifts any active restriction across all groups.
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
    TRUST_NO_PERMISSION_MESSAGE,
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
    trusted_ids = context.bot_data.get("trusted_user_ids")
    if trusted_ids is None:
        trusted_ids = set()
        context.bot_data["trusted_user_ids"] = trusted_ids
    trusted_ids.add(user_id)


def _remove_trusted_cache(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    trusted_ids = context.bot_data.get("trusted_user_ids")
    if trusted_ids is None:
        trusted_ids = set()
        context.bot_data["trusted_user_ids"] = trusted_ids
    trusted_ids.discard(user_id)


def _format_stored_user(full_name: str, user_id: int) -> str:
    """Return a markdown-safe display for a stored user.

    Uses the cached full_name from the DB. Falls back to ``User <id>``
    if the name is empty (e.g. trust granted via callback without name).
    """
    if full_name:
        return escape_markdown(full_name, version=1)
    return f"User {user_id}"


def _resolve_target_user_id(
    update: Update, args: list[str]
) -> tuple[int | None, str | None]:
    """Resolve the target user ID from CLI args or a forwarded message.

    Returns:
        tuple[int | None, str | None]: ``(user_id, None)`` on success, or
            ``(None, error_message)`` where ``error_message`` is a user-facing
            template from :mod:`bot.constants`.
    """
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
    bot: object,
    db: DatabaseService,
    registry: GroupRegistry,
    target_user_id: int,
    admin_user_id: int,
    target_user_full_name: str = "",
    target_username: str | None = None,
) -> tuple[int, int]:
    """Add a trusted user and apply cleanup side effects.

    Trust ALSO unrestricts the user in every monitored group as part of the
    cleanup loop. This intentionally lifts any active restriction — including
    restrictions previously applied manually by other admins for unrelated
    reasons.

    Returns:
        tuple[int, int]: (probation_clear_count, unrestrict_attempt_count).
            Both counts increment independently per group; a probation lookup
            failure does not prevent the unrestrict attempt for that group,
            and vice versa.
    """
    db.add_trusted_user(
        user_id=target_user_id,
        trusted_by_admin_id=admin_user_id,
        user_full_name=target_user_full_name,
        username=target_username,
    )

    cleared_probation = 0
    unrestricted_groups = 0
    for group_config in registry.all_groups():
        try:
            if db.get_new_user_probation(target_user_id, group_config.group_id):
                db.clear_new_user_probation(target_user_id, group_config.group_id)
                cleared_probation += 1
        except Exception:
            logger.warning(
                f"Probation cleanup failed for user {target_user_id} in group {group_config.group_id}",
                exc_info=True,
            )

        try:
            await unrestrict_user(bot, group_config.group_id, target_user_id)
            unrestricted_groups += 1
        except Exception:
            logger.warning(
                f"Unrestrict failed for user {target_user_id} in group {group_config.group_id}",
                exc_info=True,
            )

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
    """Handle /trust command in bot DM.

    Trusting a user ALSO unrestricts them in every monitored group, including
    restrictions that may have been applied manually by other admins.
    """
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

    # Resolve target user's display name
    target_full_name = ""
    target_username = None
    if update.message.forward_from:
        target_full_name = update.message.forward_from.full_name
        target_username = update.message.forward_from.username

    db = get_database()
    registry = get_group_registry()

    try:
        cleared_count, unrestricted_count = await trust_user(
            context.bot, db, registry, target_user_id, admin_user_id,
            target_user_full_name=target_full_name,
            target_username=target_username,
        )
        _add_trusted_cache(context, target_user_id)
        await update.message.reply_text(
            TRUST_ADDED_MESSAGE.format(
                user_id=target_user_id,
                probation_clear_count=cleared_count,
                unrestrict_count=unrestricted_count,
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
        await untrust_user(db, target_user_id)
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

        # Use stored name/username — no API calls
        user_display = _format_stored_user(record.user_full_name, record.user_id)
        if record.username:
            escaped = escape_markdown(record.username, version=1)
            user_display += f" (@{escaped})"

        trusted_lines.append(
            "• {user_display} (`{user_id}`) pada `{trusted_at}`".format(
                user_display=user_display,
                user_id=record.user_id,
                trusted_at=trusted_at_display,
            )
        )

    await update.message.reply_text(
        TRUST_LIST_HEADER.format(trusted_lines="\n".join(trusted_lines)),
        parse_mode="Markdown",
    )


async def handle_trust_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle trust callback button.

    Trusting a user ALSO unrestricts them in every monitored group, including
    restrictions that may have been applied manually by other admins.
    """
    query = update.callback_query
    if not query or not query.from_user or not query.data:
        return

    await query.answer()

    admin_user_id = query.from_user.id
    admin_ids = context.bot_data.get("admin_ids", [])
    if admin_user_id not in admin_ids:
        await query.edit_message_text(TRUST_NO_PERMISSION_MESSAGE)
        return

    try:
        target_user_id = int(query.data.split(":")[1])
    except (IndexError, ValueError):
        await query.edit_message_text(TRUST_CALLBACK_INVALID_MESSAGE)
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
    """Handle untrust callback button."""
    query = update.callback_query
    if not query or not query.from_user or not query.data:
        return

    await query.answer()

    admin_user_id = query.from_user.id
    admin_ids = context.bot_data.get("admin_ids", [])
    if admin_user_id not in admin_ids:
        await query.edit_message_text(TRUST_NO_PERMISSION_MESSAGE)
        return

    try:
        target_user_id = int(query.data.split(":")[1])
    except (IndexError, ValueError):
        await query.edit_message_text(TRUST_CALLBACK_INVALID_MESSAGE)
        return

    db = get_database()

    try:
        await untrust_user(db, target_user_id)
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
