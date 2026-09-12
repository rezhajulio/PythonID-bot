"""Tests for bot.services.admin_cache module.

Verifies that refresh_admin_ids and preload_admin_ids are importable
from the new location and behave correctly.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.group_config import GroupConfig, GroupRegistry
from bot.services.telegram_utils import TelegramAdminFetchError


@pytest.fixture(autouse=True)
def mock_disk_cache(request):
    """Stub disk I/O for tests that are not about the disk layer itself.

    TestDiskCache exercises the real functions against a tmp_path and so
    opts out.
    """
    if request.cls is not None and request.cls.__name__ == "TestDiskCache":
        yield None, None
        return
    with (
        patch("bot.services.admin_cache._save_admin_cache") as mock_save,
        patch(
            "bot.services.admin_cache._load_admin_cache", return_value={}
        ) as mock_load,
    ):
        yield mock_save, mock_load


@pytest.fixture
def mock_registry():
    """Create GroupRegistry with a test group."""
    registry = GroupRegistry()
    registry.register(
        GroupConfig(
            group_id=-1001234567890,
            warning_topic_id=42,
        )
    )
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

        with patch(
            "bot.services.admin_cache.get_group_registry", return_value=mock_registry
        ):
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

        with patch(
            "bot.services.admin_cache.get_group_registry", return_value=registry
        ):
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

        with patch(
            "bot.services.admin_cache.get_group_registry", return_value=mock_registry
        ):
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

        with (
            patch("bot.services.admin_cache.get_group_registry", return_value=registry),
            patch("bot.services.admin_cache.fetch_group_admin_ids") as mock_fetch,
        ):
            mock_fetch.side_effect = [
                [555, 666],  # -1001 success
                [777],  # -1002 success
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

        with (
            patch("bot.services.admin_cache.get_group_registry", return_value=registry),
            patch("bot.services.admin_cache.fetch_group_admin_ids") as mock_fetch,
        ):
            # First group succeeds, second fails
            mock_fetch.side_effect = [
                [444, 555],  # -1001 success
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

        with (
            patch("bot.services.admin_cache.get_group_registry", return_value=registry),
            patch("bot.services.admin_cache.fetch_group_admin_ids") as mock_fetch,
        ):
            mock_fetch.side_effect = TelegramAdminFetchError("API error")
            await preload_admin_ids(mock_context)

        assert mock_context.bot_data["group_admin_ids"][-1001] == []
        assert mock_context.bot_data["admin_ids"] == []


class TestDiskCache:
    """The on-disk cache: round-trip, malformed input, and save guarding."""

    def test_round_trips_int_keys_and_values(self, tmp_path):
        """Keys survive the JSON stringify/parse cycle as ints."""
        from bot.services import admin_cache

        target = tmp_path / "admin_cache.json"
        with patch.object(admin_cache, "CACHE_FILE_PATH", target):
            admin_cache._save_admin_cache({-1001: [11, 22], -1002: []})
            assert admin_cache._load_admin_cache() == {-1001: [11, 22], -1002: []}
        # Temp file is renamed onto the target, not left behind.
        assert not (tmp_path / "admin_cache.tmp").exists()

    def test_skips_malformed_entries_without_dropping_good_ones(self, tmp_path):
        """One bad entry must not discard the rest of the cache."""
        from bot.services import admin_cache

        target = tmp_path / "admin_cache.json"
        target.write_text(
            '{"-1001": [111], "-1002": "not-a-list", "-bad": [1], "-1003": ["222", 333]}'
        )
        with patch.object(admin_cache, "CACHE_FILE_PATH", target):
            loaded = admin_cache._load_admin_cache()
        # String IDs are coerced; unusable entries are dropped, good ones kept.
        assert loaded == {-1001: [111], -1003: [222, 333]}

    def test_corrupt_file_returns_empty(self, tmp_path):
        from bot.services import admin_cache

        target = tmp_path / "admin_cache.json"
        target.write_text("{not json")
        with patch.object(admin_cache, "CACHE_FILE_PATH", target):
            assert admin_cache._load_admin_cache() == {}

    async def test_refresh_failure_does_not_overwrite_good_disk_cache(self, tmp_path):
        """A refresh where every fetch fails must not clobber the saved roster."""
        from bot.services import admin_cache
        from bot.services.admin_cache import refresh_admin_ids

        target = tmp_path / "admin_cache.json"
        target.write_text('{"-1001": [999]}')

        registry = GroupRegistry()
        registry.register(GroupConfig(group_id=-1001, warning_topic_id=1))

        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot_data = {}

        with (
            patch.object(admin_cache, "CACHE_FILE_PATH", target),
            patch("bot.services.admin_cache.get_group_registry", return_value=registry),
            patch("bot.services.admin_cache.fetch_group_admin_ids") as mock_fetch,
        ):
            mock_fetch.side_effect = TelegramAdminFetchError("API error")
            await refresh_admin_ids(mock_context)

        assert json.loads(target.read_text()) == {"-1001": [999]}

    async def test_refresh_with_empty_registry_preserves_disk_cache(self, tmp_path):
        """No registered groups must not truncate the saved roster."""
        from bot.services import admin_cache
        from bot.services.admin_cache import refresh_admin_ids

        target = tmp_path / "admin_cache.json"
        target.write_text('{"-1001": [999]}')

        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot_data = {}

        with (
            patch.object(admin_cache, "CACHE_FILE_PATH", target),
            patch(
                "bot.services.admin_cache.get_group_registry",
                return_value=GroupRegistry(),
            ),
        ):
            await refresh_admin_ids(mock_context)

        assert json.loads(target.read_text()) == {"-1001": [999]}

    async def test_preload_seeds_from_disk_when_bot_data_empty(self, tmp_path):
        """The disk cache is the fallback when bot_data has nothing yet."""
        from bot.services import admin_cache
        from bot.services.admin_cache import preload_admin_ids

        target = tmp_path / "admin_cache.json"
        target.write_text('{"-1001": [777]}')

        registry = GroupRegistry()
        registry.register(GroupConfig(group_id=-1001, warning_topic_id=1))

        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot_data = {}

        with (
            patch.object(admin_cache, "CACHE_FILE_PATH", target),
            patch("bot.services.admin_cache.get_group_registry", return_value=registry),
            patch("bot.services.admin_cache.fetch_group_admin_ids") as mock_fetch,
        ):
            mock_fetch.side_effect = TelegramAdminFetchError("API error")
            await preload_admin_ids(mock_context)

        # Seeded from disk, and the seeded admin stays visible to admin_ids.
        assert mock_context.bot_data["group_admin_ids"][-1001] == [777]
        assert mock_context.bot_data["admin_ids"] == [777]


class TestCachePathDerivation:
    """The cache lives beside the configured database, not in a fixed spot."""

    def test_follows_configured_database_directory(self, tmp_path, monkeypatch):
        from bot.config import get_settings
        from bot.services import admin_cache

        db_path = tmp_path / "sub" / "bot.db"
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("DATABASE_PATH", str(db_path))
        monkeypatch.setattr(admin_cache, "CACHE_FILE_PATH", None)
        get_settings.cache_clear()
        try:
            assert admin_cache._cache_file_path() == tmp_path / "sub" / "admin_cache.json"
        finally:
            get_settings.cache_clear()

    def test_in_memory_database_uses_default_data_dir(self, monkeypatch):
        from bot.config import get_settings
        from bot.services import admin_cache

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("DATABASE_PATH", ":memory:")
        monkeypatch.setattr(admin_cache, "CACHE_FILE_PATH", None)
        get_settings.cache_clear()
        try:
            assert admin_cache._cache_file_path() == Path("data/admin_cache.json")
        finally:
            get_settings.cache_clear()

    def test_bare_filename_does_not_write_to_cwd(self, monkeypatch):
        from bot.config import get_settings
        from bot.services import admin_cache

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("DATABASE_PATH", "bot.db")
        monkeypatch.setattr(admin_cache, "CACHE_FILE_PATH", None)
        get_settings.cache_clear()
        try:
            assert admin_cache._cache_file_path() == Path("data/admin_cache.json")
        finally:
            get_settings.cache_clear()

    def test_missing_settings_falls_back_to_default(self, monkeypatch):
        from bot.config import get_settings
        from bot.services import admin_cache

        for var in ("TELEGRAM_BOT_TOKEN", "GROUP_ID", "WARNING_TOPIC_ID"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr(admin_cache, "CACHE_FILE_PATH", None)
        get_settings.cache_clear()
        try:
            assert admin_cache._cache_file_path() == Path("data/admin_cache.json")
        finally:
            get_settings.cache_clear()


class TestFetchErrorHandling:
    """Only recoverable errors degrade to cache; programming errors propagate."""

    async def test_recoverable_error_falls_back_to_cache(self):
        from telegram.error import TimedOut

        from bot.services.admin_cache import refresh_admin_ids

        registry = GroupRegistry()
        registry.register(GroupConfig(group_id=-1001, warning_topic_id=1))

        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot_data = {"group_admin_ids": {-1001: [999]}, "admin_ids": [999]}

        with (
            patch("bot.services.admin_cache.get_group_registry", return_value=registry),
            patch(
                "bot.services.admin_cache.fetch_group_admin_ids",
                side_effect=TimedOut("timeout"),
            ),
        ):
            await refresh_admin_ids(mock_context)

        assert mock_context.bot_data["group_admin_ids"][-1001] == [999]

    async def test_programming_error_is_not_swallowed(self):
        """A TypeError must surface, not masquerade as a failed fetch."""
        from bot.services.admin_cache import refresh_admin_ids

        registry = GroupRegistry()
        registry.register(GroupConfig(group_id=-1001, warning_topic_id=1))

        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot_data = {}

        with (
            patch("bot.services.admin_cache.get_group_registry", return_value=registry),
            patch(
                "bot.services.admin_cache.fetch_group_admin_ids",
                side_effect=TypeError("bug in fetch path"),
            ),
        ):
            with pytest.raises(TypeError):
                await refresh_admin_ids(mock_context)


class TestConcurrentFetch:
    """Fetching is concurrent; a sequential loop must fail these tests."""

    async def test_groups_are_fetched_concurrently(self):
        from bot.services.admin_cache import refresh_admin_ids

        registry = GroupRegistry()
        for gid in (-1001, -1002, -1003):
            registry.register(GroupConfig(group_id=gid, warning_topic_id=1))

        started: list[int] = []
        release = asyncio.Event()

        async def slow_fetch(bot, group_id):
            started.append(group_id)
            if len(started) == 3:
                release.set()
            # Every fetch must be in flight before any can complete.
            await asyncio.wait_for(release.wait(), timeout=1)
            return [group_id]

        mock_context = MagicMock()
        mock_context.bot = AsyncMock()
        mock_context.bot_data = {}

        with (
            patch("bot.services.admin_cache.get_group_registry", return_value=registry),
            patch("bot.services.admin_cache.fetch_group_admin_ids", side_effect=slow_fetch),
            patch("bot.services.admin_cache._save_admin_cache"),
        ):
            await refresh_admin_ids(mock_context)

        assert len(started) == 3
        assert set(mock_context.bot_data["group_admin_ids"]) == {-1001, -1002, -1003}
