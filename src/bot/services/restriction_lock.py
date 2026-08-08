"""Per-(group_id, user_id) asyncio locks for restriction transitions.

Telegram has a single physical restriction state per user per chat.
When multiple code paths (guest-bot handler, profile scheduler, DM
unrestriction, admin /verify) can restrict or unrestrict the same user
concurrently — especially when JobQueue jobs overlap with message
handlers — the DB restriction flags and Telegram's physical state can
diverge.

This module provides :func:`restriction_lock`, an async context manager
that serialises the Telegram API call + DB state transition for a given
``(group_id, user_id)`` pair. ``asyncio.Lock`` binds to the event loop of
its first *contended* acquire, so locks are scoped per running loop via a
:class:`weakref.WeakKeyDictionary` — this keeps a single-process bot's
locks alive for its one lifetime loop, while letting each test's fresh
event loop (see ``asyncio_default_fixture_loop_scope`` in pyproject.toml)
start with an empty lock table instead of reusing a lock bound to an
already-closed loop.
"""

import asyncio
import contextlib
import weakref
from collections.abc import AsyncIterator

_locks_by_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[tuple[int, int], asyncio.Lock]]" = (
    weakref.WeakKeyDictionary()
)


def _get_lock(group_id: int, user_id: int) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    per_loop = _locks_by_loop.get(loop)
    if per_loop is None:
        per_loop = {}
        _locks_by_loop[loop] = per_loop
    key = (group_id, user_id)
    lock = per_loop.get(key)
    if lock is None:
        lock = asyncio.Lock()
        per_loop[key] = lock
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
