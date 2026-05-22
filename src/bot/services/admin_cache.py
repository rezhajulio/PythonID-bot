"""Admin ID cache management for the PythonID bot.

Provides ``refresh_admin_ids`` for periodic refresh of group admin rosters
in ``bot_data``.  Extracted from ``main.py`` to break the circular import
between ``main.py`` and ``jobs.py``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bot.group_config import get_group_registry
from bot.services.telegram_utils import fetch_group_admin_ids

if TYPE_CHECKING:
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def refresh_admin_ids(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Periodically refresh cached admin IDs for all monitored groups.

    Called by JobQueue every 10 minutes to keep admin rosters up to date
    when promotions/demotions happen after startup.
    """
    registry = get_group_registry()
    group_admin_ids: dict[int, list[int]] = {}
    all_admin_ids: set[int] = set()

    for gc in registry.all_groups():
        try:
            ids = await fetch_group_admin_ids(context.bot, gc.group_id)
            group_admin_ids[gc.group_id] = ids
            all_admin_ids.update(ids)
        except Exception as e:
            logger.error(f"Failed to refresh admin IDs for group {gc.group_id}: {e}")
            existing = context.bot_data.get("group_admin_ids", {}).get(gc.group_id, [])
            group_admin_ids[gc.group_id] = existing
            all_admin_ids.update(existing)

    context.bot_data["group_admin_ids"] = group_admin_ids
    context.bot_data["admin_ids"] = list(all_admin_ids)
    logger.info(f"Refreshed admin IDs: {len(all_admin_ids)} unique admin(s) across {len(group_admin_ids)} group(s)")