import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.error import BadRequest

from bot.database.service import init_database, reset_database
from bot.handlers.dm import handle_dm
from bot.services.user_checker import ProfileCheckResult


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.group_id = -1001234567890
    settings.rules_link = "https://t.me/test/rules"
    return settings


@pytest.fixture
def mock_update():
    update = MagicMock()
    update.message = MagicMock()
    update.message.from_user = MagicMock()
    update.message.from_user.id = 12345
    update.message.from_user.username = "testuser"
    update.message.from_user.full_name = "Test User"
    update.message.reply_text = AsyncMock()
    update.effective_chat = MagicMock()
    update.effective_chat.type = "private"
    return update


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.bot = AsyncMock()
    context.bot.id = 99999
    user_member = MagicMock()
    user_member.status = "member"
    context.bot.get_chat_member.return_value = user_member
    return context


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_database(str(db_path))
        yield db_path
        reset_database()


class TestHandleDM:
    async def test_no_message(self, mock_context):
        update = MagicMock()
        update.message = None

        await handle_dm(update, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()

    async def test_no_user(self, mock_context):
        update = MagicMock()
        update.message = MagicMock()
        update.message.from_user = None

        await handle_dm(update, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()

    async def test_non_private_chat_ignored(self, mock_update, mock_context, mock_settings):
        mock_update.effective_chat.type = "group"

        with patch("bot.handlers.dm.get_settings", return_value=mock_settings):
            await handle_dm(mock_update, mock_context)

        mock_update.message.reply_text.assert_not_called()

    async def test_user_not_in_group(self, mock_update, mock_context, mock_settings):
        mock_context.bot.get_chat_member.side_effect = BadRequest("User not found")

        with patch("bot.handlers.dm.get_settings", return_value=mock_settings):
            await handle_dm(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "belum bergabung di grup" in call_args.args[0]
        mock_context.bot.restrict_chat_member.assert_not_called()

    async def test_user_left_group(self, mock_update, mock_context, mock_settings):
        user_member = MagicMock()
        user_member.status = "left"
        mock_context.bot.get_chat_member.return_value = user_member

        with patch("bot.handlers.dm.get_settings", return_value=mock_settings):
            await handle_dm(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "belum bergabung di grup" in call_args.args[0]

    async def test_user_kicked_from_group(self, mock_update, mock_context, mock_settings):
        user_member = MagicMock()
        user_member.status = "kicked"
        mock_context.bot.get_chat_member.return_value = user_member

        with patch("bot.handlers.dm.get_settings", return_value=mock_settings):
            await handle_dm(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "belum bergabung di grup" in call_args.args[0]

    async def test_missing_profile_sends_requirements(
        self, mock_update, mock_context, mock_settings, temp_db
    ):
        incomplete_result = ProfileCheckResult(
            has_profile_photo=False, has_username=True
        )

        with (
            patch("bot.handlers.dm.get_settings", return_value=mock_settings),
            patch(
                "bot.handlers.dm.check_user_profile",
                return_value=incomplete_result,
            ),
        ):
            await handle_dm(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "❌" in call_args.args[0]
        assert "foto profil publik" in call_args.args[0]
        mock_context.bot.restrict_chat_member.assert_not_called()

    async def test_missing_username_sends_requirements(
        self, mock_update, mock_context, mock_settings, temp_db
    ):
        incomplete_result = ProfileCheckResult(
            has_profile_photo=True, has_username=False
        )

        with (
            patch("bot.handlers.dm.get_settings", return_value=mock_settings),
            patch(
                "bot.handlers.dm.check_user_profile",
                return_value=incomplete_result,
            ),
        ):
            await handle_dm(mock_update, mock_context)

        call_args = mock_update.message.reply_text.call_args
        assert "username" in call_args.args[0]

    async def test_complete_profile_not_restricted_by_bot(
        self, mock_update, mock_context, mock_settings, temp_db
    ):
        complete_result = ProfileCheckResult(
            has_profile_photo=True, has_username=True
        )

        with (
            patch("bot.handlers.dm.get_settings", return_value=mock_settings),
            patch(
                "bot.handlers.dm.check_user_profile",
                return_value=complete_result,
            ),
        ):
            await handle_dm(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "tidak memiliki pembatasan dari bot" in call_args.args[0]
        mock_context.bot.restrict_chat_member.assert_not_called()

    async def test_complete_profile_unrestricts_user(
        self, mock_update, mock_context, mock_settings, temp_db
    ):
        from bot.database.service import get_database

        db = get_database()
        db.get_or_create_user_warning(12345, -1001234567890)
        db.increment_message_count(12345, -1001234567890)
        db.increment_message_count(12345, -1001234567890)
        db.mark_user_restricted(12345, -1001234567890)

        user_member = MagicMock()
        user_member.status = "restricted"
        mock_context.bot.get_chat_member.return_value = user_member

        chat = MagicMock()
        chat.permissions = MagicMock()
        chat.permissions.can_send_messages = True
        mock_context.bot.get_chat.return_value = chat

        complete_result = ProfileCheckResult(
            has_profile_photo=True, has_username=True
        )

        with (
            patch("bot.handlers.dm.get_settings", return_value=mock_settings),
            patch(
                "bot.handlers.dm.check_user_profile",
                return_value=complete_result,
            ),
        ):
            await handle_dm(mock_update, mock_context)

        mock_context.bot.restrict_chat_member.assert_called_once()
        call_args = mock_context.bot.restrict_chat_member.call_args
        assert call_args.kwargs["chat_id"] == -1001234567890
        assert call_args.kwargs["user_id"] == 12345

        reply_args = mock_update.message.reply_text.call_args
        assert "✅" in reply_args.args[0]
        assert "dicabut" in reply_args.args[0]

        assert db.is_user_restricted_by_bot(12345, -1001234567890) is False

    async def test_user_already_unrestricted_on_telegram(
        self, mock_update, mock_context, mock_settings, temp_db
    ):
        from bot.database.service import get_database

        db = get_database()
        db.get_or_create_user_warning(12345, -1001234567890)
        db.increment_message_count(12345, -1001234567890)
        db.increment_message_count(12345, -1001234567890)
        db.mark_user_restricted(12345, -1001234567890)

        user_member = MagicMock()
        user_member.status = "member"
        mock_context.bot.get_chat_member.return_value = user_member

        complete_result = ProfileCheckResult(
            has_profile_photo=True, has_username=True
        )

        with (
            patch("bot.handlers.dm.get_settings", return_value=mock_settings),
            patch(
                "bot.handlers.dm.check_user_profile",
                return_value=complete_result,
            ),
        ):
            await handle_dm(mock_update, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()
        call_args = mock_update.message.reply_text.call_args
        assert "sudah tidak dibatasi" in call_args.args[0]
        assert db.is_user_restricted_by_bot(12345, -1001234567890) is False

    async def test_does_not_unrestrict_admin_restricted_user(
        self, mock_update, mock_context, mock_settings, temp_db
    ):
        from bot.database.service import get_database

        db = get_database()
        db.get_or_create_user_warning(12345, -1001234567890)

        complete_result = ProfileCheckResult(
            has_profile_photo=True, has_username=True
        )

        with (
            patch("bot.handlers.dm.get_settings", return_value=mock_settings),
            patch(
                "bot.handlers.dm.check_user_profile",
                return_value=complete_result,
            ),
        ):
            await handle_dm(mock_update, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()
        call_args = mock_update.message.reply_text.call_args
        assert "tidak memiliki pembatasan dari bot" in call_args.args[0]

    async def test_redirects_user_with_pending_captcha_to_group(
        self, mock_update, mock_context, mock_settings, temp_db
    ):
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(
            user_id=12345,
            group_id=-1001234567890,
            chat_id=-1001234567890,
            message_id=999,
            user_full_name="Test User",
        )

        user_member = MagicMock()
        user_member.status = "restricted"
        mock_context.bot.get_chat_member.return_value = user_member

        with patch("bot.handlers.dm.get_settings", return_value=mock_settings):
            await handle_dm(mock_update, mock_context)

        # Should not unrestrict user
        mock_context.bot.restrict_chat_member.assert_not_called()
        
        # Should tell user to check group and verify
        reply_args = mock_update.message.reply_text.call_args
        assert "⏳" in reply_args.args[0]
        assert "verifikasi captcha yang tertunda" in reply_args.args[0]
        assert "tekan tombol verifikasi" in reply_args.args[0]

        # Pending captcha should still exist (not removed)
        assert db.get_pending_captcha(12345, -1001234567890) is not None

    async def test_pending_captcha_check_takes_priority_over_profile_check(
        self, mock_update, mock_context, mock_settings, temp_db
    ):
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(
            user_id=12345,
            group_id=-1001234567890,
            chat_id=-1001234567890,
            message_id=999,
            user_full_name="Test User",
        )

        user_member = MagicMock()
        user_member.status = "restricted"
        mock_context.bot.get_chat_member.return_value = user_member

        with (
            patch("bot.handlers.dm.get_settings", return_value=mock_settings),
            patch("bot.handlers.dm.check_user_profile") as mock_check_profile,
        ):
            await handle_dm(mock_update, mock_context)

        # Should skip profile check entirely
        mock_check_profile.assert_not_called()

        # Should redirect to group
        reply_args = mock_update.message.reply_text.call_args
        assert "⏳" in reply_args.args[0]
        assert "verifikasi captcha yang tertunda" in reply_args.args[0]


class TestDatabaseIsUserRestrictedByBot:
    def test_returns_false_when_no_record(self, temp_db):
        from bot.database.service import get_database

        db = get_database()
        assert db.is_user_restricted_by_bot(99999, -1001234567890) is False

    def test_returns_false_when_not_restricted(self, temp_db):
        from bot.database.service import get_database

        db = get_database()
        db.get_or_create_user_warning(12345, -1001234567890)
        assert db.is_user_restricted_by_bot(12345, -1001234567890) is False

    def test_returns_true_when_restricted_by_bot(self, temp_db):
        from bot.database.service import get_database

        db = get_database()
        db.get_or_create_user_warning(12345, -1001234567890)
        db.increment_message_count(12345, -1001234567890)
        db.increment_message_count(12345, -1001234567890)
        db.mark_user_restricted(12345, -1001234567890)
        assert db.is_user_restricted_by_bot(12345, -1001234567890) is True


class TestUnrestrictUserError:
    async def test_unrestrict_user_exception_logged_and_raised(
        self, mock_update, mock_context, mock_settings, temp_db
    ):
        from bot.database.service import get_database

        db = get_database()
        db.get_or_create_user_warning(12345, -1001234567890)
        db.increment_message_count(12345, -1001234567890)
        db.increment_message_count(12345, -1001234567890)
        db.mark_user_restricted(12345, -1001234567890)

        user_member = MagicMock()
        user_member.status = "restricted"
        mock_context.bot.get_chat_member.return_value = user_member

        complete_result = ProfileCheckResult(
            has_profile_photo=True, has_username=True
        )

        with (
            patch("bot.handlers.dm.get_settings", return_value=mock_settings),
            patch(
                "bot.handlers.dm.check_user_profile",
                return_value=complete_result,
            ),
            patch(
                "bot.handlers.dm.unrestrict_user",
                side_effect=Exception("test error"),
            ),
        ):
            with pytest.raises(Exception, match="test error"):
                await handle_dm(mock_update, mock_context)
