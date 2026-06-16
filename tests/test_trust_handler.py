"""Tests for trusted user command handlers."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.constants import (
    TRUST_USER_ID_INVALID_MESSAGE,
    TRUST_USER_ID_REQUIRED_MESSAGE,
)
from bot.database.service import get_database, init_database, reset_database
from bot.group_config import GroupConfig, GroupRegistry
from bot.handlers.trust import (
    _resolve_target_user_id,
    handle_trust_callback,
    handle_trust_command,
    handle_trusted_list_command,
    handle_untrust_callback,
    handle_untrust_command,
)


@pytest.fixture(autouse=True)
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        reset_database()
        init_database(str(db_path))
        yield db_path
        reset_database()


@pytest.fixture
def mock_registry():
    registry = GroupRegistry()
    registry.register(GroupConfig(group_id=-1001, warning_topic_id=11))
    registry.register(GroupConfig(group_id=-1002, warning_topic_id=12))
    return registry


@pytest.fixture
def mock_update():
    update = MagicMock()
    update.message = MagicMock()
    update.message.from_user = MagicMock()
    update.message.from_user.id = 12345
    update.message.from_user.full_name = "Admin User"
    update.message.from_user.username = "admin_user"
    update.message.reply_text = AsyncMock()
    update.effective_chat = MagicMock()
    update.effective_chat.type = "private"
    update.message.forward_origin = None
    update.message.forward_from = None
    return update


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.bot = MagicMock()
    context.bot_data = {"admin_ids": [12345], "trusted_user_ids": set()}
    context.args = []
    return context


class TestTrustCommands:
    async def test_trust_command_no_message_returns_early(self, mock_context):
        update = MagicMock()
        update.message = None

        await handle_trust_command(update, mock_context)

    async def test_trust_command_no_from_user_returns_early(self, mock_context):
        update = MagicMock()
        update.message = MagicMock()
        update.message.from_user = None

        await handle_trust_command(update, mock_context)

    async def test_trust_command_requires_admin(self, mock_update, mock_context):
        mock_update.message.from_user.id = 99999
        mock_context.args = ["1111"]

        await handle_trust_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "izin" in mock_update.message.reply_text.call_args.args[0]

    async def test_trust_command_requires_private_chat(self, mock_update, mock_context):
        mock_update.effective_chat.type = "group"
        mock_context.args = ["1111"]

        await handle_trust_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "chat pribadi" in mock_update.message.reply_text.call_args.args[0]

    async def test_trust_command_invalid_user_id(self, mock_update, mock_context):
        mock_context.args = ["abc"]

        await handle_trust_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "angka" in mock_update.message.reply_text.call_args.args[0]

    async def test_trust_command_missing_user_id_and_no_forward(self, mock_update, mock_context):
        mock_context.args = []

        await handle_trust_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "penggunaan" in mock_update.message.reply_text.call_args.args[0].lower()

    async def test_trust_command_success_by_user_id(
        self, mock_update, mock_context, mock_registry, monkeypatch
    ):
        monkeypatch.setattr("bot.handlers.trust.get_group_registry", lambda: mock_registry)
        mock_context.args = ["1111"]

        unrestrict = AsyncMock()
        monkeypatch.setattr("bot.handlers.trust.unrestrict_user", unrestrict)

        db = get_database()
        db.start_new_user_probation(user_id=1111, group_id=-1001)
        db.start_new_user_probation(user_id=1111, group_id=-1002)

        await handle_trust_command(mock_update, mock_context)

        assert db.is_user_trusted(1111) is True
        assert 1111 in mock_context.bot_data["trusted_user_ids"]
        assert isinstance(mock_context.bot_data["trusted_user_ids"], set)
        assert db.get_new_user_probation(1111, -1001) is None
        assert db.get_new_user_probation(1111, -1002) is None
        assert unrestrict.await_count == 2
        reply_args = mock_update.message.reply_text.call_args
        assert "ditambahkan" in reply_args.args[0].lower()
        assert reply_args.kwargs.get("parse_mode") == "Markdown"

    async def test_trust_command_success_from_forwarded_message(
        self, mock_update, mock_context, mock_registry, monkeypatch
    ):
        monkeypatch.setattr("bot.handlers.trust.get_group_registry", lambda: mock_registry)
        monkeypatch.setattr("bot.handlers.trust.unrestrict_user", AsyncMock())

        forwarded_user = MagicMock()
        forwarded_user.id = 4444
        forwarded_user.full_name = "Forwarded User"
        forwarded_user.username = None
        mock_update.message.forward_from = forwarded_user

        await handle_trust_command(mock_update, mock_context)

        assert get_database().is_user_trusted(4444) is True

    async def test_trust_command_duplicate(self, mock_update, mock_context, mock_registry, monkeypatch):
        monkeypatch.setattr("bot.handlers.trust.get_group_registry", lambda: mock_registry)
        monkeypatch.setattr("bot.handlers.trust.unrestrict_user", AsyncMock())
        mock_context.args = ["1111"]

        db = get_database()
        db.add_trusted_user(user_id=1111, trusted_by_admin_id=12345)

        await handle_trust_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        reply_args = mock_update.message.reply_text.call_args
        assert "sudah" in reply_args.args[0].lower()
        assert reply_args.kwargs.get("parse_mode") == "Markdown"

    async def test_trust_command_continues_on_unrestrict_error(
        self, mock_update, mock_context, mock_registry, monkeypatch
    ):
        monkeypatch.setattr("bot.handlers.trust.get_group_registry", lambda: mock_registry)

        unrestrict = AsyncMock(side_effect=[Exception("failed"), None])
        monkeypatch.setattr("bot.handlers.trust.unrestrict_user", unrestrict)
        mock_context.args = ["2111"]

        await handle_trust_command(mock_update, mock_context)

        assert get_database().is_user_trusted(2111) is True

    async def test_trust_command_unrestrict_attempted_even_when_probation_lookup_fails(
        self, mock_update, mock_context, mock_registry, monkeypatch
    ):
        """If probation lookup raises, unrestrict_user is still called for that group."""
        monkeypatch.setattr("bot.handlers.trust.get_group_registry", lambda: mock_registry)
        unrestrict = AsyncMock()
        monkeypatch.setattr("bot.handlers.trust.unrestrict_user", unrestrict)
        mock_context.args = ["9111"]

        db = get_database()
        # Force get_new_user_probation to blow up for both groups.
        monkeypatch.setattr(
            db,
            "get_new_user_probation",
            MagicMock(side_effect=Exception("probation lookup failed")),
        )

        await handle_trust_command(mock_update, mock_context)

        # Unrestrict was still attempted once per group despite probation
        # cleanup raising.
        assert unrestrict.await_count == 2
        reply_args = mock_update.message.reply_text.call_args
        assert "ditambahkan" in reply_args.args[0].lower()
        # Probation count is 0, unrestrict count is 2.
        assert "0" in reply_args.args[0]
        assert "2" in reply_args.args[0]

    async def test_untrust_command_requires_private_chat(self, mock_update, mock_context):
        mock_update.effective_chat.type = "group"
        mock_context.args = ["2222"]

        await handle_untrust_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "chat pribadi" in mock_update.message.reply_text.call_args.args[0]

    async def test_untrust_command_requires_admin(self, mock_update, mock_context):
        mock_update.message.from_user.id = 99999
        mock_context.args = ["2222"]

        await handle_untrust_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "izin" in mock_update.message.reply_text.call_args.args[0]

    async def test_untrust_command_no_message_returns_early(self, mock_context):
        update = MagicMock()
        update.message = None

        await handle_untrust_command(update, mock_context)

    async def test_untrust_command_no_from_user_returns_early(self, mock_context):
        update = MagicMock()
        update.message = MagicMock()
        update.message.from_user = None

        await handle_untrust_command(update, mock_context)

    async def test_untrust_command_invalid_user_id(self, mock_update, mock_context):
        mock_context.args = ["abc"]

        await handle_untrust_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "angka" in mock_update.message.reply_text.call_args.args[0]

    async def test_untrust_command_missing_user_id_and_no_forward(self, mock_update, mock_context):
        mock_context.args = []

        await handle_untrust_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "penggunaan" in mock_update.message.reply_text.call_args.args[0].lower()

    async def test_untrust_command_success(self, mock_update, mock_context):
        mock_context.args = ["2222"]

        db = get_database()
        db.add_trusted_user(user_id=2222, trusted_by_admin_id=12345)
        mock_context.bot_data["trusted_user_ids"] = {2222}

        await handle_untrust_command(mock_update, mock_context)

        assert db.is_user_trusted(2222) is False
        assert 2222 not in mock_context.bot_data["trusted_user_ids"]
        assert isinstance(mock_context.bot_data["trusted_user_ids"], set)
        reply_args = mock_update.message.reply_text.call_args
        assert "dihapus" in reply_args.args[0].lower()
        assert reply_args.kwargs.get("parse_mode") == "Markdown"

    async def test_untrust_command_missing_user(self, mock_update, mock_context):
        mock_context.args = ["3333"]

        await handle_untrust_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        reply_args = mock_update.message.reply_text.call_args
        assert "tidak ada" in reply_args.args[0].lower()
        assert reply_args.kwargs.get("parse_mode") == "Markdown"

    async def test_trusted_list_command_no_message_returns_early(self, mock_context):
        update = MagicMock()
        update.message = None

        await handle_trusted_list_command(update, mock_context)

    async def test_trusted_list_command_no_from_user_returns_early(self, mock_context):
        update = MagicMock()
        update.message = MagicMock()
        update.message.from_user = None

        await handle_trusted_list_command(update, mock_context)

    async def test_trusted_list_command_requires_private_chat(self, mock_update, mock_context):
        mock_update.effective_chat.type = "group"

        await handle_trusted_list_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "chat pribadi" in mock_update.message.reply_text.call_args.args[0]

    async def test_trusted_list_command_requires_admin(self, mock_update, mock_context):
        mock_update.message.from_user.id = 99999

        await handle_trusted_list_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "izin" in mock_update.message.reply_text.call_args.args[0]

    async def test_trusted_list_command_empty(self, mock_update, mock_context):
        await handle_trusted_list_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "kosong" in mock_update.message.reply_text.call_args.args[0].lower()

    async def test_trusted_list_command(self, mock_update, mock_context):
        db = get_database()
        db.add_trusted_user(
            user_id=8001, trusted_by_admin_id=12345,
            user_full_name="Alice Trusted", username="alice_t",
            admin_full_name="Admin One", admin_username="admin_one",
        )
        db.add_trusted_user(
            user_id=8002, trusted_by_admin_id=54321,
            user_full_name="Bob Trusted", username=None,
            admin_full_name="Admin Two", admin_username=None,
        )

        await handle_trusted_list_command(mock_update, mock_context)

        message = mock_update.message.reply_text.call_args.args[0]
        assert "8001" in message
        assert "8002" in message
        assert "UTC" in message
        assert "Alice Trusted" in message
        assert "@alice\_t" in message
        assert "Bob Trusted" in message
        assert "Admin One" in message
        assert "Admin Two" in message

    async def test_trusted_list_command_empty_name_fallback(
        self, mock_update, mock_context
    ):
        db = get_database()
        db.add_trusted_user(user_id=8001, trusted_by_admin_id=12345)

        await handle_trusted_list_command(mock_update, mock_context)

        message = mock_update.message.reply_text.call_args.args[0]
        assert "User 8001" in message


class TestTrustCallbacks:
    @pytest.fixture
    def mock_callback_update(self):
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.from_user = MagicMock()
        update.callback_query.from_user.id = 12345
        update.callback_query.from_user.full_name = "Admin User"
        update.callback_query.from_user.username = "admin_user"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        return update

    async def test_trust_callback_no_query_returns_early(self, mock_context):
        update = MagicMock()
        update.callback_query = None

        await handle_trust_callback(update, mock_context)

    async def test_trust_callback_invalid_data(self, mock_callback_update, mock_context):
        mock_callback_update.callback_query.data = "trust:bad"

        await handle_trust_callback(mock_callback_update, mock_context)

        mock_callback_update.callback_query.edit_message_text.assert_called_once()
        assert "callback" in mock_callback_update.callback_query.edit_message_text.call_args.args[0].lower()

    async def test_trust_callback_success(self, mock_callback_update, mock_context, mock_registry, monkeypatch):
        monkeypatch.setattr("bot.handlers.trust.get_group_registry", lambda: mock_registry)
        monkeypatch.setattr("bot.handlers.trust.unrestrict_user", AsyncMock())
        mock_callback_update.callback_query.data = "trust:7001"

        await handle_trust_callback(mock_callback_update, mock_context)

        assert get_database().is_user_trusted(7001) is True
        assert 7001 in mock_context.bot_data["trusted_user_ids"]
        assert isinstance(mock_context.bot_data["trusted_user_ids"], set)
        mock_callback_update.callback_query.edit_message_text.assert_called_once()
        edit_args = mock_callback_update.callback_query.edit_message_text.call_args
        assert edit_args.kwargs.get("parse_mode") == "Markdown"

    async def test_untrust_callback_no_query_returns_early(self, mock_context):
        update = MagicMock()
        update.callback_query = None

        await handle_untrust_callback(update, mock_context)

    async def test_untrust_callback_invalid_data(self, mock_callback_update, mock_context):
        mock_callback_update.callback_query.data = "untrust:bad"

        await handle_untrust_callback(mock_callback_update, mock_context)

        mock_callback_update.callback_query.edit_message_text.assert_called_once()
        assert "callback" in mock_callback_update.callback_query.edit_message_text.call_args.args[0].lower()

    async def test_untrust_callback_success(self, mock_callback_update, mock_context):
        get_database().add_trusted_user(user_id=7002, trusted_by_admin_id=12345)
        mock_context.bot_data["trusted_user_ids"] = {7002}
        mock_callback_update.callback_query.data = "untrust:7002"

        await handle_untrust_callback(mock_callback_update, mock_context)

        assert get_database().is_user_trusted(7002) is False
        assert 7002 not in mock_context.bot_data["trusted_user_ids"]
        assert isinstance(mock_context.bot_data["trusted_user_ids"], set)
        mock_callback_update.callback_query.edit_message_text.assert_called_once()
        edit_args = mock_callback_update.callback_query.edit_message_text.call_args
        assert edit_args.kwargs.get("parse_mode") == "Markdown"

    async def test_trust_callback_duplicate(
        self, mock_callback_update, mock_context, mock_registry, monkeypatch
    ):
        """Trust callback for already-trusted user yields TRUST_ALREADY_EXISTS message."""
        monkeypatch.setattr("bot.handlers.trust.get_group_registry", lambda: mock_registry)
        monkeypatch.setattr("bot.handlers.trust.unrestrict_user", AsyncMock())
        get_database().add_trusted_user(user_id=7003, trusted_by_admin_id=12345)
        mock_callback_update.callback_query.data = "trust:7003"

        await handle_trust_callback(mock_callback_update, mock_context)

        edit_args = mock_callback_update.callback_query.edit_message_text.call_args
        assert "sudah" in edit_args.args[0].lower()
        assert edit_args.kwargs.get("parse_mode") == "Markdown"

    async def test_untrust_callback_missing_user(self, mock_callback_update, mock_context):
        """Untrust callback for user not in trusted list yields not-found message."""
        mock_callback_update.callback_query.data = "untrust:7004"

        await handle_untrust_callback(mock_callback_update, mock_context)

        edit_args = mock_callback_update.callback_query.edit_message_text.call_args
        assert "tidak ada" in edit_args.args[0].lower()
        assert edit_args.kwargs.get("parse_mode") == "Markdown"

    async def test_callback_non_admin_rejected(self, mock_callback_update, mock_context):
        mock_callback_update.callback_query.from_user.id = 99999
        mock_callback_update.callback_query.data = "trust:8003"

        await handle_trust_callback(mock_callback_update, mock_context)

        mock_callback_update.callback_query.edit_message_text.assert_called_once()
        assert "izin" in mock_callback_update.callback_query.edit_message_text.call_args.args[0].lower()

    async def test_untrust_callback_non_admin_rejected(self, mock_callback_update, mock_context):
        mock_callback_update.callback_query.from_user.id = 99999
        mock_callback_update.callback_query.data = "untrust:8003"

        await handle_untrust_callback(mock_callback_update, mock_context)

        mock_callback_update.callback_query.edit_message_text.assert_called_once()
        assert "izin" in mock_callback_update.callback_query.edit_message_text.call_args.args[0].lower()


class TestResolveTargetUserId:
    """Tests for the tuple-returning ``_resolve_target_user_id`` helper."""

    def _make_update(self, *, forward_from=None) -> MagicMock:
        update = MagicMock()
        update.message = MagicMock()
        update.message.forward_origin = None
        update.message.forward_from = forward_from
        return update

    def test_success_with_explicit_arg(self):
        update = self._make_update()

        user_id, err = _resolve_target_user_id(update, ["1234"])

        assert user_id == 1234
        assert err is None

    def test_invalid_int_returns_invalid_message(self):
        update = self._make_update()

        user_id, err = _resolve_target_user_id(update, ["abc"])

        assert user_id is None
        assert err == TRUST_USER_ID_INVALID_MESSAGE

    def test_missing_args_and_no_forward_returns_required_message(self):
        update = self._make_update()

        user_id, err = _resolve_target_user_id(update, [])

        assert user_id is None
        assert err == TRUST_USER_ID_REQUIRED_MESSAGE

    def test_forwarded_message_resolves_user_id(self):
        forwarded_user = MagicMock()
        forwarded_user.id = 5555
        forwarded_user.full_name = "Forwarded"
        update = self._make_update(forward_from=forwarded_user)

        user_id, err = _resolve_target_user_id(update, [])

        assert user_id == 5555
        assert err is None


class TestTrustedCacheHelpers:
    """Tests for ``_add_trusted_cache``/``_remove_trusted_cache`` set semantics."""

    def test_add_initialises_missing_cache_as_set(self):
        from bot.handlers.trust import _add_trusted_cache

        context = MagicMock()
        context.bot_data = {}

        _add_trusted_cache(context, 42)

        assert context.bot_data["trusted_user_ids"] == {42}
        assert isinstance(context.bot_data["trusted_user_ids"], set)

    def test_add_mutates_existing_set_in_place(self):
        from bot.handlers.trust import _add_trusted_cache

        existing = {1, 2}
        context = MagicMock()
        context.bot_data = {"trusted_user_ids": existing}

        _add_trusted_cache(context, 3)

        assert context.bot_data["trusted_user_ids"] is existing
        assert existing == {1, 2, 3}

    def test_remove_initialises_missing_cache_as_set(self):
        from bot.handlers.trust import _remove_trusted_cache

        context = MagicMock()
        context.bot_data = {}

        _remove_trusted_cache(context, 42)

        assert context.bot_data["trusted_user_ids"] == set()
        assert isinstance(context.bot_data["trusted_user_ids"], set)

    def test_remove_mutates_existing_set_in_place(self):
        from bot.handlers.trust import _remove_trusted_cache

        existing = {1, 2, 3}
        context = MagicMock()
        context.bot_data = {"trusted_user_ids": existing}

        _remove_trusted_cache(context, 2)

        assert context.bot_data["trusted_user_ids"] is existing
        assert existing == {1, 3}
