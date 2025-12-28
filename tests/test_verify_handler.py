import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.database.service import get_database, init_database, reset_database
from bot.handlers.verify import (
    handle_forwarded_message,
    handle_unverify_callback,
    handle_unverify_command,
    handle_verify_callback,
    handle_verify_command,
)


@pytest.fixture(autouse=True)
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        reset_database()  # Reset before init
        init_database(str(db_path))
        yield db_path
        reset_database()


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
    context.bot.get_chat = AsyncMock()
    context.bot.restrict_chat_member = AsyncMock()
    context.bot.send_message = AsyncMock()
    
    # Mock get_chat to return both chat permissions and user info
    mock_chat = MagicMock()
    mock_permissions = MagicMock()
    mock_permissions.can_send_messages = True
    mock_permissions.can_send_polls = True
    mock_permissions.can_send_other_messages = True
    mock_permissions.can_add_web_page_previews = True
    mock_permissions.can_change_info = False
    mock_permissions.can_invite_users = True
    mock_permissions.can_pin_messages = False
    mock_chat.permissions = mock_permissions
    mock_chat.full_name = "Test User"
    context.bot.get_chat.return_value = mock_chat
    
    context.bot_data = {"admin_ids": [12345]}
    context.args = []
    return context


class TestHandleVerifyCommand:
    async def test_no_message(self, mock_context):
        update = MagicMock()
        update.message = None

        await handle_verify_command(update, mock_context)

        mock_context.bot_data["admin_ids"]  # Just verify no crash

    async def test_no_from_user(self, mock_context):
        update = MagicMock()
        update.message = MagicMock()
        update.message.from_user = None

        await handle_verify_command(update, mock_context)

        # Should return early without calling reply_text

    async def test_non_private_chat_rejected(self, mock_update, mock_context):
        mock_update.effective_chat.type = "group"
        mock_context.args = ["123456"]

        await handle_verify_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "chat pribadi" in call_args.args[0]

    async def test_non_admin_rejected(self, mock_update, mock_context):
        mock_update.message.from_user.id = 99999
        mock_context.bot_data = {"admin_ids": [12345]}
        mock_context.args = ["123456"]

        await handle_verify_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "izin" in call_args.args[0]

    async def test_no_user_id_provided(self, mock_update, mock_context):
        mock_context.args = []

        await handle_verify_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "/verify USER_ID" in call_args.args[0]

    async def test_invalid_user_id_format(self, mock_update, mock_context):
        mock_context.args = ["not_a_number"]

        await handle_verify_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "angka" in call_args.args[0]

    async def test_successful_verify_new_user(self, mock_update, mock_context, temp_db, monkeypatch):
        # Mock the settings
        class MockSettings:
            group_id = -1001234567890
            warning_topic_id = 12345
            telegram_bot_token = "fake_token"
        
        monkeypatch.setattr("bot.handlers.verify.get_settings", lambda: MockSettings())
        
        target_user_id = 11111111  # Use unique ID
        mock_context.args = [str(target_user_id)]

        await handle_verify_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        response_text = call_args.args[0]
        assert "diverifikasi" in response_text
        assert "whitelist foto profil" in response_text
        assert "Pembatasan dicabut" in response_text
        assert "Riwayat warning dihapus" in response_text
        assert str(target_user_id) in response_text

        db = get_database()
        assert db.is_user_photo_whitelisted(target_user_id)

    async def test_verify_already_whitelisted_user(self, mock_update, mock_context, temp_db):
        target_user_id = 555666
        db = get_database()
        db.add_photo_verification_whitelist(
            user_id=target_user_id, verified_by_admin_id=12345
        )

        mock_context.args = [str(target_user_id)]

        await handle_verify_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "sudah ada di whitelist" in call_args.args[0]

    async def test_verify_multiple_users(self, mock_update, mock_context, temp_db, monkeypatch):
        # Mock the settings
        class MockSettings:
            group_id = -1001234567890
            warning_topic_id = 12345
            telegram_bot_token = "fake_token"
        
        monkeypatch.setattr("bot.handlers.verify.get_settings", lambda: MockSettings())
        
        db = get_database()

        # Verify first user
        mock_context.args = ["111111"]
        await handle_verify_command(mock_update, mock_context)
        assert db.is_user_photo_whitelisted(111111)

        # Verify second user
        mock_context.args = ["222222"]
        await handle_verify_command(mock_update, mock_context)
        assert db.is_user_photo_whitelisted(222222)

        # Both should be whitelisted
        assert db.is_user_photo_whitelisted(111111)
        assert db.is_user_photo_whitelisted(222222)

    async def test_verify_respects_admin_ids(self, mock_update, mock_context):
        mock_context.bot_data = {"admin_ids": [999, 888]}
        mock_update.message.from_user.id = 555  # Not an admin
        mock_context.args = ["123456"]

        await handle_verify_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "izin" in call_args.args[0]

    async def test_verify_with_extra_args_uses_first(self, mock_update, mock_context, temp_db, monkeypatch):
        # Mock the settings
        class MockSettings:
            group_id = -1001234567890
            warning_topic_id = 12345
            telegram_bot_token = "fake_token"
        
        monkeypatch.setattr("bot.handlers.verify.get_settings", lambda: MockSettings())
        
        target_user_id = 22222222  # Use unique ID
        mock_context.args = [str(target_user_id), "extra", "args"]

        await handle_verify_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "diverifikasi" in call_args.args[0]

        db = get_database()
        assert db.is_user_photo_whitelisted(target_user_id)

    async def test_verify_large_user_id(self, mock_update, mock_context, temp_db, monkeypatch):
        # Mock the settings
        class MockSettings:
            group_id = -1001234567890
            warning_topic_id = 12345
            telegram_bot_token = "fake_token"
        
        monkeypatch.setattr("bot.handlers.verify.get_settings", lambda: MockSettings())
        
        large_id = 9999999999
        mock_context.args = [str(large_id)]

        await handle_verify_command(mock_update, mock_context)

        db = get_database()
        assert db.is_user_photo_whitelisted(large_id)

    async def test_verify_unrestricts_user(self, mock_update, mock_context, temp_db, monkeypatch):
        """Test that verify command unrestricts the user."""
        # Mock the settings
        class MockSettings:
            group_id = -1001234567890
            warning_topic_id = 12345
            telegram_bot_token = "fake_token"
        
        monkeypatch.setattr("bot.handlers.verify.get_settings", lambda: MockSettings())
        
        target_user_id = 33333333  # Use unique ID
        mock_context.args = [str(target_user_id)]

        await handle_verify_command(mock_update, mock_context)

        # Should call restrict_chat_member with unrestricted permissions
        mock_context.bot.restrict_chat_member.assert_called_once()
        call_args = mock_context.bot.restrict_chat_member.call_args
        assert call_args.kwargs["user_id"] == target_user_id
        assert call_args.kwargs["permissions"].can_send_messages is True

    async def test_verify_deletes_warnings(self, mock_update, mock_context, temp_db, monkeypatch):
        """Test that verify command deletes all warning records."""
        # Mock the settings
        class MockSettings:
            group_id = -1001234567890
            warning_topic_id = 12345
            telegram_bot_token = "fake_token"
        
        monkeypatch.setattr("bot.handlers.verify.get_settings", lambda: MockSettings())
        
        target_user_id = 66666666  # Use unique ID
        db = get_database()

        # Create some warning records for the user
        db.get_or_create_user_warning(target_user_id, MockSettings.group_id)
        db.increment_message_count(target_user_id, MockSettings.group_id)
        
        # Verify there's at least one warning
        warning = db.get_or_create_user_warning(target_user_id, MockSettings.group_id)
        assert warning.message_count >= 1

        # Now verify the user
        mock_context.args = [str(target_user_id)]
        await handle_verify_command(mock_update, mock_context)

        # Warnings should be deleted - trying to get warnings should create a new one
        new_warning = db.get_or_create_user_warning(target_user_id, MockSettings.group_id)
        assert new_warning.message_count == 1  # Fresh start

    async def test_verify_handles_non_restricted_user_gracefully(
        self, mock_update, mock_context, temp_db, monkeypatch
    ):
        """Test that verify doesn't fail if user is not restricted."""
        from telegram.error import BadRequest
        
        # Mock the settings
        class MockSettings:
            group_id = -1001234567890
            warning_topic_id = 12345
            telegram_bot_token = "fake_token"
        
        monkeypatch.setattr("bot.handlers.verify.get_settings", lambda: MockSettings())
        
        target_user_id = 44444444  # Use unique ID
        mock_context.args = [str(target_user_id)]
        
        # Simulate BadRequest when trying to unrestrict a non-restricted user
        mock_context.bot.restrict_chat_member.side_effect = BadRequest("User not restricted")

        # Should not raise exception
        await handle_verify_command(mock_update, mock_context)

        # User should still be whitelisted
        db = get_database()
        assert db.is_user_photo_whitelisted(target_user_id)
        
        # Should still send success message
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "diverifikasi" in call_args.args[0]

    async def test_verify_with_warnings_sends_notification_to_topic(
        self, mock_update, mock_context, temp_db, monkeypatch
    ):
        """Test that verify sends notification to warning topic when user has warnings."""
        # Mock the settings
        class MockSettings:
            group_id = -1001234567890
            warning_topic_id = 12345
            telegram_bot_token = "fake_token"
        
        monkeypatch.setattr("bot.handlers.verify.get_settings", lambda: MockSettings())
        
        target_user_id = 77777777  # Use unique ID
        db = get_database()

        # Create warning records for the user
        db.get_or_create_user_warning(target_user_id, MockSettings.group_id)
        db.increment_message_count(target_user_id, MockSettings.group_id)
        db.increment_message_count(target_user_id, MockSettings.group_id)

        # Now verify the user
        mock_context.args = [str(target_user_id)]
        await handle_verify_command(mock_update, mock_context)

        # Should send notification to warning topic
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert call_args.kwargs["chat_id"] == MockSettings.group_id
        assert call_args.kwargs["message_thread_id"] == MockSettings.warning_topic_id
        assert call_args.kwargs["parse_mode"] == "Markdown"
        # Check the message contains user mention
        assert "Test User" in call_args.kwargs["text"] or str(target_user_id) in call_args.kwargs["text"]

    async def test_verify_without_warnings_no_notification(
        self, mock_update, mock_context, temp_db, monkeypatch
    ):
        """Test that verify doesn't send notification when user has no warnings."""
        # Mock the settings
        class MockSettings:
            group_id = -1001234567890
            warning_topic_id = 12345
            telegram_bot_token = "fake_token"
        
        monkeypatch.setattr("bot.handlers.verify.get_settings", lambda: MockSettings())
        
        target_user_id = 88888888  # Use unique ID
        mock_context.args = [str(target_user_id)]

        # Verify user without any warnings
        await handle_verify_command(mock_update, mock_context)

        # Should NOT send notification to warning topic
        mock_context.bot.send_message.assert_not_called()


class TestHandleUnverifyCommand:
    async def test_no_message(self, mock_context):
        update = MagicMock()
        update.message = None

        await handle_unverify_command(update, mock_context)

        # Should return early without crash

    async def test_no_from_user(self, mock_context):
        update = MagicMock()
        update.message = MagicMock()
        update.message.from_user = None

        await handle_unverify_command(update, mock_context)

        # Should return early without crash

    async def test_non_private_chat_rejected(self, mock_update, mock_context):
        mock_update.effective_chat.type = "group"
        mock_context.args = ["123456"]

        await handle_unverify_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "chat pribadi" in call_args.args[0]

    async def test_non_admin_rejected(self, mock_update, mock_context):
        mock_update.message.from_user.id = 99999
        mock_context.bot_data = {"admin_ids": [12345]}
        mock_context.args = ["123456"]

        await handle_unverify_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "izin" in call_args.args[0]

    async def test_no_user_id_provided(self, mock_update, mock_context):
        mock_context.args = []

        await handle_unverify_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "/unverify USER_ID" in call_args.args[0]

    async def test_invalid_user_id_format(self, mock_update, mock_context):
        mock_context.args = ["invalid_id"]

        await handle_unverify_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "angka" in call_args.args[0]

    async def test_successful_unverify_whitelisted_user(
        self, mock_update, mock_context, temp_db
    ):
        target_user_id = 555666
        db = get_database()
        db.add_photo_verification_whitelist(
            user_id=target_user_id, verified_by_admin_id=12345
        )

        mock_context.args = [str(target_user_id)]

        await handle_unverify_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "dihapus dari whitelist" in call_args.args[0]

        assert not db.is_user_photo_whitelisted(target_user_id)

    async def test_unverify_not_whitelisted_user(self, mock_update, mock_context, temp_db):
        target_user_id = 555666
        mock_context.args = [str(target_user_id)]

        await handle_unverify_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "tidak ada di whitelist" in call_args.args[0]

    async def test_unverify_multiple_users(self, mock_update, mock_context, temp_db):
        db = get_database()

        # Add two users to whitelist
        db.add_photo_verification_whitelist(user_id=111111, verified_by_admin_id=12345)
        db.add_photo_verification_whitelist(user_id=222222, verified_by_admin_id=12345)

        # Unverify first user
        mock_context.args = ["111111"]
        await handle_unverify_command(mock_update, mock_context)
        assert not db.is_user_photo_whitelisted(111111)

        # Second should still be whitelisted
        assert db.is_user_photo_whitelisted(222222)

        # Unverify second user
        mock_context.args = ["222222"]
        await handle_unverify_command(mock_update, mock_context)
        assert not db.is_user_photo_whitelisted(222222)

    async def test_unverify_respects_admin_ids(self, mock_update, mock_context, temp_db):
        db = get_database()
        db.add_photo_verification_whitelist(user_id=555666, verified_by_admin_id=12345)

        mock_context.bot_data = {"admin_ids": [999, 888]}
        mock_update.message.from_user.id = 555  # Not an admin
        mock_context.args = ["555666"]

        await handle_unverify_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "izin" in call_args.args[0]

        # User should still be whitelisted
        assert db.is_user_photo_whitelisted(555666)

    async def test_unverify_with_extra_args_uses_first(
        self, mock_update, mock_context, temp_db
    ):
        db = get_database()
        db.add_photo_verification_whitelist(user_id=555666, verified_by_admin_id=12345)

        mock_context.args = ["555666", "extra", "args"]

        await handle_unverify_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "dihapus dari whitelist" in call_args.args[0]

        assert not db.is_user_photo_whitelisted(555666)


class TestHandleForwardedMessage:
    async def test_no_message(self, mock_context):
        update = MagicMock()
        update.message = None

        await handle_forwarded_message(update, mock_context)

    async def test_no_from_user(self, mock_context):
        update = MagicMock()
        update.message = MagicMock()
        update.message.from_user = None

        await handle_forwarded_message(update, mock_context)

    async def test_non_admin_rejected(self, mock_update, mock_context):
        mock_update.message.from_user.id = 99999
        mock_context.bot_data = {"admin_ids": [12345]}
        
        # Mock forwarded message
        mock_update.message.forward_origin = MagicMock()
        mock_update.message.forward_origin.sender_user = MagicMock()
        mock_update.message.forward_origin.sender_user.id = 555666

        await handle_forwarded_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "izin" in call_args.args[0]

    async def test_successful_forwarded_message_new_api(self, mock_update, mock_context):
        # Mock forwarded message with new API (forward_origin)
        forwarded_user = MagicMock()
        forwarded_user.id = 555666
        forwarded_user.full_name = "Test User"
        
        mock_update.message.forward_origin = MagicMock()
        mock_update.message.forward_origin.sender_user = forwarded_user
        mock_update.message.forward_from = None

        await handle_forwarded_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert call_args.kwargs["parse_mode"] == "Markdown"
        assert call_args.kwargs["reply_markup"] is not None
        
        # Check message content
        message_text = call_args.args[0]
        assert "555666" in message_text
        assert "Test User" in message_text or "555666" in message_text
        
        # Check keyboard buttons
        keyboard = call_args.kwargs["reply_markup"].inline_keyboard
        assert len(keyboard) == 1
        assert len(keyboard[0]) == 2
        assert keyboard[0][0].text == "✅ Verify User"
        assert keyboard[0][0].callback_data == "verify:555666"
        assert keyboard[0][1].text == "❌ Unverify User"
        assert keyboard[0][1].callback_data == "unverify:555666"

    async def test_successful_forwarded_message_legacy_api(self, mock_update, mock_context):
        # Mock forwarded message with legacy API (forward_from)
        forwarded_user = MagicMock()
        forwarded_user.id = 777888
        forwarded_user.first_name = "Legacy User"
        forwarded_user.full_name = "Legacy User"  # Add full_name attribute
        
        mock_update.message.forward_origin = None
        mock_update.message.forward_from = forwarded_user

        await handle_forwarded_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        
        # Check keyboard buttons
        keyboard = call_args.kwargs["reply_markup"].inline_keyboard
        assert keyboard[0][0].callback_data == "verify:777888"
        assert keyboard[0][1].callback_data == "unverify:777888"

    async def test_forwarded_message_no_user_info(self, mock_update, mock_context):
        # Mock forwarded message without user info (privacy settings)
        mock_update.message.forward_origin = None
        mock_update.message.forward_from = None

        await handle_forwarded_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "Tidak dapat mengekstrak" in call_args.args[0]


class TestHandleVerifyCallback:
    async def test_no_query(self, mock_context):
        update = MagicMock()
        update.callback_query = None

        await handle_verify_callback(update, mock_context)

    async def test_no_from_user(self, mock_context):
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.from_user = None

        await handle_verify_callback(update, mock_context)

    async def test_non_admin_rejected(self, mock_context):
        update = MagicMock()
        query = MagicMock()
        query.from_user = MagicMock()
        query.from_user.id = 99999
        query.from_user.full_name = "Non Admin"
        query.data = "verify:555666"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query
        
        mock_context.bot_data = {"admin_ids": [12345]}

        await handle_verify_callback(update, mock_context)

        query.answer.assert_called_once()
        query.edit_message_text.assert_called_once()
        call_args = query.edit_message_text.call_args
        assert "izin" in call_args.args[0]

    async def test_invalid_callback_data_format(self, mock_context):
        update = MagicMock()
        query = MagicMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.full_name = "Admin User"
        query.data = "verify:invalid"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query

        await handle_verify_callback(update, mock_context)

        query.answer.assert_called_once()
        query.edit_message_text.assert_called_once()
        call_args = query.edit_message_text.call_args
        assert "tidak valid" in call_args.args[0]

    async def test_successful_verify_callback(self, temp_db, mock_context, monkeypatch):
        # Mock the settings
        class MockSettings:
            group_id = -1001234567890
            warning_topic_id = 12345
            telegram_bot_token = "fake_token"
        
        monkeypatch.setattr("bot.handlers.verify.get_settings", lambda: MockSettings())
        
        update = MagicMock()
        query = MagicMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.full_name = "Admin User"
        query.data = "verify:999888"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query

        await handle_verify_callback(update, mock_context)

        query.answer.assert_called_once()
        query.edit_message_text.assert_called_once()
        call_args = query.edit_message_text.call_args
        assert "diverifikasi" in call_args.args[0]
        
        # Verify user was added to whitelist
        db = get_database()
        assert db.is_user_photo_whitelisted(999888)

    async def test_verify_callback_already_whitelisted(self, temp_db, mock_context):
        db = get_database()
        db.add_photo_verification_whitelist(user_id=555666, verified_by_admin_id=12345)
        
        update = MagicMock()
        query = MagicMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.full_name = "Admin User"
        query.data = "verify:555666"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query

        await handle_verify_callback(update, mock_context)

        query.answer.assert_called_once()
        query.edit_message_text.assert_called_once()
        call_args = query.edit_message_text.call_args
        assert "sudah ada di whitelist" in call_args.args[0]

    async def test_verify_callback_generic_exception(self, temp_db, mock_context):
        update = MagicMock()
        query = MagicMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.full_name = "Admin User"
        query.data = "verify:555666"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query
        
        # Mock get_settings to raise a generic exception
        with patch("bot.handlers.verify.get_settings", side_effect=RuntimeError("Settings error")):
            await handle_verify_callback(update, mock_context)

        query.answer.assert_called_once()
        query.edit_message_text.assert_called_once()
        call_args = query.edit_message_text.call_args
        assert "Terjadi kesalahan" in call_args.args[0]


class TestHandleUnverifyCallback:
    async def test_no_query(self, mock_context):
        update = MagicMock()
        update.callback_query = None

        await handle_unverify_callback(update, mock_context)

    async def test_no_from_user(self, mock_context):
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.from_user = None

        await handle_unverify_callback(update, mock_context)

    async def test_non_admin_rejected(self, mock_context):
        update = MagicMock()
        query = MagicMock()
        query.from_user = MagicMock()
        query.from_user.id = 99999
        query.from_user.full_name = "Non Admin"
        query.data = "unverify:555666"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query
        
        mock_context.bot_data = {"admin_ids": [12345]}

        await handle_unverify_callback(update, mock_context)

        query.answer.assert_called_once()
        query.edit_message_text.assert_called_once()
        call_args = query.edit_message_text.call_args
        assert "izin" in call_args.args[0]

    async def test_invalid_callback_data_format(self, mock_context):
        update = MagicMock()
        query = MagicMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.full_name = "Admin User"
        query.data = "unverify:invalid"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query

        await handle_unverify_callback(update, mock_context)

        query.answer.assert_called_once()
        query.edit_message_text.assert_called_once()
        call_args = query.edit_message_text.call_args
        assert "tidak valid" in call_args.args[0]

    async def test_successful_unverify_callback(self, temp_db, mock_context):
        db = get_database()
        db.add_photo_verification_whitelist(user_id=555666, verified_by_admin_id=12345)
        
        update = MagicMock()
        query = MagicMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.full_name = "Admin User"
        query.data = "unverify:555666"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query

        await handle_unverify_callback(update, mock_context)

        query.answer.assert_called_once()
        query.edit_message_text.assert_called_once()
        call_args = query.edit_message_text.call_args
        assert "dihapus dari whitelist" in call_args.args[0]
        
        # Verify user was removed from whitelist
        assert not db.is_user_photo_whitelisted(555666)

    async def test_unverify_callback_not_whitelisted(self, temp_db, mock_context):
        update = MagicMock()
        query = MagicMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.full_name = "Admin User"
        query.data = "unverify:555666"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query

        await handle_unverify_callback(update, mock_context)

        query.answer.assert_called_once()
        query.edit_message_text.assert_called_once()
        call_args = query.edit_message_text.call_args
        assert "tidak ada di whitelist" in call_args.args[0]

    async def test_unverify_callback_generic_exception(self, temp_db, mock_context):
        update = MagicMock()
        query = MagicMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.full_name = "Admin User"
        query.data = "unverify:555666"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query
        
        # Mock unverify_user to raise a generic exception
        with patch("bot.handlers.verify.unverify_user", side_effect=RuntimeError("Unverify error")):
            await handle_unverify_callback(update, mock_context)

        query.answer.assert_called_once()
        query.edit_message_text.assert_called_once()
        call_args = query.edit_message_text.call_args
        assert "Terjadi kesalahan" in call_args.args[0]
