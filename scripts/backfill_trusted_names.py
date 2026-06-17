"""Backfill user_full_name/username and admin names for existing trusted users.

Run once after deploying the cache-trusted-user-names feature.
Fetches names from Telegram API and updates the DB.

Usage: uv run python scripts/backfill_trusted_names.py
"""

import asyncio
import logging
import re

from telegram import Bot

from bot.config import get_settings
from bot.database.service import get_database, init_database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _fetch_name(bot: Bot, tg_id: int) -> tuple[str, str | None]:
    """Fetch display name + username from Telegram. Returns ``("", None)`` on error.

    The display layer (``_format_person`` in ``bot/handlers/trust.py``) already
    has a ``User <id>`` fallback for empty names, so we leave the column empty
    on API error and let the display layer handle it. This keeps the DB clean,
    avoids colliding with real users named ``User 12345``, and lets a re-run of
    this script retry the failed lookups.
    """
    try:
        chat = await bot.get_chat(tg_id)
    except Exception as e:
        logger.warning(f"  ✗ id={tg_id}: {e}")
        return "", None
    return chat.full_name or "", chat.username


async def main():
    settings = get_settings()
    init_database(settings.database_path)
    db = get_database()
    bot = Bot(token=settings.telegram_bot_token)

    users = db.get_trusted_users()

    # Clean up legacy "User <id>" placeholder rows written by commit 6499f63's
    # backfill (the previous version assigned f"User <record.user_id}" to
    # user_full_name inside the except branch). Those rows are non-empty, so
    # the new filter below would skip them forever and /trusted would keep
    # rendering the placeholder as a real name. ponytail: one-shot cleanup;
    # remove when no production rows with the placeholder remain.
    cleaned = 0
    for u in users:
        if u.user_full_name and re.match(r"^User \d+$", u.user_full_name):
            try:
                db.update_trusted_user_names(
                    user_id=u.user_id, user_full_name="", username=None
                )
                logger.warning(
                    f"Legacy placeholder cleared: user_id={u.user_id} "
                    f"matched={u.user_full_name!r}"
                )
                cleaned += 1
            except Exception as e:
                logger.warning(f"  ✗ cleanup failed for user_id={u.user_id}: {e}")
    if cleaned:
        logger.warning(f"Cleared {cleaned} legacy placeholder row(s) before backfill.")
        users = db.get_trusted_users()

    to_backfill = [
        u for u in users
        if not u.user_full_name or not u.admin_full_name
    ]

    if not to_backfill:
        logger.info("All trusted users already have names. Nothing to do.")
        return

    logger.info(f"Backfilling {len(to_backfill)} trusted user(s)...")

    async with bot:
        for record in to_backfill:
            user_full_name = record.user_full_name
            username = record.username
            if not user_full_name:
                user_full_name, fetched_username = await _fetch_name(bot, record.user_id)
                if fetched_username is not None:
                    username = fetched_username
                if user_full_name:
                    logger.info(f"  ✓ user_id={record.user_id}: {user_full_name}")

            admin_full_name = record.admin_full_name
            admin_username = record.admin_username
            if not admin_full_name:
                admin_full_name, fetched_username = await _fetch_name(bot, record.trusted_by_admin_id)
                if fetched_username is not None:
                    admin_username = fetched_username
                if admin_full_name:
                    logger.info(f"  ✓ admin_id={record.trusted_by_admin_id}: {admin_full_name}")

            db.update_trusted_user_names(
                user_id=record.user_id,
                user_full_name=user_full_name,
                username=username,
                admin_full_name=admin_full_name,
                admin_username=admin_username,
            )

    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
