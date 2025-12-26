import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.database.service import init_database, reset_database
from bot.handlers.captcha import (
    captcha_callback_handler,
    captcha_timeout_callback,
    chat_member_handler,
    new_member_handler,
)


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.group_id = -1001234567890
    settings.captcha_enabled = True
    settings.captcha_timeout_seconds = 300
    return settings


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.bot = AsyncMock()
    context.bot.restrict_chat_member = AsyncMock()
    context.bot.send_message = AsyncMock()
    context.bot.ban_chat_member = AsyncMock()
    context.bot.edit_message_text = AsyncMock()
    context.job_queue = MagicMock()
    context.job_queue.run_once = MagicMock()
    context.job_queue.get_jobs_by_name = MagicMock(return_value=[])
    return context


@pytest.fixture
def mock_new_member():
    member = MagicMock()
    member.id = 12345
    member.is_bot = False
    member.username = "testuser"
    member.full_name = "Test User"
    return member


@pytest.fixture
def mock_update_new_member(mock_new_member):
    update = MagicMock()
    update.message = MagicMock()
    update.message.new_chat_members = [mock_new_member]
    update.effective_chat = MagicMock()
    update.effective_chat.id = -1001234567890
    return update


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_database(str(db_path))
        yield db_path
        reset_database()


class TestNewMemberHandler:
    async def test_new_member_restricts_user(
        self, mock_update_new_member, mock_context, mock_settings, temp_db
    ):
        sent_message = MagicMock()
        sent_message.chat_id = -1001234567890
        sent_message.message_id = 999
        mock_context.bot.send_message.return_value = sent_message

        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await new_member_handler(mock_update_new_member, mock_context)

        mock_context.bot.restrict_chat_member.assert_called_once()
        call_args = mock_context.bot.restrict_chat_member.call_args
        assert call_args.kwargs["chat_id"] == -1001234567890
        assert call_args.kwargs["user_id"] == 12345

    async def test_new_member_sends_captcha_message(
        self, mock_update_new_member, mock_context, mock_settings, temp_db
    ):
        sent_message = MagicMock()
        sent_message.chat_id = -1001234567890
        sent_message.message_id = 999
        mock_context.bot.send_message.return_value = sent_message

        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await new_member_handler(mock_update_new_member, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert call_args.kwargs["chat_id"] == -1001234567890
        assert "Selamat datang" in call_args.kwargs["text"]
        assert "300 detik" in call_args.kwargs["text"]
        assert call_args.kwargs["reply_markup"] is not None

    async def test_new_member_saves_to_database(
        self, mock_update_new_member, mock_context, mock_settings, temp_db
    ):
        from bot.database.service import get_database

        sent_message = MagicMock()
        sent_message.chat_id = -1001234567890
        sent_message.message_id = 999
        mock_context.bot.send_message.return_value = sent_message

        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await new_member_handler(mock_update_new_member, mock_context)

        db = get_database()
        pending = db.get_pending_captcha(12345, -1001234567890)
        assert pending is not None
        assert pending.user_id == 12345
        assert pending.group_id == -1001234567890
        assert pending.message_id == 999

    async def test_new_member_schedules_timeout(
        self, mock_update_new_member, mock_context, mock_settings, temp_db
    ):
        sent_message = MagicMock()
        sent_message.chat_id = -1001234567890
        sent_message.message_id = 999
        mock_context.bot.send_message.return_value = sent_message

        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await new_member_handler(mock_update_new_member, mock_context)

        mock_context.job_queue.run_once.assert_called_once()
        call_args = mock_context.job_queue.run_once.call_args
        assert call_args.kwargs["when"] == 300
        assert call_args.kwargs["name"] == "captcha_timeout_-1001234567890_12345"
        assert call_args.kwargs["data"]["user_id"] == 12345

    async def test_captcha_disabled_skips_check(
        self, mock_update_new_member, mock_context, mock_settings, temp_db
    ):
        mock_settings.captcha_enabled = False

        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await new_member_handler(mock_update_new_member, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_not_called()

    async def test_bot_members_skipped(
        self, mock_update_new_member, mock_context, mock_settings, temp_db
    ):
        mock_update_new_member.message.new_chat_members[0].is_bot = True

        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await new_member_handler(mock_update_new_member, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_not_called()

    async def test_no_message_does_nothing(self, mock_context, mock_settings):
        update = MagicMock()
        update.message = None

        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await new_member_handler(update, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()

    async def test_no_new_members_does_nothing(self, mock_context, mock_settings):
        update = MagicMock()
        update.message = MagicMock()
        update.message.new_chat_members = None

        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await new_member_handler(update, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()

    async def test_wrong_group_skipped(
        self, mock_update_new_member, mock_context, mock_settings, temp_db
    ):
        mock_update_new_member.effective_chat.id = -9999999999

        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await new_member_handler(mock_update_new_member, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_not_called()

    async def test_restrict_failure_continues_gracefully(
        self, mock_update_new_member, mock_context, mock_settings, temp_db
    ):
        mock_context.bot.restrict_chat_member.side_effect = Exception(
            "Restriction failed"
        )

        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await new_member_handler(mock_update_new_member, mock_context)

        mock_context.bot.send_message.assert_not_called()

    async def test_duplicate_prevention_new_member_handler(
        self, mock_update_new_member, mock_context, mock_settings, temp_db
    ):
        """Test that duplicate captcha is prevented in new_member_handler."""
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await new_member_handler(mock_update_new_member, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_not_called()


class TestCaptchaCallbackHandler:
    async def test_captcha_callback_verifies_correct_user(
        self, mock_context, mock_settings, temp_db
    ):
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        query = MagicMock()
        query.answer = AsyncMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.username = "testuser"
        query.from_user.full_name = "Test User"
        query.data = "captcha_verify_12345"
        query.edit_message_text = AsyncMock()

        update = MagicMock()
        update.callback_query = query

        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await captcha_callback_handler(update, mock_context)

        query.answer.assert_called_once()
        assert db.get_pending_captcha(12345, -1001234567890) is None

    async def test_captcha_callback_unrestricts_user(
        self, mock_context, mock_settings, temp_db
    ):
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        query = MagicMock()
        query.answer = AsyncMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.username = "testuser"
        query.from_user.full_name = "Test User"
        query.data = "captcha_verify_12345"
        query.edit_message_text = AsyncMock()

        update = MagicMock()
        update.callback_query = query

        with (
            patch("bot.handlers.captcha.get_settings", return_value=mock_settings),
            patch("bot.handlers.captcha.unrestrict_user") as mock_unrestrict,
        ):
            mock_unrestrict.return_value = AsyncMock()
            await captcha_callback_handler(update, mock_context)

        mock_unrestrict.assert_called_once()
        assert mock_unrestrict.call_args.args[1] == -1001234567890
        assert mock_unrestrict.call_args.args[2] == 12345

    async def test_captcha_callback_deletes_message(
        self, mock_context, mock_settings, temp_db
    ):
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        query = MagicMock()
        query.answer = AsyncMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.username = "testuser"
        query.from_user.full_name = "Test User"
        query.data = "captcha_verify_12345"
        query.edit_message_text = AsyncMock()

        update = MagicMock()
        update.callback_query = query

        with (
            patch("bot.handlers.captcha.get_settings", return_value=mock_settings),
            patch("bot.handlers.captcha.unrestrict_user", return_value=AsyncMock()),
        ):
            await captcha_callback_handler(update, mock_context)

        query.edit_message_text.assert_called_once()
        call_args = query.edit_message_text.call_args
        assert "Terima kasih" in call_args.kwargs["text"]

    async def test_wrong_user_rejected(self, mock_context, mock_settings, temp_db):
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        query = MagicMock()
        query.answer = AsyncMock()
        query.from_user = MagicMock()
        query.from_user.id = 99999
        query.data = "captcha_verify_12345"

        update = MagicMock()
        update.callback_query = query

        with (
            patch("bot.handlers.captcha.get_settings", return_value=mock_settings),
            patch("bot.handlers.captcha.unrestrict_user") as mock_unrestrict,
        ):
            await captcha_callback_handler(update, mock_context)

        assert query.answer.call_count == 2
        second_call = query.answer.call_args_list[1]
        assert "bukan untukmu" in second_call.args[0]
        assert second_call.kwargs["show_alert"] is True
        mock_unrestrict.assert_not_called()
        assert db.get_pending_captcha(12345, -1001234567890) is not None

    async def test_no_query_does_nothing(self, mock_context):
        update = MagicMock()
        update.callback_query = None

        await captcha_callback_handler(update, mock_context)

        mock_context.job_queue.get_jobs_by_name.assert_not_called()

    async def test_no_query_data_does_nothing(self, mock_context):
        query = MagicMock()
        query.answer = AsyncMock()
        query.data = None

        update = MagicMock()
        update.callback_query = query

        await captcha_callback_handler(update, mock_context)

        mock_context.job_queue.get_jobs_by_name.assert_not_called()

    async def test_cancels_timeout_job(self, mock_context, mock_settings, temp_db):
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        mock_job = MagicMock()
        mock_job.schedule_removal = MagicMock()
        mock_context.job_queue.get_jobs_by_name.return_value = [mock_job]

        query = MagicMock()
        query.answer = AsyncMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.username = "testuser"
        query.from_user.full_name = "Test User"
        query.data = "captcha_verify_12345"
        query.edit_message_text = AsyncMock()

        update = MagicMock()
        update.callback_query = query

        with (
            patch("bot.handlers.captcha.get_settings", return_value=mock_settings),
            patch("bot.handlers.captcha.unrestrict_user", return_value=AsyncMock()),
        ):
            await captcha_callback_handler(update, mock_context)

        mock_context.job_queue.get_jobs_by_name.assert_called_once_with(
            "captcha_timeout_-1001234567890_12345"
        )
        mock_job.schedule_removal.assert_called_once()

    async def test_unrestrict_failure_stops_execution(
        self, mock_context, mock_settings, temp_db
    ):
        """Test that unrestrict failure prevents false verification."""
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        query = MagicMock()
        query.answer = AsyncMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.username = "testuser"
        query.from_user.full_name = "Test User"
        query.data = "captcha_verify_12345"
        query.edit_message_text = AsyncMock()

        update = MagicMock()
        update.callback_query = query

        with (
            patch("bot.handlers.captcha.get_settings", return_value=mock_settings),
            patch("bot.handlers.captcha.unrestrict_user") as mock_unrestrict,
        ):
            mock_unrestrict.side_effect = Exception("Unrestrict failed")
            await captcha_callback_handler(update, mock_context)

        # Should NOT edit message or remove from database
        query.edit_message_text.assert_not_called()
        # Database record should still exist for retry
        assert db.get_pending_captcha(12345, -1001234567890) is not None
        # Should show error alert
        query.answer.assert_called_with("Gagal memverifikasi. Silakan coba lagi.", show_alert=True)

    async def test_edit_message_failure_in_callback_continues_gracefully(
        self, mock_context, mock_settings, temp_db
    ):
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        query = MagicMock()
        query.answer = AsyncMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.username = "testuser"
        query.from_user.full_name = "Test User"
        query.data = "captcha_verify_12345"
        query.edit_message_text = AsyncMock()
        query.edit_message_text.side_effect = Exception("Edit failed")

        update = MagicMock()
        update.callback_query = query

        with (
            patch("bot.handlers.captcha.get_settings", return_value=mock_settings),
            patch("bot.handlers.captcha.unrestrict_user", return_value=AsyncMock()),
        ):
            await captcha_callback_handler(update, mock_context)

        assert db.get_pending_captcha(12345, -1001234567890) is None


class TestGetHandlers:
    def test_get_handlers_returns_list(self):
        from bot.handlers.captcha import get_handlers

        handlers = get_handlers()
        assert isinstance(handlers, list)
        assert len(handlers) == 3

    def test_get_handlers_contains_message_handler(self):
        from telegram.ext import MessageHandler

        from bot.handlers.captcha import get_handlers

        handlers = get_handlers()
        assert any(isinstance(h, MessageHandler) for h in handlers)

    def test_get_handlers_contains_callback_handler(self):
        from telegram.ext import CallbackQueryHandler

        from bot.handlers.captcha import get_handlers

        handlers = get_handlers()
        assert any(isinstance(h, CallbackQueryHandler) for h in handlers)


class TestCaptchaTimeoutCallback:
    async def test_captcha_timeout_keeps_user_restricted(self, mock_context, temp_db):
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        job = MagicMock()
        job.data = {
            "user_id": 12345,
            "group_id": -1001234567890,
            "chat_id": -1001234567890,
            "message_id": 999,
            "user_full_name": "Test User",
        }
        mock_context.job = job

        await captcha_timeout_callback(mock_context)

        mock_context.bot.ban_chat_member.assert_not_called()

    async def test_timeout_removes_from_database(self, mock_context, temp_db):
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        job = MagicMock()
        job.data = {
            "user_id": 12345,
            "group_id": -1001234567890,
            "chat_id": -1001234567890,
            "message_id": 999,
            "user_full_name": "Test User",
        }
        mock_context.job = job

        await captcha_timeout_callback(mock_context)

        assert db.get_pending_captcha(12345, -1001234567890) is None

    async def test_timeout_edits_message(self, mock_context, temp_db):
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        job = MagicMock()
        job.data = {
            "user_id": 12345,
            "group_id": -1001234567890,
            "chat_id": -1001234567890,
            "message_id": 999,
            "user_full_name": "Test User",
        }
        mock_context.job = job

        await captcha_timeout_callback(mock_context)

        mock_context.bot.edit_message_text.assert_called_once()
        call_args = mock_context.bot.edit_message_text.call_args
        assert call_args.kwargs["chat_id"] == -1001234567890
        assert call_args.kwargs["message_id"] == 999
        assert "tidak menyelesaikan verifikasi" in call_args.kwargs["text"]

    async def test_already_verified_skips_actions(self, mock_context, temp_db):
        job = MagicMock()
        job.data = {
            "user_id": 12345,
            "group_id": -1001234567890,
            "chat_id": -1001234567890,
            "message_id": 999,
            "user_full_name": "Test User",
        }
        mock_context.job = job

        await captcha_timeout_callback(mock_context)

        mock_context.bot.edit_message_text.assert_not_called()

    async def test_no_job_does_nothing(self, mock_context):
        mock_context.job = None

        await captcha_timeout_callback(mock_context)

        mock_context.bot.edit_message_text.assert_not_called()

    async def test_no_job_data_does_nothing(self, mock_context):
        job = MagicMock()
        job.data = None
        mock_context.job = job

        await captcha_timeout_callback(mock_context)

        mock_context.bot.edit_message_text.assert_not_called()

    async def test_edit_message_failure_in_timeout_continues_gracefully(
        self, mock_context, temp_db
    ):
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        mock_context.bot.edit_message_text.side_effect = Exception("Edit failed")

        job = MagicMock()
        job.data = {
            "user_id": 12345,
            "group_id": -1001234567890,
            "chat_id": -1001234567890,
            "message_id": 999,
            "user_full_name": "Test User",
        }
        mock_context.job = job

        await captcha_timeout_callback(mock_context)

        assert db.get_pending_captcha(12345, -1001234567890) is None


class TestChatMemberHandler:
    """Tests for chat_member_handler that uses ChatMemberUpdated events."""

    def create_chat_member_update(self, old_status, new_status, user_id=12345, group_id=-1001234567890):
        """Helper to create ChatMemberUpdated update objects."""
        update = MagicMock()
        update.chat_member = MagicMock()
        
        old_member = MagicMock()
        old_member.status = old_status
        update.chat_member.old_chat_member = old_member
        
        new_member = MagicMock()
        new_member.status = new_status
        new_member.user = MagicMock()
        new_member.user.id = user_id
        new_member.user.is_bot = False
        new_member.user.full_name = "Test User"
        update.chat_member.new_chat_member = new_member
        
        update.effective_chat = MagicMock()
        update.effective_chat.id = group_id
        
        return update

    async def test_left_to_member_triggers_captcha(
        self, mock_context, mock_settings, temp_db
    ):
        """Test LEFT → MEMBER transition triggers captcha."""
        from telegram.constants import ChatMemberStatus
        
        update = self.create_chat_member_update(ChatMemberStatus.LEFT, ChatMemberStatus.MEMBER)
        
        sent_message = MagicMock()
        sent_message.chat_id = -1001234567890
        sent_message.message_id = 999
        mock_context.bot.send_message.return_value = sent_message
        
        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await chat_member_handler(update, mock_context)
        
        mock_context.bot.restrict_chat_member.assert_called_once()
        mock_context.bot.send_message.assert_called_once()

    async def test_banned_to_member_triggers_captcha(
        self, mock_context, mock_settings, temp_db
    ):
        """Test BANNED → MEMBER transition triggers captcha."""
        from telegram.constants import ChatMemberStatus
        
        update = self.create_chat_member_update(ChatMemberStatus.BANNED, ChatMemberStatus.MEMBER)
        
        sent_message = MagicMock()
        sent_message.chat_id = -1001234567890
        sent_message.message_id = 999
        mock_context.bot.send_message.return_value = sent_message
        
        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await chat_member_handler(update, mock_context)
        
        mock_context.bot.restrict_chat_member.assert_called_once()
        mock_context.bot.send_message.assert_called_once()

    async def test_member_to_administrator_no_captcha(
        self, mock_context, mock_settings, temp_db
    ):
        """Test MEMBER → ADMINISTRATOR transition should NOT trigger captcha."""
        from telegram.constants import ChatMemberStatus
        
        update = self.create_chat_member_update(ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR)
        
        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await chat_member_handler(update, mock_context)
        
        mock_context.bot.restrict_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_not_called()

    async def test_left_to_restricted_triggers_captcha(
        self, mock_context, mock_settings, temp_db
    ):
        """Test LEFT → RESTRICTED transition triggers captcha (user joined but auto-restricted)."""
        from telegram.constants import ChatMemberStatus
        
        update = self.create_chat_member_update(ChatMemberStatus.LEFT, ChatMemberStatus.RESTRICTED)
        
        sent_message = MagicMock()
        sent_message.chat_id = -1001234567890
        sent_message.message_id = 999
        mock_context.bot.send_message.return_value = sent_message
        
        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await chat_member_handler(update, mock_context)
        
        mock_context.bot.restrict_chat_member.assert_called_once()
        mock_context.bot.send_message.assert_called_once()

    async def test_duplicate_prevention_chat_member(
        self, mock_context, mock_settings, temp_db
    ):
        """Test that duplicate captcha is prevented in chat_member_handler."""
        from bot.database.service import get_database
        from telegram.constants import ChatMemberStatus
        
        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")
        
        update = self.create_chat_member_update(ChatMemberStatus.LEFT, ChatMemberStatus.MEMBER)
        
        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await chat_member_handler(update, mock_context)
        
        mock_context.bot.restrict_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_not_called()

    async def test_race_condition_handling(
        self, mock_context, mock_settings, temp_db
    ):
        """Test race condition handling when both handlers trigger simultaneously."""
        from sqlalchemy.exc import IntegrityError
        from telegram.constants import ChatMemberStatus
        
        update = self.create_chat_member_update(ChatMemberStatus.LEFT, ChatMemberStatus.MEMBER)
        
        sent_message = MagicMock()
        sent_message.chat_id = -1001234567890
        sent_message.message_id = 999
        mock_context.bot.send_message.return_value = sent_message
        
        with (
            patch("bot.handlers.captcha.get_settings", return_value=mock_settings),
            patch("bot.database.service.DatabaseService.add_pending_captcha") as mock_add,
        ):
            mock_add.side_effect = IntegrityError(None, None, None)
            await chat_member_handler(update, mock_context)
        
        # Should handle gracefully and not schedule timeout job
        mock_context.job_queue.run_once.assert_not_called()

    async def test_bot_member_skipped_in_chat_member(
        self, mock_context, mock_settings, temp_db
    ):
        """Test that bot members are skipped in chat_member_handler."""
        from telegram.constants import ChatMemberStatus
        
        update = self.create_chat_member_update(ChatMemberStatus.LEFT, ChatMemberStatus.MEMBER)
        update.chat_member.new_chat_member.user.is_bot = True
        
        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await chat_member_handler(update, mock_context)
        
        mock_context.bot.restrict_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_not_called()

    async def test_captcha_disabled_skips_in_chat_member(
        self, mock_context, mock_settings, temp_db
    ):
        """Test captcha disabled skips processing in chat_member_handler."""
        from telegram.constants import ChatMemberStatus
        
        mock_settings.captcha_enabled = False
        update = self.create_chat_member_update(ChatMemberStatus.LEFT, ChatMemberStatus.MEMBER)
        
        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await chat_member_handler(update, mock_context)
        
        mock_context.bot.restrict_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_not_called()

    async def test_wrong_group_skipped_in_chat_member(
        self, mock_context, mock_settings, temp_db
    ):
        """Test wrong group is skipped in chat_member_handler."""
        from telegram.constants import ChatMemberStatus
        
        update = self.create_chat_member_update(
            ChatMemberStatus.LEFT, ChatMemberStatus.MEMBER, group_id=-9999999999
        )
        
        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await chat_member_handler(update, mock_context)
        
        mock_context.bot.restrict_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_not_called()

    async def test_no_chat_member_does_nothing(self, mock_context, mock_settings):
        """Test that missing chat_member in update does nothing."""
        update = MagicMock()
        update.chat_member = None
        
        with patch("bot.handlers.captcha.get_settings", return_value=mock_settings):
            await chat_member_handler(update, mock_context)
        
        mock_context.bot.restrict_chat_member.assert_not_called()
