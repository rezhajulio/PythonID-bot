from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.handlers.topic_guard import guard_warning_topic


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.group_id = -1001234567890
    settings.warning_topic_id = 42
    return settings


@pytest.fixture
def mock_update():
    update = MagicMock()
    update.message = MagicMock()
    update.message.from_user = MagicMock()
    update.message.from_user.id = 12345
    update.message.from_user.full_name = "Test User"
    update.message.message_thread_id = 42
    update.message.delete = AsyncMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = -1001234567890
    return update


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.bot = AsyncMock()
    context.bot.id = 99999
    return context


class TestGuardWarningTopic:
    async def test_no_message(self, mock_context):
        update = MagicMock()
        update.message = None

        await guard_warning_topic(update, mock_context)

        mock_context.bot.get_chat_member.assert_not_called()

    async def test_no_user(self, mock_context):
        update = MagicMock()
        update.message = MagicMock()
        update.message.from_user = None

        await guard_warning_topic(update, mock_context)

        mock_context.bot.get_chat_member.assert_not_called()

    async def test_wrong_group_ignored(self, mock_update, mock_context, mock_settings):
        mock_update.effective_chat.id = -100999999

        with patch("bot.handlers.topic_guard.get_settings", return_value=mock_settings):
            await guard_warning_topic(mock_update, mock_context)

        mock_context.bot.get_chat_member.assert_not_called()
        mock_update.message.delete.assert_not_called()

    async def test_different_topic_ignored(
        self, mock_update, mock_context, mock_settings
    ):
        mock_update.message.message_thread_id = 999

        with patch("bot.handlers.topic_guard.get_settings", return_value=mock_settings):
            await guard_warning_topic(mock_update, mock_context)

        mock_context.bot.get_chat_member.assert_not_called()
        mock_update.message.delete.assert_not_called()

    async def test_bot_message_allowed(self, mock_update, mock_context, mock_settings):
        mock_update.message.from_user.id = 99999  # Same as bot id

        with patch("bot.handlers.topic_guard.get_settings", return_value=mock_settings):
            await guard_warning_topic(mock_update, mock_context)

        mock_context.bot.get_chat_member.assert_not_called()
        mock_update.message.delete.assert_not_called()

    async def test_admin_message_allowed(
        self, mock_update, mock_context, mock_settings
    ):
        chat_member = MagicMock()
        chat_member.status = "administrator"
        mock_context.bot.get_chat_member.return_value = chat_member

        with patch("bot.handlers.topic_guard.get_settings", return_value=mock_settings):
            await guard_warning_topic(mock_update, mock_context)

        mock_context.bot.get_chat_member.assert_called_once_with(
            chat_id=-1001234567890,
            user_id=12345,
        )
        mock_update.message.delete.assert_not_called()

    async def test_creator_message_allowed(
        self, mock_update, mock_context, mock_settings
    ):
        chat_member = MagicMock()
        chat_member.status = "creator"
        mock_context.bot.get_chat_member.return_value = chat_member

        with patch("bot.handlers.topic_guard.get_settings", return_value=mock_settings):
            await guard_warning_topic(mock_update, mock_context)

        mock_update.message.delete.assert_not_called()

    async def test_regular_user_message_deleted(
        self, mock_update, mock_context, mock_settings
    ):
        chat_member = MagicMock()
        chat_member.status = "member"
        mock_context.bot.get_chat_member.return_value = chat_member

        with patch("bot.handlers.topic_guard.get_settings", return_value=mock_settings):
            await guard_warning_topic(mock_update, mock_context)

        mock_update.message.delete.assert_called_once()

    async def test_restricted_user_message_deleted(
        self, mock_update, mock_context, mock_settings
    ):
        chat_member = MagicMock()
        chat_member.status = "restricted"
        mock_context.bot.get_chat_member.return_value = chat_member

        with patch("bot.handlers.topic_guard.get_settings", return_value=mock_settings):
            await guard_warning_topic(mock_update, mock_context)

        mock_update.message.delete.assert_called_once()


class TestGuardWarningTopicErrorHandling:
    async def test_delete_message_exception_logged(
        self, mock_update, mock_context, mock_settings
    ):
        """Test when update.message.delete() raises an exception (lines 91-92)."""
        chat_member = MagicMock()
        chat_member.status = "member"
        mock_context.bot.get_chat_member.return_value = chat_member
        mock_update.message.delete.side_effect = Exception("test error")

        with patch("bot.handlers.topic_guard.get_settings", return_value=mock_settings):
            # Should not raise, error is caught and logged
            await guard_warning_topic(mock_update, mock_context)

        mock_update.message.delete.assert_called_once()
