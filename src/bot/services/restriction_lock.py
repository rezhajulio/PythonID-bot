"""Per-(group_id, user_id) asyncio locks for restriction transitions.

Telegram has a single physical restriction state per user per chat.
When multiple code paths (guest-bot handler, profile scheduler, DM
unrestriction, admin /verify) can restrict or unrestrict the same user
concurrently — especially when JobQueue jobs overlap with message
handlers — the DB restriction flags and Telegram's physical state can
diverge.

This module provides :func:`restriction_lock`, an async context manager
that serialises the Telegram API call + DB state transition for a given
``(group_id, user_id)`` pair. Locks are created on demand and stored in
a module-level dict; they persist for the process lifetime, which is
fine for a single-process bot.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator

_locks: dict[tuple[int, int], asyncio.Lock] = {}


def _get_lock(group_id: int, user_id: int) -> asyncio.Lock:
    key = (group_id, user_id)
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


@contextlib.asynccontextmanager
async def restriction_lock(group_id: int, user_id: int) -> AsyncIterator[None]:
    """Acquire the per-(group_id, user_id) restriction transition lock.

    Usage::

        async with restriction_lock(group_id, user_id):
            await bot.restrict_chat_member(...)
            db.mark_user_restricted(...)
    """
    lock = _get_lock(group_id, user_id)
    async with lock:
        yield
