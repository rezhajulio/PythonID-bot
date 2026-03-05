from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.ext import ApplicationHandlerStop

from bot.group_config import GroupConfig
from bot.handlers.topic_guard import guard_warning_topic


@pytest.fixture
def group_config():
    return GroupConfig(
        group_id=-1001234567890,
        warning_topic_id=42,
    )


@pytest.fixture
def mock_update():
    update = MagicMock()
    update.message = MagicMock()
    update.message.from_user = MagicMock()
    update.message.from_user.id = 12345
    update.message.from_user.full_name = "Test User"
    update.message.message_thread_id = 42
    update.message.delete = AsyncMock()
    update.edited_message = None
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
        update.edited_message = None

        await guard_warning_topic(update, mock_context)

        mock_context.bot.get_chat_member.assert_not_called()

    async def test_no_user(self, mock_context):
        update = MagicMock()
        update.message = MagicMock()
        update.message.from_user = None
        update.edited_message = None

        await guard_warning_topic(update, mock_context)

        mock_context.bot.get_chat_member.assert_not_called()

    async def test_wrong_group_ignored(self, mock_update, mock_context):
        mock_update.effective_chat.id = -100999999

        with patch("bot.handlers.topic_guard.get_group_config_for_update", return_value=None):
            await guard_warning_topic(mock_update, mock_context)

        mock_context.bot.get_chat_member.assert_not_called()
        mock_update.message.delete.assert_not_called()

    async def test_different_topic_ignored(
        self, mock_update, mock_context, group_config
    ):
        mock_update.message.message_thread_id = 999

        with patch("bot.handlers.topic_guard.get_group_config_for_update", return_value=group_config):
            await guard_warning_topic(mock_update, mock_context)

        mock_context.bot.get_chat_member.assert_not_called()
        mock_update.message.delete.assert_not_called()

    async def test_bot_message_allowed(self, mock_update, mock_context, group_config):
        mock_update.message.from_user.id = 99999  # Same as bot id

        with patch("bot.handlers.topic_guard.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await guard_warning_topic(mock_update, mock_context)

        mock_context.bot.get_chat_member.assert_not_called()
        mock_update.message.delete.assert_not_called()

    async def test_admin_message_allowed(
        self, mock_update, mock_context, group_config
    ):
        chat_member = MagicMock()
        chat_member.status = "administrator"
        mock_context.bot.get_chat_member.return_value = chat_member

        with patch("bot.handlers.topic_guard.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await guard_warning_topic(mock_update, mock_context)

        mock_context.bot.get_chat_member.assert_called_once_with(
            chat_id=-1001234567890,
            user_id=12345,
        )
        mock_update.message.delete.assert_not_called()

    async def test_creator_message_allowed(
        self, mock_update, mock_context, group_config
    ):
        chat_member = MagicMock()
        chat_member.status = "creator"
        mock_context.bot.get_chat_member.return_value = chat_member

        with patch("bot.handlers.topic_guard.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await guard_warning_topic(mock_update, mock_context)

        mock_update.message.delete.assert_not_called()

    async def test_regular_user_message_deleted(
        self, mock_update, mock_context, group_config
    ):
        chat_member = MagicMock()
        chat_member.status = "member"
        mock_context.bot.get_chat_member.return_value = chat_member

        with patch("bot.handlers.topic_guard.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await guard_warning_topic(mock_update, mock_context)

        mock_update.message.delete.assert_called_once()

    async def test_restricted_user_message_deleted(
        self, mock_update, mock_context, group_config
    ):
        chat_member = MagicMock()
        chat_member.status = "restricted"
        mock_context.bot.get_chat_member.return_value = chat_member

        with patch("bot.handlers.topic_guard.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await guard_warning_topic(mock_update, mock_context)

        mock_update.message.delete.assert_called_once()

    async def test_get_group_config_error_does_not_delete(
        self, mock_update, mock_context
    ):
        """Test that if get_group_config_for_update raises, message is NOT deleted."""
        with patch(
            "bot.handlers.topic_guard.get_group_config_for_update",
            side_effect=Exception("config lookup failed"),
        ):
            with pytest.raises(Exception, match="config lookup failed"):
                await guard_warning_topic(mock_update, mock_context)

        mock_update.message.delete.assert_not_called()


class TestGuardWarningTopicEditedMessage:
    async def test_edited_message_from_bot_allowed(self, mock_context, group_config):
        update = MagicMock()
        update.message = None
        update.edited_message = MagicMock()
        update.edited_message.from_user = MagicMock()
        update.edited_message.from_user.id = 99999  # bot id
        update.edited_message.from_user.full_name = "Bot"
        update.edited_message.message_thread_id = 42
        update.edited_message.delete = AsyncMock()
        update.effective_chat = MagicMock()
        update.effective_chat.id = -1001234567890

        with patch("bot.handlers.topic_guard.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await guard_warning_topic(update, mock_context)

        mock_context.bot.get_chat_member.assert_not_called()
        update.edited_message.delete.assert_not_called()

    async def test_edited_message_from_admin_allowed(self, mock_context, group_config):
        update = MagicMock()
        update.message = None
        update.edited_message = MagicMock()
        update.edited_message.from_user = MagicMock()
        update.edited_message.from_user.id = 12345
        update.edited_message.from_user.full_name = "Admin User"
        update.edited_message.message_thread_id = 42
        update.edited_message.delete = AsyncMock()
        update.effective_chat = MagicMock()
        update.effective_chat.id = -1001234567890

        chat_member = MagicMock()
        chat_member.status = "administrator"
        mock_context.bot.get_chat_member.return_value = chat_member

        with patch("bot.handlers.topic_guard.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await guard_warning_topic(update, mock_context)

        update.edited_message.delete.assert_not_called()

    async def test_edited_message_from_regular_user_deleted(self, mock_context, group_config):
        update = MagicMock()
        update.message = None
        update.edited_message = MagicMock()
        update.edited_message.from_user = MagicMock()
        update.edited_message.from_user.id = 12345
        update.edited_message.from_user.full_name = "Regular User"
        update.edited_message.message_thread_id = 42
        update.edited_message.delete = AsyncMock()
        update.effective_chat = MagicMock()
        update.effective_chat.id = -1001234567890

        chat_member = MagicMock()
        chat_member.status = "member"
        mock_context.bot.get_chat_member.return_value = chat_member

        with patch("bot.handlers.topic_guard.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await guard_warning_topic(update, mock_context)

        update.edited_message.delete.assert_called_once()


class TestGuardWarningTopicErrorHandling:
    async def test_get_chat_member_error_deletes_message(
        self, mock_update, mock_context, group_config
    ):
        """Test fail-closed: on get_chat_member error, message is still deleted."""
        mock_context.bot.get_chat_member.side_effect = Exception("API error")

        with patch("bot.handlers.topic_guard.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await guard_warning_topic(mock_update, mock_context)

        mock_update.message.delete.assert_called_once()

    async def test_delete_message_exception_still_raises_stop(
        self, mock_update, mock_context, group_config
    ):
        """Test when delete in normal flow raises, error handler still deletes and raises stop."""
        chat_member = MagicMock()
        chat_member.status = "member"
        mock_context.bot.get_chat_member.return_value = chat_member
        mock_update.message.delete.side_effect = Exception("delete error")

        with patch("bot.handlers.topic_guard.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await guard_warning_topic(mock_update, mock_context)

    async def test_error_recovery_delete_also_fails(
        self, mock_update, mock_context, group_config
    ):
        """Test when both get_chat_member and recovery delete fail, still raises stop."""
        mock_context.bot.get_chat_member.side_effect = Exception("API error")
        mock_update.message.delete.side_effect = Exception("delete also failed")

        with patch("bot.handlers.topic_guard.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await guard_warning_topic(mock_update, mock_context)

        mock_update.message.delete.assert_called_once()
