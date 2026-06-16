"""Backfill user_full_name/username and admin names for existing trusted users.

Run once after deploying the cache-trusted-user-names feature.
Fetches names from Telegram API and updates the DB.

Usage: uv run python scripts/backfill_trusted_names.py
"""

import asyncio
import logging

from telegram import Bot

from bot.config import get_settings
from bot.database.service import get_database, init_database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    settings = get_settings()
    init_database(settings.database_path)
    db = get_database()
    bot = Bot(token=settings.telegram_bot_token)

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
            # Fetch target user name
            user_full_name = record.user_full_name
            username = record.username
            if not user_full_name:
                try:
                    chat = await bot.get_chat(record.user_id)
                    user_full_name = chat.full_name or ""
                    username = chat.username
                    logger.info(f"  ✓ user_id={record.user_id}: {user_full_name}")
                except Exception as e:
                    user_full_name = f"User {record.user_id}"
                    logger.warning(f"  ✗ user_id={record.user_id}: {e}")

            # Fetch admin name
            admin_full_name = record.admin_full_name
            admin_username = record.admin_username
            if not admin_full_name:
                try:
                    chat = await bot.get_chat(record.trusted_by_admin_id)
                    admin_full_name = chat.full_name or ""
                    admin_username = chat.username
                    logger.info(f"  ✓ admin_id={record.trusted_by_admin_id}: {admin_full_name}")
                except Exception as e:
                    admin_full_name = f"User {record.trusted_by_admin_id}"
                    logger.warning(f"  ✗ admin_id={record.trusted_by_admin_id}: {e}")

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
