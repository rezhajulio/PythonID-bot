"""Tests for admin check handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import TimedOut

from bot.group_config import GroupConfig, GroupRegistry
from bot.handlers.check import (
    _parse_warn_callback_data,
    handle_check_command,
    handle_check_forwarded_message,
    handle_check_group_callback,
    handle_warn_callback,
)
from bot.services.user_checker import ProfileCheckResult


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.group_id = -1001234567890
    settings.warning_topic_id = 12345
    settings.rules_link = "https://t.me/test/rules"
    return settings


@pytest.fixture
def group_config():
    return GroupConfig(
        group_id=-1001234567890,
        warning_topic_id=12345,
        rules_link="https://t.me/test/rules",
    )


@pytest.fixture
def mock_registry(group_config):
    registry = GroupRegistry()
    registry.register(group_config)
    return registry


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
    update.message.forward_origin = None
    update.message.forward_from = None
    return update


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.bot = MagicMock()
    context.bot.get_chat = AsyncMock()
    context.bot.get_user_profile_photos = AsyncMock()
    context.bot.send_message = AsyncMock()

    mock_chat = MagicMock()
    mock_chat.full_name = "Test User"
    mock_chat.username = "testuser"
    context.bot.get_chat.return_value = mock_chat

    context.bot_data = {
        "admin_ids": [12345],
        "group_admin_ids": {-1001234567890: [12345]},
    }
    context.args = []
    return context


class TestHandleCheckCommand:
    async def test_check_command_non_admin(self, mock_update, mock_context):
        """Non-admin cannot use /check."""
        mock_update.message.from_user.id = 99999
        mock_context.bot_data = {
            "admin_ids": [12345],
            "group_admin_ids": {-1001234567890: []},
        }
        mock_context.args = ["123456"]

        await handle_check_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "izin" in call_args.args[0]

    async def test_check_command_missing_user_id(self, mock_update, mock_context):
        """Missing user ID shows usage."""
        mock_context.args = []

        await handle_check_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "/check USER_ID" in call_args.args[0]

    async def test_check_command_invalid_user_id(self, mock_update, mock_context):
        """Invalid user ID shows error."""
        mock_context.args = ["not_a_number"]

        await handle_check_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "angka" in call_args.args[0]

    async def test_check_command_complete_profile(self, mock_update, mock_context):
        """Shows complete profile with a Trust button for non-trusted users."""
        mock_context.args = ["555666"]

        complete_result = ProfileCheckResult(
            has_profile_photo=True, has_username=True
        )

        mock_db = MagicMock()
        mock_db.is_user_photo_whitelisted.return_value = False
        mock_db.is_user_trusted.return_value = False

        with (
            patch(
                "bot.handlers.check.check_user_profile",
                return_value=complete_result,
            ),
            patch("bot.handlers.check.get_database", return_value=mock_db),
        ):
            await handle_check_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "555666" in call_args.args[0]
        assert "\u2705" in call_args.args[0]
        keyboard = call_args.kwargs.get("reply_markup")
        assert keyboard is not None
        buttons = keyboard.inline_keyboard[0]
        callback_data = [btn.callback_data for btn in buttons]
        assert any(data == "trust:-1001234567890:555666" for data in callback_data)
        assert not any("unverify" in data for data in callback_data)

    async def test_check_command_complete_profile_shows_trust_button_when_not_trusted(
        self, mock_update, mock_context
    ):
        """Shows trust button on complete-profile branch for non-trusted users."""
        mock_context.args = ["555666"]

        complete_result = ProfileCheckResult(
            has_profile_photo=True, has_username=True
        )

        mock_db = MagicMock()
        mock_db.is_user_photo_whitelisted.return_value = False
        mock_db.is_user_trusted.return_value = False

        with (
            patch("bot.handlers.check.check_user_profile", return_value=complete_result),
            patch("bot.handlers.check.get_database", return_value=mock_db),
        ):
            await handle_check_command(mock_update, mock_context)

        keyboard = mock_update.message.reply_text.call_args.kwargs.get("reply_markup")
        assert keyboard is not None
        buttons = keyboard.inline_keyboard[0]
        callback_data = [btn.callback_data for btn in buttons]
        assert any(data == "trust:-1001234567890:555666" for data in callback_data)

    async def test_check_command_complete_profile_whitelisted(
        self, mock_update, mock_context
    ):
        """Shows complete profile with unverify button when user is whitelisted."""
        mock_context.args = ["555666"]

        complete_result = ProfileCheckResult(
            has_profile_photo=True, has_username=True
        )

        mock_db = MagicMock()
        mock_db.is_user_photo_whitelisted.return_value = True

        with (
            patch(
                "bot.handlers.check.check_user_profile",
                return_value=complete_result,
            ),
            patch("bot.handlers.check.get_database", return_value=mock_db),
        ):
            await handle_check_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "555666" in call_args.args[0]
        assert "\u2705" in call_args.args[0]
        keyboard = call_args.kwargs.get("reply_markup")
        assert keyboard is not None
        buttons = keyboard.inline_keyboard[0]
        assert any(
            btn.callback_data == "unverify:-1001234567890:555666"
            for btn in buttons
        )
        assert any("Cabut izin foto" in btn.text for btn in buttons)

    async def test_check_command_multiple_admin_groups_shows_group_selector(
        self, mock_update, mock_context
    ):
        """Admins of multiple groups choose the group before acting."""
        mock_context.args = ["555666"]
        mock_context.bot_data["group_admin_ids"] = {
            -1001234567890: [12345],
            -1009876543210: [12345],
        }
        result = ProfileCheckResult(has_profile_photo=True, has_username=True)
        mock_db = MagicMock()
        mock_db.is_user_photo_whitelisted.return_value = False
        mock_db.is_user_trusted.return_value = False

        with (
            patch("bot.handlers.check.check_user_profile", return_value=result),
            patch("bot.handlers.check.get_database", return_value=mock_db),
        ):
            await handle_check_command(mock_update, mock_context)

        keyboard = mock_update.message.reply_text.call_args.kwargs["reply_markup"]
        callback_data = [row[0].callback_data for row in keyboard.inline_keyboard]
        assert callback_data == [
            "checkgrp:-1001234567890:555666",
            "checkgrp:-1009876543210:555666",
        ]

    async def test_check_command_incomplete_profile(self, mock_update, mock_context):
        """Shows incomplete profile with warn button."""
        mock_context.args = ["555666"]

        incomplete_result = ProfileCheckResult(
            has_profile_photo=False, has_username=False
        )

        mock_db = MagicMock()
        mock_db.is_user_photo_whitelisted.return_value = False
        mock_db.is_user_trusted.return_value = False

        with (
            patch(
                "bot.handlers.check.check_user_profile",
                return_value=incomplete_result,
            ),
            patch("bot.handlers.check.get_database", return_value=mock_db),
        ):
            await handle_check_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "555666" in call_args.args[0]
        assert "\u274c" in call_args.args[0]
        keyboard = call_args.kwargs.get("reply_markup")
        assert keyboard is not None
        buttons = keyboard.inline_keyboard[0]
        callback_data = [btn.callback_data for btn in buttons]
        assert "warn:-1001234567890:555666:pu" in callback_data
        assert "verify:-1001234567890:555666" in callback_data

    async def test_check_command_incomplete_profile_shows_trust_button(
        self, mock_update, mock_context
    ):
        """Shows trust button for incomplete non-trusted users."""
        mock_context.args = ["555666"]

        incomplete_result = ProfileCheckResult(
            has_profile_photo=False, has_username=False
        )

        mock_db = MagicMock()
        mock_db.is_user_photo_whitelisted.return_value = False
        mock_db.is_user_trusted.return_value = False

        with (
            patch("bot.handlers.check.check_user_profile", return_value=incomplete_result),
            patch("bot.handlers.check.get_database", return_value=mock_db),
        ):
            await handle_check_command(mock_update, mock_context)

        keyboard = mock_update.message.reply_text.call_args.kwargs.get("reply_markup")
        assert keyboard is not None
        buttons = [button for row in keyboard.inline_keyboard for button in row]
        callback_data = [btn.callback_data for btn in buttons]
        assert "trust:-1001234567890:555666" in callback_data

    async def test_check_command_complete_profile_shows_untrust_button_when_trusted(
        self, mock_update, mock_context
    ):
        """Shows untrust button for trusted users."""
        mock_context.args = ["555666"]

        complete_result = ProfileCheckResult(
            has_profile_photo=True, has_username=True
        )

        mock_db = MagicMock()
        mock_db.is_user_photo_whitelisted.return_value = False
        mock_db.is_user_trusted.return_value = True

        with (
            patch("bot.handlers.check.check_user_profile", return_value=complete_result),
            patch("bot.handlers.check.get_database", return_value=mock_db),
        ):
            await handle_check_command(mock_update, mock_context)

        keyboard = mock_update.message.reply_text.call_args.kwargs.get("reply_markup")
        assert keyboard is not None
        buttons = keyboard.inline_keyboard[0]
        callback_data = [btn.callback_data for btn in buttons]
        assert any(
            data == "untrust:-1001234567890:555666" for data in callback_data
        )

    async def test_check_command_only_private(self, mock_update, mock_context):
        """Command only works in private chat."""
        mock_update.effective_chat.type = "group"
        mock_context.args = ["123456"]

        await handle_check_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "chat pribadi" in call_args.args[0]

    async def test_check_command_no_message(self, mock_context):
        """Returns early if no message."""
        update = MagicMock()
        update.message = None

        await handle_check_command(update, mock_context)

    async def test_check_command_no_from_user(self, mock_context):
        """Returns early if no from_user."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.from_user = None

        await handle_check_command(update, mock_context)

    async def test_check_command_get_chat_error(self, mock_update, mock_context):
        """Handles get_chat error gracefully."""
        mock_context.args = ["555666"]
        mock_context.bot.get_chat.side_effect = Exception("User not found")

        await handle_check_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "Gagal memeriksa" in call_args.args[0]

    async def test_check_command_timeout(self, mock_update, mock_context):
        """Handles TimedOut error gracefully."""
        mock_context.args = ["555666"]
        mock_context.bot.get_chat.side_effect = TimedOut()

        await handle_check_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "timeout" in call_args.args[0].lower()


class TestHandleCheckForwardedMessage:
    async def test_check_forwarded_non_admin(self, mock_update, mock_context):
        """Forwarded checks show no available groups for a non-admin."""
        mock_update.message.from_user.id = 99999
        mock_context.bot_data = {
            "admin_ids": [12345],
            "group_admin_ids": {-1001234567890: []},
        }

        forwarded_user = MagicMock()
        forwarded_user.id = 555666
        forwarded_user.full_name = "Forwarded User"
        mock_update.message.forward_from = forwarded_user

        result = ProfileCheckResult(has_profile_photo=True, has_username=True)
        mock_db = MagicMock()
        mock_db.is_user_photo_whitelisted.return_value = False
        mock_db.is_user_trusted.return_value = False

        with (
            patch("bot.handlers.check.check_user_profile", return_value=result),
            patch("bot.handlers.check.get_database", return_value=mock_db),
        ):
            await handle_check_forwarded_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "admin" in call_args.args[0]

    async def test_check_forwarded_hidden_user(self, mock_update, mock_context):
        """Hidden forward privacy shows error."""
        mock_update.message.forward_origin = None
        mock_update.message.forward_from = None

        await handle_check_forwarded_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "Tidak dapat mengekstrak" in call_args.args[0]

    async def test_check_forwarded_success(self, mock_update, mock_context):
        """Successfully checks forwarded user."""
        forwarded_user = MagicMock()
        forwarded_user.id = 555666
        forwarded_user.full_name = "Forwarded User"
        mock_update.message.forward_from = forwarded_user

        complete_result = ProfileCheckResult(
            has_profile_photo=True, has_username=True
        )

        mock_db = MagicMock()
        mock_db.is_user_photo_whitelisted.return_value = False

        with (
            patch(
                "bot.handlers.check.check_user_profile",
                return_value=complete_result,
            ),
            patch("bot.handlers.check.get_database", return_value=mock_db),
        ):
            await handle_check_forwarded_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "555666" in call_args.args[0]

    async def test_check_forwarded_with_forward_origin(
        self, mock_update, mock_context
    ):
        """Successfully checks forwarded user via forward_origin."""
        forwarded_user = MagicMock()
        forwarded_user.id = 555666
        forwarded_user.full_name = "Forwarded User"

        forward_origin = MagicMock()
        forward_origin.sender_user = forwarded_user
        mock_update.message.forward_origin = forward_origin
        mock_update.message.forward_from = None

        complete_result = ProfileCheckResult(
            has_profile_photo=True, has_username=True
        )

        mock_db = MagicMock()
        mock_db.is_user_photo_whitelisted.return_value = False

        with (
            patch(
                "bot.handlers.check.check_user_profile",
                return_value=complete_result,
            ),
            patch("bot.handlers.check.get_database", return_value=mock_db),
        ):
            await handle_check_forwarded_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()

    async def test_check_forwarded_no_message(self, mock_context):
        """Returns early if no message."""
        update = MagicMock()
        update.message = None

        await handle_check_forwarded_message(update, mock_context)

    async def test_check_forwarded_no_from_user(self, mock_context):
        """Returns early if no from_user."""
        update = MagicMock()
        update.message = MagicMock()
        update.message.from_user = None

        await handle_check_forwarded_message(update, mock_context)

    async def test_check_forwarded_error(self, mock_update, mock_context):
        """Handles error gracefully when checking forwarded user."""
        forwarded_user = MagicMock()
        forwarded_user.id = 555666
        forwarded_user.full_name = "Forwarded User"
        mock_update.message.forward_from = forwarded_user

        mock_context.bot.get_chat.side_effect = Exception("User not found")

        await handle_check_forwarded_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "Gagal memeriksa" in call_args.args[0]

    async def test_check_forwarded_timeout(self, mock_update, mock_context):
        """Handles TimedOut error gracefully."""
        forwarded_user = MagicMock()
        forwarded_user.id = 555666
        forwarded_user.full_name = "Forwarded User"
        mock_update.message.forward_from = forwarded_user

        mock_context.bot.get_chat.side_effect = TimedOut()

        await handle_check_forwarded_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "timeout" in call_args.args[0].lower()


class TestHandleCheckGroupCallback:
    async def test_group_callback_shows_group_scoped_actions(self, mock_context):
        """A group selection displays actions encoded for that group."""
        update = MagicMock()
        update.message = None
        query = MagicMock()
        query.from_user.id = 12345
        query.data = "checkgrp:-1001234567890:555666"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query
        result = ProfileCheckResult(has_profile_photo=False, has_username=True)
        mock_db = MagicMock()
        mock_db.is_user_photo_whitelisted.return_value = False
        mock_db.is_user_trusted.return_value = False

        with (
            patch("bot.handlers.check.check_user_profile", return_value=result),
            patch("bot.handlers.check.get_database", return_value=mock_db),
        ):
            await handle_check_group_callback(update, mock_context)

        query.answer.assert_awaited_once()
        keyboard = query.edit_message_text.call_args.kwargs["reply_markup"]
        callback_data = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
        ]
        assert "warn:-1001234567890:555666:p" in callback_data
        assert "verify:-1001234567890:555666" in callback_data
        assert "unrestrict:-1001234567890:555666" in callback_data

    async def test_group_callback_rejects_non_admin(self, mock_context):
        """A caller must be an admin of the selected group."""
        update = MagicMock()
        query = MagicMock()
        query.from_user.id = 99999
        query.data = "checkgrp:-1001234567890:555666"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query

        await handle_check_group_callback(update, mock_context)

        query.edit_message_text.assert_awaited_once()
        assert "bukan admin" in query.edit_message_text.call_args.args[0]
        mock_context.bot.get_chat.assert_not_awaited()

    async def test_group_callback_rejects_invalid_data(self, mock_context):
        """Malformed group callback data is rejected."""
        update = MagicMock()
        query = MagicMock()
        query.from_user.id = 12345
        query.data = "checkgrp:invalid"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query

        await handle_check_group_callback(update, mock_context)

        assert "tidak valid" in query.edit_message_text.call_args.args[0]


class TestHandleWarnCallback:
    def test_parse_warn_callback_data_includes_group_id(self):
        """Warn callback parsing preserves group, user, and missing code."""
        assert _parse_warn_callback_data("warn:-1001234567890:555666:pu") == (
            -1001234567890,
            555666,
            "pu",
        )
        assert _parse_warn_callback_data("warn:invalid") is None

    async def test_warn_callback_non_admin(self, mock_context):
        """Non-admin cannot use warn callback."""
        update = MagicMock()
        query = MagicMock()
        query.from_user = MagicMock()
        query.from_user.id = 99999
        query.from_user.full_name = "Non Admin"
        query.data = "warn:-1001234567890:555666:pu"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query

        mock_context.bot_data = {
            "group_admin_ids": {-1001234567890: []},
        }

        await handle_warn_callback(update, mock_context)

        query.answer.assert_called_once()
        query.edit_message_text.assert_called_once()
        call_args = query.edit_message_text.call_args
        assert "bukan admin" in call_args.args[0]

    async def test_warn_callback_success(
        self, mock_context, mock_settings, group_config, mock_registry
    ):
        """Successfully sends warning to the selected group."""
        update = MagicMock()
        query = MagicMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.full_name = "Admin User"
        query.data = "warn:-1001234567890:555666:pu"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query

        mock_chat = MagicMock()
        mock_chat.full_name = "Test User"
        mock_chat.username = "testuser"
        mock_context.bot.get_chat.return_value = mock_chat

        with (
            patch(
                "bot.handlers.check.get_group_registry",
                return_value=mock_registry,
            ),
        ):
            await handle_warn_callback(update, mock_context)

        query.answer.assert_called_once()
        mock_context.bot.send_message.assert_called_once()
        send_call_args = mock_context.bot.send_message.call_args
        assert send_call_args.kwargs["chat_id"] == group_config.group_id
        assert (
            send_call_args.kwargs["message_thread_id"]
            == group_config.warning_topic_id
        )
        assert "foto profil publik" in send_call_args.kwargs["text"]
        assert "username" in send_call_args.kwargs["text"]

        query.edit_message_text.assert_called_once()
        edit_call_args = query.edit_message_text.call_args
        assert "dikirim" in edit_call_args.args[0]

    async def test_warn_callback_success_missing_photo_only(
        self, mock_context, mock_settings, group_config, mock_registry
    ):
        """Successfully sends warning for missing photo only."""
        update = MagicMock()
        query = MagicMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.full_name = "Admin User"
        query.data = "warn:-1001234567890:555666:p"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query

        mock_chat = MagicMock()
        mock_chat.full_name = "Test User"
        mock_chat.username = "testuser"
        mock_context.bot.get_chat.return_value = mock_chat

        with (
            patch(
                "bot.handlers.check.get_group_registry",
                return_value=mock_registry,
            ),
        ):
            await handle_warn_callback(update, mock_context)

        send_call_args = mock_context.bot.send_message.call_args
        assert "foto profil publik" in send_call_args.kwargs["text"]
        assert "@testuser" in send_call_args.kwargs["text"]

    async def test_warn_callback_invalid_data(self, mock_context):
        """Invalid callback data shows error."""
        update = MagicMock()
        query = MagicMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.full_name = "Admin User"
        query.data = "warn:invalid"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query

        await handle_warn_callback(update, mock_context)

        query.answer.assert_called_once()
        query.edit_message_text.assert_called_once()
        call_args = query.edit_message_text.call_args
        assert "tidak valid" in call_args.args[0]

    async def test_warn_callback_no_query(self, mock_context):
        """Returns early if no callback query."""
        update = MagicMock()
        update.callback_query = None

        await handle_warn_callback(update, mock_context)

    async def test_warn_callback_no_from_user(self, mock_context):
        """Returns early if no from_user."""
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.from_user = None

        await handle_warn_callback(update, mock_context)

    async def test_warn_callback_no_data(self, mock_context):
        """Returns early if no callback data."""
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.from_user = MagicMock()
        update.callback_query.data = None

        await handle_warn_callback(update, mock_context)

    async def test_warn_callback_send_message_error(
        self, mock_context, mock_settings, mock_registry
    ):
        """Handles send_message error gracefully."""
        update = MagicMock()
        query = MagicMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.full_name = "Admin User"
        query.data = "warn:-1001234567890:555666:pu"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query

        mock_chat = MagicMock()
        mock_chat.full_name = "Test User"
        mock_context.bot.get_chat.return_value = mock_chat
        mock_context.bot.send_message.side_effect = Exception("Failed to send")

        with (
            patch(
                "bot.handlers.check.get_group_registry",
                return_value=mock_registry,
            ),
        ):
            await handle_warn_callback(update, mock_context)

        query.edit_message_text.assert_called_once()
        call_args = query.edit_message_text.call_args
        assert "Gagal mengirim" in call_args.args[0]

    async def test_warn_callback_timeout(
        self, mock_context, mock_settings, mock_registry
    ):
        """Handles TimedOut error gracefully (per-group failure)."""
        update = MagicMock()
        query = MagicMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.full_name = "Admin User"
        query.data = "warn:-1001234567890:555666:pu"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query

        mock_chat = MagicMock()
        mock_chat.full_name = "Test User"
        mock_context.bot.get_chat.return_value = mock_chat
        mock_context.bot.send_message.side_effect = TimedOut()

        with (
            patch(
                "bot.handlers.check.get_group_registry",
                return_value=mock_registry,
            ),
        ):
            await handle_warn_callback(update, mock_context)

        query.edit_message_text.assert_called_once()
        call_args = query.edit_message_text.call_args
        assert "Gagal mengirim" in call_args.args[0]

    async def test_warn_callback_get_chat_timeout(
        self, mock_context, mock_settings, mock_registry
    ):
        """Handles TimedOut on get_chat (before the per-group loop)."""
        update = MagicMock()
        query = MagicMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.full_name = "Admin User"
        query.data = "warn:-1001234567890:555666:pu"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query

        mock_context.bot.get_chat.side_effect = TimedOut()

        with (
            patch(
                "bot.handlers.check.get_group_registry",
                return_value=mock_registry,
            ),
        ):
            await handle_warn_callback(update, mock_context)

        query.edit_message_text.assert_called_once()
        call_args = query.edit_message_text.call_args
        assert "timeout" in call_args.args[0].lower()

    async def test_warn_callback_send_failure(
        self, mock_context, mock_settings, mock_registry
    ):
        """A selected-group send failure shows an error."""
        update = MagicMock()
        query = MagicMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.full_name = "Admin User"
        query.data = "warn:-1001234567890:555666:pu"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query

        mock_chat = MagicMock()
        mock_chat.full_name = "Test User"
        mock_chat.username = "testuser"
        mock_context.bot.get_chat.return_value = mock_chat
        mock_context.bot.send_message.side_effect = RuntimeError("Connection lost")

        with (
            patch(
                "bot.handlers.check.get_group_registry",
                return_value=mock_registry,
            ),
        ):
            await handle_warn_callback(update, mock_context)

        query.edit_message_text.assert_called_once()
        call_args = query.edit_message_text.call_args
        assert "Gagal mengirim peringatan" in call_args.args[0]
