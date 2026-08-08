"""Tests for the per-(group_id, user_id) restriction lock."""

import asyncio

from bot.services.restriction_lock import _locks_by_loop, restriction_lock


class TestRestrictionLock:
    async def test_serializes_concurrent_access(self):
        """Two concurrent acquisitions for the same key are serialized."""
        key = (-100, 42)
        order: list[str] = []

        async def task(label: str) -> None:
            async with restriction_lock(*key):
                order.append(f"{label}_enter")
                await asyncio.sleep(0.01)
                order.append(f"{label}_exit")

        await asyncio.gather(task("a"), task("b"))

        assert order == ["a_enter", "a_exit", "b_enter", "b_exit"]

    async def test_different_keys_run_concurrently(self):
        """Locks for different (group_id, user_id) pairs do not block each other."""
        order: list[str] = []

        async def task(group_id: int, user_id: int, label: str) -> None:
            async with restriction_lock(group_id, user_id):
                order.append(f"{label}_enter")
                await asyncio.sleep(0.01)
                order.append(f"{label}_exit")

        await asyncio.gather(
            task(-100, 1, "a"),
            task(-200, 2, "b"),
        )

        assert "a_enter" in order
        assert "b_enter" in order
        a_idx = order.index("a_enter")
        b_idx = order.index("b_enter")
        assert abs(a_idx - b_idx) <= 1

    async def test_lock_is_reused(self):
        """Same key returns the same lock object, scoped to the running loop."""
        key = (-300, 99)
        async with restriction_lock(*key):
            pass
        loop = asyncio.get_running_loop()
        assert key in _locks_by_loop[loop]
