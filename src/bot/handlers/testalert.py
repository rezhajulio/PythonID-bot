"""DM admin command: /testalert — verify AI-spam alert delivery.

Sends a clearly-marked test message to the configured
``ai_spam_alert_chat_id`` of the caller's admin groups (or one group
given as an argument), then reports per-group success/failure back in
the DM. Lets an admin confirm the alert chat id is correct and the bot
can actually send there, without waiting for real spam.
"""

from __future__ import annotations

import logging

from bot.dispatch import (
    AppState,
    HandlerContext,
    command_filter,
    effective_chat,
    HandlerSpec,
)
from bot.group_config import get_group_registry
from bot.services.telegram_utils import get_admin_groups

logger = logging.getLogger(__name__)

TEST_ALERT_TEXT = (
    "🧪 *Test Alert* — pesan uji dari /testalert.\n\n"
    "Kalau kamu membaca ini, `ai_spam_alert_chat_id` untuk grup `{group_id}` "
    "sudah benar dan bot bisa mengirim pesan ke sini."
)


async def _check_testalert_prereqs(update, context: HandlerContext) -> bool:
    """Validate /testalert prerequisites: message exists, private chat, admin."""
    if not update.message or not update.message.from_user:
        logger.warning("handle_testalert called without message or sender")
        return False

    chat = effective_chat(update)
    if chat and chat.type != "private":
        await update.message.reply(
            "❌ Perintah ini hanya bisa digunakan di chat pribadi dengan bot."
        )
        return False

    admin_user_id = update.message.from_user.id
    if admin_user_id not in context.state.admin_ids:
        await update.message.reply(
            "❌ Kamu tidak memiliki izin untuk menggunakan perintah ini."
        )
        logger.warning(
            "Non-admin user %s attempted /testalert", admin_user_id
        )
        return False
    return True


async def handle_testalert_command(update, context: HandlerContext) -> None:
    """Handle /testalert [group_id] in bot DM — test AI-spam alert delivery."""
    if not await _check_testalert_prereqs(update, context):
        return

    admin_user_id = update.message.from_user.id
    admin_group_ids = set(get_admin_groups(context, admin_user_id))

    args = context.args or []
    if args:
        try:
            wanted = int(args[0])
        except (ValueError, TypeError):
            await update.message.reply(
                "❌ Format: `/testalert [group_id]` — contoh: `/testalert -1001052242766`."
            )
            return
        if wanted not in admin_group_ids:
            await update.message.reply(
                "❌ Kamu bukan admin grup itu atau grup tidak dikenal."
            )
            return
        target_groups = [wanted]
    else:
        target_groups = sorted(admin_group_ids)

    if not target_groups:
        await update.message.reply("❌ Kamu tidak menjadi admin di grup mana pun.")
        return

    registry = get_group_registry()
    lines: list[str] = []
    for group_id in target_groups:
        group_config = registry.get(group_id)
        alert_chat_id = (
            group_config.ai_spam_alert_chat_id if group_config else None
        )
        if alert_chat_id is None:
            lines.append(
                f"❌ `{group_id}`: `ai_spam_alert_chat_id` belum dikonfigurasi."
            )
            logger.warning(
                "testalert: no alert chat configured for group=%s", group_id
            )
            continue
        try:
            await context.bot.send_message(
                chat_id=alert_chat_id,
                text=TEST_ALERT_TEXT.format(group_id=group_id),
                parse_mode="Markdown",
            )
        except Exception as e:
            lines.append(
                f"❌ `{group_id}`: gagal kirim ke `{alert_chat_id}`: {e}"
            )
            logger.error(
                "testalert: failed to send test alert to chat_id=%s "
                "for group=%s",
                alert_chat_id,
                group_id,
                exc_info=True,
            )
        else:
            lines.append(
                f"✅ `{group_id}`: terkirim ke `{alert_chat_id}`."
            )
            logger.info(
                "testalert: test alert sent to chat_id=%s for group=%s",
                alert_chat_id,
                group_id,
            )

    await update.message.reply("\n".join(lines), parse_mode="Markdown")


def get_handlers(state: AppState) -> list[HandlerSpec]:
    """Return list of handler specs for the testalert command."""
    return [
        HandlerSpec(
            plugin_name="testalert",
            group=0,
            update_kinds=("message", "edited_message"),
            check=command_filter("testalert", state),
            callback=handle_testalert_command,
            label="testalert_command",
            command="testalert",
        )
    ]
