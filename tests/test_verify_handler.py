import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.database.service import get_database, init_database, reset_database
from bot.handlers.verify import handle_unverify_command, handle_verify_command


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
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
    
    # Mock get_chat to return a chat with default permissions
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

    async def test_successful_verify_new_user(self, mock_update, mock_context, temp_db):
        target_user_id = 555666
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

    async def test_verify_multiple_users(self, mock_update, mock_context, temp_db):
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

    async def test_verify_with_extra_args_uses_first(self, mock_update, mock_context, temp_db):
        mock_context.args = ["555666", "extra", "args"]

        await handle_verify_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "diverifikasi" in call_args.args[0]

        db = get_database()
        assert db.is_user_photo_whitelisted(555666)

    async def test_verify_large_user_id(self, mock_update, mock_context, temp_db):
        large_id = 9999999999
        mock_context.args = [str(large_id)]

        await handle_verify_command(mock_update, mock_context)

        db = get_database()
        assert db.is_user_photo_whitelisted(large_id)

    async def test_verify_unrestricts_user(self, mock_update, mock_context, temp_db):
        """Test that verify command unrestricts the user."""
        target_user_id = 555666
        mock_context.args = [str(target_user_id)]

        await handle_verify_command(mock_update, mock_context)

        # Should call restrict_chat_member with unrestricted permissions
        mock_context.bot.restrict_chat_member.assert_called_once()
        call_args = mock_context.bot.restrict_chat_member.call_args
        assert call_args.kwargs["user_id"] == target_user_id
        assert call_args.kwargs["permissions"].can_send_messages is True

    async def test_verify_deletes_warnings(self, mock_update, mock_context, temp_db):
        """Test that verify command deletes all warning records."""
        from bot.config import get_settings
        
        target_user_id = 555666
        settings = get_settings()
        db = get_database()

        # Create some warning records for the user
        db.get_or_create_user_warning(target_user_id, settings.group_id)
        db.increment_message_count(target_user_id, settings.group_id)
        
        # Verify there's at least one warning
        warning = db.get_or_create_user_warning(target_user_id, settings.group_id)
        assert warning.message_count >= 1

        # Now verify the user
        mock_context.args = [str(target_user_id)]
        await handle_verify_command(mock_update, mock_context)

        # Warnings should be deleted - trying to get warnings should create a new one
        new_warning = db.get_or_create_user_warning(target_user_id, settings.group_id)
        assert new_warning.message_count == 1  # Fresh start

    async def test_verify_handles_non_restricted_user_gracefully(
        self, mock_update, mock_context, temp_db
    ):
        """Test that verify doesn't fail if user is not restricted."""
        from telegram.error import BadRequest
        
        target_user_id = 555666
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
