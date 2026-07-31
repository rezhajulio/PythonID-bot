"""Tests for the /status command handler."""

import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.database.service import get_database, init_database, reset_database
from bot.group_config import GroupConfig, GroupRegistry
from bot.handlers.status import handle_status


@pytest.fixture(autouse=True)
def temp_db():
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        reset_database()
        init_database(str(db_path))
        yield db_path
        reset_database()


@pytest.fixture
def mock_registry():
    registry = GroupRegistry()
    registry.register(GroupConfig(
        group_id=-1001, warning_topic_id=11,
        captcha_enabled=True,
    ))
    registry.register(GroupConfig(
        group_id=-1002, warning_topic_id=12,
        captcha_enabled=False,
    ))
    return registry


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.database_path = "/tmp/test.db"
    return settings


@pytest.fixture
def mock_update():
    update = MagicMock()
    update.message = MagicMock()
    update.message.from_user = MagicMock()
    update.message.from_user.id = 12345
    update.message.from_user.full_name = "Admin User"
    update.message.reply_text = AsyncMock()
    update.effective_chat = MagicMock()
    update.effective_chat.type = "private"
    return update


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.bot = MagicMock()
    context.bot_data = {
        "admin_ids": [12345],
        "group_admin_ids": {-1001: [12345], -1002: [12345]},
        "start_time": time.monotonic(),
        "plugin_effective_map": {
            -1001: {"captcha": True, "spam": True},
            -1002: {"captcha": False, "spam": True, "profile_monitor": False},
        },
    }
    return context


class TestHandleStatus:

    async def test_handle_status_non_private_chat_rejected(self, mock_context):
        """Group chat → handler replies with DM-only error."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.from_user = MagicMock()
        update.message.from_user.id = 12345
        update.message.reply_text = AsyncMock()
        update.effective_chat = MagicMock()
        update.effective_chat.type = "group"

        await handle_status(update, mock_context)

        update.message.reply_text.assert_called_once()
        args, _ = update.message.reply_text.call_args
        assert "chat pribadi" in args[0]

    async def test_handle_status_non_admin_rejected(self, mock_context):
        """Private chat but caller not admin → handler replies with no-permission."""
        mock_context.bot_data["admin_ids"] = [99999]
        non_admin_update = MagicMock()
        non_admin_update.message = MagicMock()
        non_admin_update.message.from_user = MagicMock()
        non_admin_update.message.from_user.id = 111
        non_admin_update.message.from_user.full_name = "Bad Actor"
        non_admin_update.message.reply_text = AsyncMock()
        non_admin_update.effective_chat = MagicMock()
        non_admin_update.effective_chat.type = "private"

        await handle_status(non_admin_update, mock_context)

        non_admin_update.message.reply_text.assert_called_once()
        args, _ = non_admin_update.message.reply_text.call_args
        assert "tidak memiliki izin" in args[0]

    async def test_handle_status_admin_success(
        self, mock_update, mock_context, mock_registry, mock_settings,
    ):
        """Admin in private chat gets full status with all sections."""
        with (
            patch("bot.handlers.status.get_group_registry", return_value=mock_registry),
            patch("bot.handlers.status.get_settings", return_value=mock_settings),
            patch("bot.handlers.status.get_admin_groups", return_value=[-1001, -1002]),
        ):
            await handle_status(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        args, kwargs = mock_update.message.reply_text.call_args
        text = args[0]
        assert "*Uptime:*" in text
        assert "*Grup yang kamu admin:*" in text
        assert "*Database:*" in text
        assert "*Jadwal terakhir:*" in text

    async def test_handle_status_shows_enforcement_mode(
        self, mock_update, mock_context, mock_registry, mock_settings,
    ):
        """Enforcement mode (Restriksi/Peringatan) appears per group."""
        with (
            patch("bot.handlers.status.get_group_registry", return_value=mock_registry),
            patch("bot.handlers.status.get_settings", return_value=mock_settings),
            patch("bot.handlers.status.get_admin_groups", return_value=[-1001, -1002]),
        ):
            await handle_status(mock_update, mock_context)

        args, _ = mock_update.message.reply_text.call_args
        text = args[0]
        assert "Restriksi" in text or "Peringatan" in text

    async def test_handle_status_shows_per_group_captcha_count(
        self, mock_update, mock_context, mock_registry, mock_settings,
    ):
        """Per-group pending captcha counts appear in status reply."""
        db = get_database()
        db.add_pending_captcha(
            user_id=111, group_id=-1001,
            chat_id=-1001, message_id=1,
            user_full_name="User1",
        )
        db.add_pending_captcha(
            user_id=222, group_id=-1002,
            chat_id=-1002, message_id=2,
            user_full_name="User2",
        )

        with (
            patch("bot.handlers.status.get_group_registry", return_value=mock_registry),
            patch("bot.handlers.status.get_settings", return_value=mock_settings),
            patch("bot.handlers.status.get_admin_groups", return_value=[-1001, -1002]),
        ):
            await handle_status(mock_update, mock_context)

        args, _ = mock_update.message.reply_text.call_args
        text = args[0]
        assert "Captcha: 1" in text

    async def test_handle_status_shows_disabled_plugins(
        self, mock_update, mock_context, mock_registry, mock_settings,
    ):
        """Disabled plugins appear in per-group section."""
        with (
            patch("bot.handlers.status.get_group_registry", return_value=mock_registry),
            patch("bot.handlers.status.get_settings", return_value=mock_settings),
            patch("bot.handlers.status.get_admin_groups", return_value=[-1001, -1002]),
        ):
            await handle_status(mock_update, mock_context)

        args, _ = mock_update.message.reply_text.call_args
        text = args[0]
        assert "Plugin nonaktif" in text
        assert "profile" in text and "monitor" in text

    async def test_handle_status_shows_last_job_timestamps(
        self, mock_update, mock_context, mock_registry, mock_settings,
    ):
        """Timestamps for last jobs appear in status reply."""
        mock_context.bot_data["last_admin_refresh"] = time.time() - 60
        mock_context.bot_data["last_auto_restrict"] = time.time() - 300

        with (
            patch("bot.handlers.status.get_group_registry", return_value=mock_registry),
            patch("bot.handlers.status.get_settings", return_value=mock_settings),
            patch("bot.handlers.status.get_admin_groups", return_value=[-1001, -1002]),
        ):
            await handle_status(mock_update, mock_context)

        args, _ = mock_update.message.reply_text.call_args
        text = args[0]
        assert "Refresh admin:" in text
        assert "Auto-restrict:" in text
        assert "belum pernah" not in text

    async def test_handle_status_no_admin_groups(
        self, mock_update, mock_context, mock_registry, mock_settings,
    ):
        """Admin with no group admin rights sees empty group list."""
        with (
            patch("bot.handlers.status.get_group_registry", return_value=mock_registry),
            patch("bot.handlers.status.get_settings", return_value=mock_settings),
            patch("bot.handlers.status.get_admin_groups", return_value=[]),
        ):
            await handle_status(mock_update, mock_context)

        args, _ = mock_update.message.reply_text.call_args
        text = args[0]
        assert "Tidak ada grup yang dipantau" in text

    async def test_handle_status_scoped_to_admin_groups_only(
        self, mock_update, mock_context, mock_registry, mock_settings,
    ):
        """Only groups where caller is admin are shown."""
        with (
            patch("bot.handlers.status.get_group_registry", return_value=mock_registry),
            patch("bot.handlers.status.get_settings", return_value=mock_settings),
            patch("bot.handlers.status.get_admin_groups", return_value=[-1001]),
        ):
            await handle_status(mock_update, mock_context)

        args, _ = mock_update.message.reply_text.call_args
        text = args[0]
        assert "-1001" in text
        assert "-1002" not in text
