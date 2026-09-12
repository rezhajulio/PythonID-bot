"""Admin ID cache management for the PythonID bot.

Provides ``refresh_admin_ids`` for periodic refresh of group admin rosters
and ``preload_admin_ids`` for startup cache loading with fallback.
Both extracted from ``main.py`` to break the circular import
between ``main.py`` and ``jobs.py``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError
from telegram.error import TelegramError

from bot.config import get_settings
from bot.group_config import get_group_registry
from bot.services.telegram_utils import TelegramAdminFetchError, fetch_group_admin_ids

if TYPE_CHECKING:
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

CACHE_FILE_PATH: Path | None = None
"""Test/override hook. When None the path is derived from settings at call time."""


def _cache_file_path() -> Path:
    """Resolve the admin cache path, preferring the configured database directory.

    Resolved per call rather than at import, so importing this module never
    requires a fully populated environment and so a DATABASE_PATH change is
    honoured. Tests override ``CACHE_FILE_PATH``.
    """
    if CACHE_FILE_PATH is not None:
        return CACHE_FILE_PATH
    try:
        database_path = get_settings().database_path
    except ValidationError:
        # Settings unavailable (e.g. imported by tooling without env vars).
        logger.debug("Settings unavailable; using default admin cache path")
        return Path("data/admin_cache.json")

    # An in-memory database has no directory, and a bare filename would put the
    # cache in the working directory; both keep the conventional data/ location.
    if database_path == ":memory:":
        return Path("data/admin_cache.json")
    parent = Path(database_path).parent
    if parent == Path("."):
        return Path("data/admin_cache.json")
    return parent / "admin_cache.json"


# Network/API errors the fetch path can recover from by falling back to cache.
# TelegramError covers all PTB errors (TimedOut, NetworkError, RetryAfter, ...)
# while still letting programming errors propagate.
FETCH_ERRORS = (TelegramAdminFetchError, TelegramError)


def _load_admin_cache() -> dict[int, list[int]]:
    """Load the persisted admin cache, skipping entries that are malformed.

    A single bad entry is dropped rather than discarding the whole file, so a
    partially corrupt cache still yields the rosters that are readable.
    """
    path = _cache_file_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        logger.error(f"Failed to load admin cache from disk: {e}", exc_info=True)
        return {}

    if not isinstance(data, dict):
        logger.error(
            f"Ignoring admin cache with unexpected top-level type: {type(data).__name__}"
        )
        return {}

    cache: dict[int, list[int]] = {}
    for key, value in data.items():
        try:
            if not isinstance(value, list):
                raise TypeError(f"expected list, got {type(value).__name__}")
            cache[int(key)] = [int(uid) for uid in value]
        except (TypeError, ValueError) as e:
            logger.error(f"Skipping malformed admin cache entry {key!r}: {e}")
    return cache


def _save_admin_cache(cache: dict[int, list[int]]) -> None:
    try:
        path = _cache_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        temp_path.replace(path)
    except OSError as e:
        logger.error(f"Failed to save admin cache to disk: {e}", exc_info=True)


async def _fetch_single(
    bot, group_id: int
) -> tuple[int, list[int] | None, Exception | None]:
    try:
        ids = await fetch_group_admin_ids(bot, group_id)
        return group_id, ids, None
    except FETCH_ERRORS as e:
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
    old_cache: dict[int, list[int]] = dict(
        context.bot_data.get("group_admin_ids", {})
    )

    # Disk is the fallback for groups that are missing from bot_data, which
    # happens on a cold start and after a cycle where every fetch failed.
    if not old_cache:
        old_cache = await asyncio.to_thread(_load_admin_cache)

    group_admin_ids: dict[int, list[int]] = dict(old_cache) if seed_existing else {}
    fetched_any = False

    tasks = [_fetch_single(context.bot, gc.group_id) for gc in registry.all_groups()]

    if tasks:
        results = await asyncio.gather(*tasks)
        for group_id, ids, error in results:
            if error is None and ids is not None:
                group_admin_ids[group_id] = ids
                fetched_any = True
            else:
                # Only recoverable errors reach this branch; programming
                # errors propagate out of _fetch_single with their traceback.
                logger.error(
                    f"Failed to fetch admin IDs for group {group_id}: {error}"
                )
                group_admin_ids[group_id] = old_cache.get(group_id, [])

    # Derived from the final map so groups seeded from cache stay visible to
    # admin_ids consumers, which previously saw only freshly fetched groups.
    all_admin_ids = {
        admin_id for ids in group_admin_ids.values() for admin_id in ids
    }

    context.bot_data["group_admin_ids"] = group_admin_ids
    context.bot_data["admin_ids"] = list(all_admin_ids)

    # Never persist a result built without a single successful fetch: doing so
    # would overwrite a good roster on disk with fallback or empty data.
    if fetched_any:
        await asyncio.to_thread(_save_admin_cache, group_admin_ids)


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
