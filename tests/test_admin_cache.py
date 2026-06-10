"""Tests for bot.services.admin_cache module.

Verifies that refresh_admin_ids and preload_admin_ids are importable
from the new location and behave correctly.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.group_config import GroupConfig, GroupRegistry
from bot.services.telegram_utils import TelegramAdminFetchError

@pytest.fixture
def mock_registry():
    """Create GroupRegistry with a test group."""
    registry = GroupRegistry()
    registry.register(GroupConfig(
        group_id=-1001234567890,
        warning_topic_id=42,
    ))
    return registry

class TestRefreshAdminIds:
    """refresh_admin_ids: fetch admin IDs for all groups, cache in bot_data."""

    async def test_refresh_admin_ids_importable_from_admin_cache(self):
        """refresh_admin_ids is importable from bot.services.admin_cache."""
        from bot.services.admin_cache import refresh_admin_ids
        assert callable(refresh_admin_ids)

    async def test_refresh_admin_ids_fetches_and_caches(self, mock_registry):
        """refresh_admin_ids fetches admins and stores in bot_data."""
        from bot.services.admin_cache import refresh_admin_ids

        bot = AsyncMock()
        bot.get_chat_administrators.return_value = [
            MagicMock(user=MagicMock(id=111)),
            MagicMock(user=MagicMock(id=222)),
        ]

        context = MagicMock()
        context.bot = bot
        context.bot_data = {}

        with patch("bot.services.admin_cache.get_group_registry", return_value=mock_registry):
            with patch("bot.services.admin_cache.fetch_group_admin_ids") as mock_fetch:
                mock_fetch.return_value = [111, 222]
                await refresh_admin_ids(context)

        assert "group_admin_ids" in context.bot_data
        assert "admin_ids" in context.bot_data
        assert context.bot_data["group_admin_ids"][-1001234567890] == [111, 222]
        assert 111 in context.bot_data["admin_ids"]
        assert 222 in context.bot_data["admin_ids"]

    async def test_refresh_admin_ids_multiple_groups(self):
        """refresh_admin_ids fetches admins for all groups in registry."""
        from bot.services.admin_cache import refresh_admin_ids

        registry = GroupRegistry()
        registry.register(GroupConfig(group_id=-100111, warning_topic_id=1))
        registry.register(GroupConfig(group_id=-100222, warning_topic_id=2))

        bot = AsyncMock()
        context = MagicMock()
        context.bot = bot
        context.bot_data = {"group_admin_ids": {}, "admin_ids": []}

        with patch("bot.services.admin_cache.get_group_registry", return_value=registry):
            with patch("bot.services.admin_cache.fetch_group_admin_ids") as mock_fetch:
                def side_effect(bot, gid):
                    if gid == -100111:
                        return [111]
                    return [222]
                mock_fetch.side_effect = side_effect
                await refresh_admin_ids(context)

        assert -100111 in context.bot_data["group_admin_ids"]
        assert -100222 in context.bot_data["group_admin_ids"]
        assert context.bot_data["group_admin_ids"][-100111] == [111]
        assert context.bot_data["group_admin_ids"][-100222] == [222]
        assert set(context.bot_data["admin_ids"]) == {111, 222}

    async def test_refresh_admin_ids_fallback_on_error(self, mock_registry):
        """On fetch error, fallback to existing cached data."""
        from bot.services.admin_cache import refresh_admin_ids

        context = MagicMock()
        context.bot = AsyncMock()
        context.bot_data = {
            "group_admin_ids": {-1001234567890: [999]},
            "admin_ids": [999],
        }

        with patch("bot.services.admin_cache.get_group_registry", return_value=mock_registry):
            with patch("bot.services.admin_cache.fetch_group_admin_ids") as mock_fetch:
                mock_fetch.side_effect = TelegramAdminFetchError("API error")
                await refresh_admin_ids(context)

        assert context.bot_data["group_admin_ids"][-1001234567890] == [999]
        assert context.bot_data["admin_ids"] == [999]

    async def test_refresh_admin_ids_not_importable_from_main(self):
        """refresh_admin_ids is NOT defined in main.py anymore."""
        import bot.main as main_mod
        assert not hasattr(main_mod, "refresh_admin_ids")

    async def test_jobs_imports_from_admin_cache(self):
        """jobs.py imports refresh_admin_ids from bot.services.admin_cache."""
        import bot.plugins.builtin.jobs as jobs_mod
        import bot.services.admin_cache as admin_cache_mod

        # Verify the import source directly (no reload needed)
        assert jobs_mod.refresh_admin_ids is admin_cache_mod.refresh_admin_ids

class TestPreloadAdminIds:
    """preload_admin_ids: startup cache with fallback to existing data."""

    async def test_preload_admin_ids_all_succeed(self):
        """preload_admin_ids updates all groups when all fetches succeed."""
        from bot.services.admin_cache import preload_admin_ids

        registry = GroupRegistry()
        registry.register(GroupConfig(group_id=-1001, warning_topic_id=1))
        registry.register(GroupConfig(group_id=-1002, warning_topic_id=2))

        mock_bot = AsyncMock()
        mock_context = MagicMock()
        mock_context.bot = mock_bot
        mock_context.bot_data = {
            "group_admin_ids": {-1001: [111], -1002: [333]},
            "admin_ids": [111, 333],
        }

        with patch("bot.services.admin_cache.get_group_registry", return_value=registry), \
             patch("bot.services.admin_cache.fetch_group_admin_ids") as mock_fetch:
            mock_fetch.side_effect = [
                [555, 666],   # -1001 success
                [777],        # -1002 success
            ]
            await preload_admin_ids(mock_context)

        assert mock_context.bot_data["group_admin_ids"][-1001] == [555, 666]
        assert mock_context.bot_data["group_admin_ids"][-1002] == [777]
        assert set(mock_context.bot_data["admin_ids"]) == {555, 666, 777}

    async def test_preload_admin_ids_preserves_cache_on_failure(self):
        """On fetch failure, preserve existing cached data for that group."""
        from bot.services.admin_cache import preload_admin_ids

        registry = GroupRegistry()
        registry.register(GroupConfig(group_id=-1001, warning_topic_id=1))
        registry.register(GroupConfig(group_id=-1002, warning_topic_id=2))

        mock_bot = AsyncMock()
        mock_context = MagicMock()
        mock_context.bot = mock_bot
        mock_context.bot_data = {
            "group_admin_ids": {-1001: [111, 222], -1002: [333]},
            "admin_ids": [111, 222, 333],
        }

        with patch("bot.services.admin_cache.get_group_registry", return_value=registry), \
             patch("bot.services.admin_cache.fetch_group_admin_ids") as mock_fetch:
            # First group succeeds, second fails
            mock_fetch.side_effect = [
                [444, 555],                     # -1001 success
                TelegramAdminFetchError("API error"),  # -1002 failure
            ]
            await preload_admin_ids(mock_context)

        # -1001 updated with new data
        assert mock_context.bot_data["group_admin_ids"][-1001] == [444, 555]
        # -1002 preserved from existing cache (not empty list)
        assert mock_context.bot_data["group_admin_ids"][-1002] == [333]
        # admin_ids includes both new (-1001) and preserved (-1002)
        assert set(mock_context.bot_data["admin_ids"]) == {333, 444, 555}

    async def test_preload_admin_ids_no_existing_cache(self):
        """On failure with no existing cache, store empty list."""
        from bot.services.admin_cache import preload_admin_ids

        registry = GroupRegistry()
        registry.register(GroupConfig(group_id=-1001, warning_topic_id=1))

        mock_bot = AsyncMock()
        mock_context = MagicMock()
        mock_context.bot = mock_bot
        mock_context.bot_data = {}

        with patch("bot.services.admin_cache.get_group_registry", return_value=registry), \
             patch("bot.services.admin_cache.fetch_group_admin_ids") as mock_fetch:
            mock_fetch.side_effect = TelegramAdminFetchError("API error")
            await preload_admin_ids(mock_context)

        assert mock_context.bot_data["group_admin_ids"][-1001] == []
        assert mock_context.bot_data["admin_ids"] == []
