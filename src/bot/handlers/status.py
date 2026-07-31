"""
Status command handler for the PythonID bot.

Provides a DM-only, admin-only ``/status`` command that shows bot
operational state scoped to the groups the caller actually administers:
uptime, per-group config summary (enforcement mode, captcha, disabled
plugins), per-group probation and captcha queue lengths, database file
size, and last job timestamps.
"""

from __future__ import annotations

import logging
import os
import time

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from telegram.helpers import escape_markdown

from bot.config import get_settings
from bot.database.service import get_database
from bot.group_config import get_group_registry
from bot.services.telegram_utils import get_admin_groups

logger = logging.getLogger(__name__)


def _format_uptime(seconds: float) -> str:
    """Format monotonic seconds into Xd Yh Zm."""
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def _format_filesize(path: str) -> str:
    """Return file size as KB or MB."""
    try:
        size = os.path.getsize(path)
    except FileNotFoundError:
        return "N/A"
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / 1024:.1f} KB"


async def _check_status_prereqs(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """Validate /status prerequisites: message exists, private chat, admin.

    Returns True if all checks pass. Sends error reply and returns False
    on any failure.
    """
    if not update.message or not update.message.from_user:
        logger.warning("handle_status called without message or sender")
        return False

    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_text(
            "❌ Perintah ini hanya bisa digunakan di chat pribadi dengan bot."
        )
        return False

    admin_user_id = update.message.from_user.id
    admin_ids = context.bot_data.get("admin_ids", [])
    if admin_user_id not in admin_ids:
        await update.message.reply_text(
            "❌ Kamu tidak memiliki izin untuk menggunakan perintah ini."
        )
        logger.warning(
            f"Non-admin user {admin_user_id} ({update.message.from_user.full_name}) "
            "attempted to use /status command"
        )
        return False

    return True


async def handle_status(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /status command in bot DM — show scoped operational state."""
    if not await _check_status_prereqs(update, context):
        return

    admin_user_id = update.message.from_user.id
    admin_group_ids = set(get_admin_groups(context, admin_user_id))

    lines: list[str] = []

    # --- Uptime ---
    start = context.bot_data.get("start_time")
    if start is not None:
        uptime = _format_uptime(time.monotonic() - start)
        lines.append(f"*Uptime:* {uptime}")
    else:
        lines.append("*Uptime:* N/A")

    # --- Per-group summary (scoped to caller's admin groups) ---
    lines.append("")
    lines.append("*Grup yang kamu admin:*")
    registry = get_group_registry()
    effective_map = context.bot_data.get("plugin_effective_map", {})
    db = get_database()

    all_probations = db.get_all_new_user_probations()
    all_pending = db.get_all_pending_captchas()

    shown_groups = 0
    for gc in registry.all_groups():
        if gc.group_id not in admin_group_ids:
            continue
        shown_groups += 1
        gid = gc.group_id
        enforcement = "Restriksi" if gc.restrict_failed_users else "Peringatan"
        captcha = "CAPTCHA" if gc.captcha_enabled else ""
        group_line = f"  • `{escape_markdown(str(gid), version=1)}` — _{enforcement}_"
        if captcha:
            group_line += f" _{captcha}_"

        # Per-group counts
        probation_count = sum(1 for p in all_probations if p.group_id == gid)
        pending_count = sum(1 for p in all_pending if p.group_id == gid)
        group_line += f"\n    Probation: {probation_count}, Captcha: {pending_count}"

        toggles = effective_map.get(gid, {})
        disabled = [k for k, v in toggles.items() if not v]
        if disabled:
            disabled_str = ", ".join(sorted(disabled))
            group_line += (
                f"\n    Plugin nonaktif: {escape_markdown(disabled_str, version=1)}"
            )
        lines.append(group_line)

    if shown_groups == 0:
        lines.append("  (Tidak ada grup yang dipantau)")

    # --- Database size ---
    lines.append("")
    db_path = get_settings().database_path
    size_str = _format_filesize(db_path)
    lines.append(f"*Database:* {size_str}")

    # --- Last jobs ---
    lines.append("")
    lines.append("*Jadwal terakhir:*")
    refresh_ts = context.bot_data.get("last_admin_refresh")
    if refresh_ts is not None:
        lines.append(
            "  • Refresh admin: "
            f"{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(refresh_ts))}"
        )
    else:
        lines.append("  • Refresh admin: belum pernah")

    restrict_ts = context.bot_data.get("last_auto_restrict")
    if restrict_ts is not None:
        lines.append(
            "  • Auto-restrict: "
            f"{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(restrict_ts))}"
        )
    else:
        lines.append("  • Auto-restrict: belum pernah")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
    )


def get_handlers() -> list[CommandHandler]:
    """Return list of handlers for the status command."""
    return [CommandHandler("status", handle_status)]
