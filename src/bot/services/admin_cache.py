"""Admin ID cache management for the PythonID bot.

Provides ``refresh_admin_ids`` for periodic refresh of group admin rosters
and ``preload_admin_ids`` for startup cache loading with fallback.
Both extracted from ``main.py`` to break the circular import
between ``main.py`` and ``jobs.py``.
"""

from __future__ import annotations

import logging
import time
import json
import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from bot.group_config import get_group_registry
from bot.services.telegram_utils import fetch_group_admin_ids

if TYPE_CHECKING:
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

CACHE_FILE_PATH = Path("data/admin_cache.json")


def _load_admin_cache() -> dict[int, list[int]]:
    if not CACHE_FILE_PATH.exists():
        return {}
    try:
        with open(CACHE_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {int(k): v for k, v in data.items()}
    except Exception as e:
        logger.error(f"Failed to load admin cache from disk: {e}")
        return {}


def _save_admin_cache(cache: dict[int, list[int]]) -> None:
    try:
        CACHE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_path = CACHE_FILE_PATH.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        temp_path.replace(CACHE_FILE_PATH)
    except Exception as e:
        logger.error(f"Failed to save admin cache to disk: {e}")


async def _fetch_single(
    bot, group_id: int
) -> tuple[int, list[int] | None, Exception | None]:
    try:
        ids = await fetch_group_admin_ids(bot, group_id)
        return group_id, ids, None
    except Exception as e:
        return group_id, None, e


async def _sync_admin_ids(
    context: ContextTypes.DEFAULT_TYPE, *, seed_existing: bool
) -> None:
    """
    Sync admin IDs for all monitored groups with fallback to cached data.

    Args:
        context: Bot context.
        seed_existing: If True, seed the dict from existing bot_data cache;
                      if False, start with an empty dict.
    """
    registry = get_group_registry()
    old_cache: dict[int, list[int]] = context.bot_data.get("group_admin_ids", {})

    if seed_existing and not old_cache:
        old_cache = _load_admin_cache()

    group_admin_ids: dict[int, list[int]] = dict(old_cache) if seed_existing else {}
    all_admin_ids: set[int] = set()

    tasks = [_fetch_single(context.bot, gc.group_id) for gc in registry.all_groups()]

    if tasks:
        results = await asyncio.gather(*tasks)
        for group_id, ids, error in results:
            if error is None and ids is not None:
                group_admin_ids[group_id] = ids
                all_admin_ids.update(ids)
            else:
                logger.error(f"Failed to fetch admin IDs for group {group_id}: {error}")
                existing = old_cache.get(group_id, [])
                group_admin_ids[group_id] = existing
                all_admin_ids.update(existing)

    context.bot_data["group_admin_ids"] = group_admin_ids
    context.bot_data["admin_ids"] = list(all_admin_ids)

    _save_admin_cache(group_admin_ids)


async def refresh_admin_ids(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Periodically refresh cached admin IDs for all monitored groups.

    Called by JobQueue every 10 minutes to keep admin rosters up to date
    when promotions/demotions happen after startup.
    """
    await _sync_admin_ids(context, seed_existing=False)
    group_admin_ids = context.bot_data.get("group_admin_ids", {})
    all_admin_ids = context.bot_data.get("admin_ids", [])
    logger.info(
        f"Refreshed admin IDs: {len(all_admin_ids)} unique admin(s) across {len(group_admin_ids)} group(s)"
    )
    context.bot_data["last_admin_refresh"] = time.time()


async def preload_admin_ids(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Preload admin IDs at startup with fallback to existing cache.

    Unlike ``refresh_admin_ids`` which builds from scratch each cycle,
    this function preserves existing cached data for groups that fail
    to fetch.  Used in ``post_init`` to prevent wiping admin cache on
    startup failures.
    """
    await _sync_admin_ids(context, seed_existing=True)
    group_admin_ids = context.bot_data.get("group_admin_ids", {})
    all_admin_ids = context.bot_data.get("admin_ids", [])
    logger.info(
        f"Preloaded admin IDs: {len(all_admin_ids)} unique admin(s) "
        f"across {len(group_admin_ids)} group(s)"
    )
