"""Tests for guest bot message moderation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Message, User
from telegram.ext import ApplicationHandlerStop

from bot.group_config import GroupConfig
from bot.handlers.guest_bot import (
    handle_guest_bot_message,
    is_guest_bot_message,
    is_guest_bot_whitelisted,
)


@pytest.fixture
def mock_user():
    return User(id=123, first_name="Test", is_bot=False, username="testuser")


@pytest.fixture
def mock_group_config():
    return GroupConfig(
        group_id=-1001234567890,
        warning_topic_id=123,
        warning_threshold=3,
        guest_bot_whitelist=["allowedbot"],
    )


@pytest.fixture
def mock_update(mock_user):
    message = MagicMock(spec=Message)
    message.from_user = User(id=999, first_name="Guest Bot", is_bot=True, username="guestbot")
    message.guest_bot_caller_user = mock_user
    message.guest_bot_caller_chat = None
    message.delete = AsyncMock()
    update = MagicMock()
    update.message = message
    return update


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.bot_data = {"group_admin_ids": {}, "trusted_user_ids": []}
    context.bot = AsyncMock()
    return context


class TestIsGuestBotMessage:
    def test_user_caller(self):
        message = MagicMock(spec=Message)
        message.guest_bot_caller_user = MagicMock()
        message.guest_bot_caller_chat = None
        assert is_guest_bot_message(message) is True

    def test_chat_caller(self):
        message = MagicMock(spec=Message)
        message.guest_bot_caller_user = None
        message.guest_bot_caller_chat = MagicMock()
        assert is_guest_bot_message(message) is True

    def test_regular_message(self):
        message = MagicMock(spec=Message)
        message.guest_bot_caller_user = None
        message.guest_bot_caller_chat = None
        assert is_guest_bot_message(message) is False


class TestIsGuestBotWhitelisted:
    @pytest.mark.parametrize(
        ("username", "whitelist", "expected"),
        [
            ("allowedbot", ["allowedbot"], True),
            ("otherbot", ["allowedbot"], False),
            ("AllowedBot", ["allowedbot"], True),
            (None, ["allowedbot"], False),
        ],
    )
    def test_whitelist(self, username, whitelist, expected):
        message = MagicMock(spec=Message)
        message.from_user = User(id=999, first_name="Bot", is_bot=True, username=username)
        assert is_guest_bot_whitelisted(message, whitelist) is expected


class TestHandleGuestBotMessage:
    async def test_non_guest_message_does_nothing(self, mock_update, mock_context, mock_group_config):
        mock_update.message.guest_bot_caller_user = None
        with patch("bot.handlers.guest_bot.get_group_config_for_update", return_value=mock_group_config):
            await handle_guest_bot_message(mock_update, mock_context)
        mock_update.message.delete.assert_not_awaited()

    async def test_whitelisted_message_does_nothing(self, mock_update, mock_context, mock_group_config):
        mock_update.message.from_user = User(id=999, first_name="Bot", is_bot=True, username="allowedbot")
        with patch("bot.handlers.guest_bot.get_group_config_for_update", return_value=mock_group_config):
            await handle_guest_bot_message(mock_update, mock_context)
        mock_update.message.delete.assert_not_awaited()

    async def test_unmonitored_group_returns(self, mock_update, mock_context):
        with patch("bot.handlers.guest_bot.get_group_config_for_update", return_value=None):
            await handle_guest_bot_message(mock_update, mock_context)
        mock_update.message.delete.assert_not_awaited()

    async def test_admin_is_deleted_but_not_restricted(self, mock_update, mock_context, mock_group_config):
        with (
            patch("bot.handlers.guest_bot.get_group_config_for_update", return_value=mock_group_config),
            patch("bot.handlers.guest_bot.is_user_admin_or_trusted", return_value=True),
            patch("bot.handlers.guest_bot.get_database") as get_db,
            pytest.raises(ApplicationHandlerStop),
        ):
            await handle_guest_bot_message(mock_update, mock_context)
        mock_update.message.delete.assert_awaited_once()
        get_db.assert_not_called()

    @pytest.mark.parametrize(("count", "sends", "increments"), [(1, 1, True), (2, 0, True)])
    async def test_pre_threshold_violation(
        self, mock_update, mock_context, mock_group_config, count, sends, increments
    ):
        db = MagicMock()
        db.is_user_restricted_by_bot.return_value = False
        db.get_or_create_user_warning.return_value.message_count = count
        with (
            patch("bot.handlers.guest_bot.get_group_config_for_update", return_value=mock_group_config),
            patch("bot.handlers.guest_bot.is_user_admin_or_trusted", return_value=False),
            patch("bot.handlers.guest_bot.get_database", return_value=db),
            pytest.raises(ApplicationHandlerStop),
        ):
            await handle_guest_bot_message(mock_update, mock_context)
        assert mock_context.bot.send_message.await_count == sends
        assert db.increment_message_count.called is increments

    async def test_threshold_restricts_and_notifies(self, mock_update, mock_context, mock_group_config):
        db = MagicMock()
        db.is_user_restricted_by_bot.return_value = False
        db.get_or_create_user_warning.return_value.message_count = 3
        with (
            patch("bot.handlers.guest_bot.get_group_config_for_update", return_value=mock_group_config),
            patch("bot.handlers.guest_bot.is_user_admin_or_trusted", return_value=False),
            patch("bot.handlers.guest_bot.get_database", return_value=db),
            pytest.raises(ApplicationHandlerStop),
        ):
            await handle_guest_bot_message(mock_update, mock_context)
        mock_context.bot.restrict_chat_member.assert_awaited_once()
        mock_context.bot.send_message.assert_awaited_once()
        db.mark_user_restricted.assert_called_once_with(
            123, mock_group_config.group_id, warning_kind="guest_bot"
        )

    async def test_threshold_one_restricts_without_warning(self, mock_update, mock_context, mock_group_config):
        """When warning_threshold==1, first violation restricts without sending a separate warning."""
        mock_group_config.warning_threshold = 1
        db = MagicMock()
        db.is_user_restricted_by_bot.return_value = False
        db.get_or_create_user_warning.return_value.message_count = 1
        with (
            patch("bot.handlers.guest_bot.get_group_config_for_update", return_value=mock_group_config),
            patch("bot.handlers.guest_bot.is_user_admin_or_trusted", return_value=False),
            patch("bot.handlers.guest_bot.get_database", return_value=db),
            pytest.raises(ApplicationHandlerStop),
        ):
            await handle_guest_bot_message(mock_update, mock_context)
        mock_context.bot.restrict_chat_member.assert_awaited_once()
        db.mark_user_restricted.assert_called_once_with(
            123, mock_group_config.group_id, warning_kind="guest_bot"
        )
        db.increment_message_count.assert_not_called()

    async def test_chat_caller_is_deleted_only(self, mock_update, mock_context, mock_group_config):
        mock_update.message.guest_bot_caller_user = None
        mock_update.message.guest_bot_caller_chat = Chat(id=-1009, type="channel", title="Channel")
        with (
            patch("bot.handlers.guest_bot.get_group_config_for_update", return_value=mock_group_config),
            patch("bot.handlers.guest_bot.get_database") as get_db,
            pytest.raises(ApplicationHandlerStop),
        ):
            await handle_guest_bot_message(mock_update, mock_context)
        mock_update.message.delete.assert_awaited_once()
        get_db.assert_not_called()

    async def test_delete_failure_continues(self, mock_update, mock_context, mock_group_config):
        from telegram.error import BadRequest

        mock_update.message.delete.side_effect = BadRequest("delete failed")
        db = MagicMock()
        db.is_user_restricted_by_bot.return_value = False
        db.get_or_create_user_warning.return_value.message_count = 2
        with (
            patch("bot.handlers.guest_bot.get_group_config_for_update", return_value=mock_group_config),
            patch("bot.handlers.guest_bot.is_user_admin_or_trusted", return_value=False),
            patch("bot.handlers.guest_bot.get_database", return_value=db),
            pytest.raises(ApplicationHandlerStop),
        ):
            await handle_guest_bot_message(mock_update, mock_context)
        db.increment_message_count.assert_called_once()

    async def test_already_restricted_skips_warning(self, mock_update, mock_context, mock_group_config):
        db = MagicMock()
        db.is_user_restricted_by_bot.return_value = True
        with (
            patch("bot.handlers.guest_bot.get_group_config_for_update", return_value=mock_group_config),
            patch("bot.handlers.guest_bot.is_user_admin_or_trusted", return_value=False),
            patch("bot.handlers.guest_bot.get_database", return_value=db),
            pytest.raises(ApplicationHandlerStop),
        ):
            await handle_guest_bot_message(mock_update, mock_context)
        mock_update.message.delete.assert_awaited_once()
        db.get_or_create_user_warning.assert_not_called()
        db.increment_message_count.assert_not_called()
        db.mark_user_restricted.assert_not_called()
