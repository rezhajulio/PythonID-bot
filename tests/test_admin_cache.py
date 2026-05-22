"""Tests for bot.services.admin_cache module.

Verifies that refresh_admin_ids is importable from the new location
and behaves correctly.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.group_config import GroupConfig, GroupRegistry


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
                mock_fetch.side_effect = Exception("API error")
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

        with patch("bot.services.admin_cache.refresh_admin_ids"):
            import importlib
            importlib.reload(jobs_mod)

            app = MagicMock()
            app.job_queue = MagicMock()
            app.job_queue.run_repeating = MagicMock()
            app.bot_data = {}
            app.add_handler = MagicMock()

            jobs_mod.register_refresh_admin_ids_job(app)
            app.job_queue.run_repeating.assert_called_once()