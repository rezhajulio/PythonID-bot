"""
Status command handler for the PythonID bot.

Provides a DM-only, admin-only ``/status`` command that shows bot
operational state: uptime, per-group config summary, probation and
captcha queue lengths, database file size, and last job timestamps.
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
    """Handle /status command in bot DM — show operational state."""
    if not await _check_status_prereqs(update, context):
        return

    lines: list[str] = []

    # --- Uptime ---
    start = context.bot_data.get("start_time")
    if start is not None:
        uptime = _format_uptime(time.monotonic() - start)
        lines.append(f"*Uptime:* {uptime}")
    else:
        lines.append("*Uptime:* N/A")

    # --- Per-group summary ---
    lines.append("")
    lines.append("*Groups:*")
    registry = get_group_registry()
    effective_map = context.bot_data.get("plugin_effective_map", {})
    for gc in registry.all_groups():
        gid = gc.group_id
        # group_titles not cached in bot_data yet — fallback to group_id
        title = context.bot_data.get("group_titles", {}).get(gid, str(gid))
        captcha = "CAPTCHA" if gc.captcha_enabled else ""
        group_line = (
            f"  • `{escape_markdown(str(gid), version=1)}`"
            f" — {escape_markdown(title, version=1)}"
        )
        if captcha:
            group_line += f" _{captcha}_"
        toggles = effective_map.get(gid, {})
        disabled = [k for k, v in toggles.items() if not v]
        if disabled:
            disabled_str = ", ".join(sorted(disabled))
            group_line += (
                f"\n    plugins off: {escape_markdown(disabled_str, version=1)}"
            )
        lines.append(group_line)

    # --- Probation count ---
    lines.append("")
    db = get_database()
    probation_records = db.get_all_new_user_probations()
    lines.append(f"*Probation:* {len(probation_records)} user(s)")

    # --- Pending captcha count ---
    pending = db.get_all_pending_captchas()
    lines.append(f"*Captcha:* {len(pending)} pending")

    # --- Database size ---
    db_path = get_settings().database_path
    size_str = _format_filesize(db_path)
    lines.append(f"*Database:* {size_str}")

    # --- Last jobs ---
    lines.append("")
    lines.append("*Last jobs:*")
    refresh_ts = context.bot_data.get("last_admin_refresh")
    if refresh_ts is not None:
        lines.append(
            "  • admin refresh: "
            f"{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(refresh_ts))}"
        )
    else:
        lines.append("  • admin refresh: never")

    restrict_ts = context.bot_data.get("last_auto_restrict")
    if restrict_ts is not None:
        lines.append(
            "  • auto restrict: "
            f"{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(restrict_ts))}"
        )
    else:
        lines.append("  • auto restrict: never")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
    )


def get_handlers() -> list[CommandHandler]:
    """Return list of handlers for the status command."""
    return [CommandHandler("status", handle_status)]
