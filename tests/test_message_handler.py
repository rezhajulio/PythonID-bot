import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.database.service import init_database, reset_database
from bot.group_config import GroupConfig
from bot.handlers.message import handle_message
from bot.services.user_checker import ProfileCheckResult


@pytest.fixture
def group_config():
    return GroupConfig(
        group_id=-1001234567890,
        warning_topic_id=42,
        restrict_failed_users=False,
        warning_time_threshold_minutes=180,
        warning_threshold=3,
        rules_link="https://example.com/rules",
    )


@pytest.fixture
def mock_update():
    update = MagicMock()
    update.message = MagicMock()
    update.message.from_user = MagicMock()
    update.message.from_user.id = 12345
    update.message.from_user.username = "testuser"
    update.message.from_user.full_name = "Test User"
    update.message.from_user.is_bot = False
    update.effective_chat = MagicMock()
    update.effective_chat.id = -1001234567890
    return update


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.bot = AsyncMock()
    return context


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_database(str(db_path))
        yield db_path
        reset_database()


class TestHandleMessage:
    async def test_no_message(self, mock_context):
        update = MagicMock()
        update.message = None

        await handle_message(update, mock_context)

        mock_context.bot.send_message.assert_not_called()

    async def test_no_user(self, mock_context):
        update = MagicMock()
        update.message = MagicMock()
        update.message.from_user = None

        await handle_message(update, mock_context)

        mock_context.bot.send_message.assert_not_called()

    async def test_wrong_group(self, mock_update, mock_context):
        mock_update.effective_chat.id = -100999999  # Different group

        with patch("bot.handlers.message.get_group_config_for_update", return_value=None):
            await handle_message(mock_update, mock_context)

        mock_context.bot.send_message.assert_not_called()

    async def test_bot_user_ignored(self, mock_update, mock_context, group_config):
        mock_update.message.from_user.is_bot = True

        with patch("bot.handlers.message.get_group_config_for_update", return_value=group_config):
            await handle_message(mock_update, mock_context)

        mock_context.bot.send_message.assert_not_called()

    async def test_complete_profile_no_warning(
        self, mock_update, mock_context, group_config
    ):
        complete_result = ProfileCheckResult(has_profile_photo=True, has_username=True)

        with (
            patch("bot.handlers.message.get_group_config_for_update", return_value=group_config),
            patch(
                "bot.handlers.message.check_user_profile",
                return_value=complete_result,
            ),
        ):
            await handle_message(mock_update, mock_context)

        mock_context.bot.send_message.assert_not_called()

    async def test_missing_photo_sends_warning(
        self, mock_update, mock_context, group_config
    ):
        incomplete_result = ProfileCheckResult(
            has_profile_photo=False, has_username=True
        )

        with (
            patch("bot.handlers.message.get_group_config_for_update", return_value=group_config),
            patch(
                "bot.handlers.message.check_user_profile",
                return_value=incomplete_result,
            ),
        ):
            await handle_message(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert call_args.kwargs["chat_id"] == -1001234567890
        assert call_args.kwargs["message_thread_id"] == 42
        assert "foto profil publik" in call_args.kwargs["text"]

    async def test_missing_username_sends_warning(
        self, mock_update, mock_context, group_config
    ):
        mock_update.message.from_user.username = None
        incomplete_result = ProfileCheckResult(
            has_profile_photo=True, has_username=False
        )

        with (
            patch("bot.handlers.message.get_group_config_for_update", return_value=group_config),
            patch(
                "bot.handlers.message.check_user_profile",
                return_value=incomplete_result,
            ),
        ):
            await handle_message(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert "username" in call_args.kwargs["text"]
        assert "Test User" in call_args.kwargs["text"]

    async def test_missing_both_sends_warning(
        self, mock_update, mock_context, group_config
    ):
        mock_update.message.from_user.username = None
        incomplete_result = ProfileCheckResult(
            has_profile_photo=False, has_username=False
        )

        with (
            patch("bot.handlers.message.get_group_config_for_update", return_value=group_config),
            patch(
                "bot.handlers.message.check_user_profile",
                return_value=incomplete_result,
            ),
        ):
            await handle_message(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert "foto profil publik" in call_args.kwargs["text"]
        assert "username" in call_args.kwargs["text"]

    async def test_warning_mentions_username_when_available(
        self, mock_update, mock_context, group_config
    ):
        mock_update.message.from_user.username = "cooluser"
        incomplete_result = ProfileCheckResult(
            has_profile_photo=False, has_username=True
        )

        with (
            patch("bot.handlers.message.get_group_config_for_update", return_value=group_config),
            patch(
                "bot.handlers.message.check_user_profile",
                return_value=incomplete_result,
            ),
        ):
            await handle_message(mock_update, mock_context)

        call_args = mock_context.bot.send_message.call_args
        assert "@cooluser" in call_args.kwargs["text"]


class TestHandleMessageWithProgressiveRestriction:
    @pytest.fixture
    def group_config_with_restriction(self):
        return GroupConfig(
            group_id=-1001234567890,
            warning_topic_id=42,
            restrict_failed_users=True,
            warning_threshold=3,
            warning_time_threshold_minutes=180,
            rules_link="https://example.com/rules",
        )

    async def test_first_message_sends_warning(
        self, mock_update, mock_context, group_config_with_restriction, temp_db
    ):
        incomplete_result = ProfileCheckResult(
            has_profile_photo=False, has_username=True
        )

        with (
            patch(
                "bot.handlers.message.get_group_config_for_update",
                return_value=group_config_with_restriction,
            ),
            patch(
                "bot.handlers.message.check_user_profile",
                return_value=incomplete_result,
            ),
        ):
            await handle_message(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert "⚠️" in call_args.kwargs["text"]
        assert "dibatasi setelah 3 pesan" in call_args.kwargs["text"]
        mock_context.bot.restrict_chat_member.assert_not_called()

    async def test_second_message_silent(
        self, mock_update, mock_context, group_config_with_restriction, temp_db
    ):
        incomplete_result = ProfileCheckResult(
            has_profile_photo=False, has_username=True
        )

        with (
            patch(
                "bot.handlers.message.get_group_config_for_update",
                return_value=group_config_with_restriction,
            ),
            patch(
                "bot.handlers.message.check_user_profile",
                return_value=incomplete_result,
            ),
        ):
            # First message - warning
            await handle_message(mock_update, mock_context)
            mock_context.bot.send_message.reset_mock()

            # Second message - silent
            await handle_message(mock_update, mock_context)

        mock_context.bot.send_message.assert_not_called()
        mock_context.bot.restrict_chat_member.assert_not_called()

    async def test_threshold_message_restricts_user(
        self, mock_update, mock_context, group_config_with_restriction, temp_db
    ):
        incomplete_result = ProfileCheckResult(
            has_profile_photo=False, has_username=True
        )

        with (
            patch(
                "bot.handlers.message.get_group_config_for_update",
                return_value=group_config_with_restriction,
            ),
            patch(
                "bot.handlers.message.check_user_profile",
                return_value=incomplete_result,
            ),
        ):
            # Messages 1, 2, 3
            for _ in range(3):
                await handle_message(mock_update, mock_context)

        mock_context.bot.restrict_chat_member.assert_called_once()
        restrict_args = mock_context.bot.restrict_chat_member.call_args
        assert restrict_args.kwargs["chat_id"] == -1001234567890
        assert restrict_args.kwargs["user_id"] == 12345

        # Check last message was restriction notice
        call_args = mock_context.bot.send_message.call_args
        assert "🚫" in call_args.kwargs["text"]
        assert "dibatasi" in call_args.kwargs["text"]

    async def test_no_restriction_when_disabled(
        self, mock_update, mock_context, group_config
    ):
        incomplete_result = ProfileCheckResult(
            has_profile_photo=False, has_username=True
        )

        with (
            patch("bot.handlers.message.get_group_config_for_update", return_value=group_config),
            patch(
                "bot.handlers.message.check_user_profile",
                return_value=incomplete_result,
            ),
        ):
            await handle_message(mock_update, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()
        call_args = mock_context.bot.send_message.call_args
        assert "⚠️" in call_args.kwargs["text"]

    async def test_different_users_tracked_separately(
        self, mock_update, mock_context, group_config_with_restriction, temp_db
    ):
        incomplete_result = ProfileCheckResult(
            has_profile_photo=False, has_username=True
        )

        with (
            patch(
                "bot.handlers.message.get_group_config_for_update",
                return_value=group_config_with_restriction,
            ),
            patch(
                "bot.handlers.message.check_user_profile",
                return_value=incomplete_result,
            ),
        ):
            # User 1 - 2 messages
            mock_update.message.from_user.id = 111
            await handle_message(mock_update, mock_context)
            await handle_message(mock_update, mock_context)

            # User 2 - 1 message (should get warning)
            mock_update.message.from_user.id = 222
            mock_context.bot.send_message.reset_mock()
            await handle_message(mock_update, mock_context)

        # User 2 should have received first warning
        mock_context.bot.send_message.assert_called_once()
        assert "⚠️" in mock_context.bot.send_message.call_args.kwargs["text"]


class TestHandleMessageErrorHandling:
    async def test_send_warning_message_fails(self, mock_update, mock_context, group_config):
        """Test when sending warning message fails (lines 110-111)."""
        incomplete_result = ProfileCheckResult(
            has_profile_photo=False, has_username=True
        )
        mock_context.bot.send_message.side_effect = Exception("test error")

        with (
            patch("bot.handlers.message.get_group_config_for_update", return_value=group_config),
            patch(
                "bot.handlers.message.check_user_profile",
                return_value=incomplete_result,
            ),
        ):
            # Should not raise, error is caught and logged
            await handle_message(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()

    async def test_send_first_warning_fails(
        self, mock_update, mock_context, temp_db
    ):
        """Test when sending first warning fails (lines 146-147)."""
        gc = GroupConfig(
            group_id=-1001234567890,
            warning_topic_id=42,
            restrict_failed_users=True,
            warning_threshold=3,
            warning_time_threshold_minutes=180,
            rules_link="https://example.com/rules",
        )

        incomplete_result = ProfileCheckResult(
            has_profile_photo=False, has_username=True
        )
        mock_context.bot.send_message.side_effect = Exception("test error")

        with (
            patch("bot.handlers.message.get_group_config_for_update", return_value=gc),
            patch(
                "bot.handlers.message.check_user_profile",
                return_value=incomplete_result,
            ),
        ):
            # Should not raise, error is caught and logged
            await handle_message(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()

    async def test_restrict_user_fails(
        self, mock_update, mock_context, temp_db
    ):
        """Test when restricting user fails (lines 193-194)."""
        gc = GroupConfig(
            group_id=-1001234567890,
            warning_topic_id=42,
            restrict_failed_users=True,
            warning_threshold=3,
            warning_time_threshold_minutes=180,
            rules_link="https://example.com/rules",
        )

        incomplete_result = ProfileCheckResult(
            has_profile_photo=False, has_username=True
        )
        mock_context.bot.restrict_chat_member.side_effect = Exception("test error")

        with (
            patch("bot.handlers.message.get_group_config_for_update", return_value=gc),
            patch(
                "bot.handlers.message.check_user_profile",
                return_value=incomplete_result,
            ),
        ):
            # First two messages increment count
            await handle_message(mock_update, mock_context)
            await handle_message(mock_update, mock_context)
            mock_context.bot.send_message.reset_mock()

            # Third message triggers restriction which fails
            await handle_message(mock_update, mock_context)

        # restrict_chat_member should have been called and failed
        mock_context.bot.restrict_chat_member.assert_called_once()
