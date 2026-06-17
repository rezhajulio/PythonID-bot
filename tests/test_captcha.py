import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.database.service import init_database, reset_database
from bot.group_config import GroupConfig, GroupRegistry
from bot.services.user_checker import ProfileCheckResult
from bot.handlers.captcha import (
    captcha_callback_handler,
    captcha_timeout_callback,
    chat_member_handler,
    new_member_handler,
)


@pytest.fixture
def group_config():
    return GroupConfig(
        group_id=-1001234567890,
        warning_topic_id=0,
        captcha_enabled=True,
        captcha_timeout_seconds=300,
    )


@pytest.fixture
def mock_registry(group_config):
    registry = GroupRegistry()
    registry.register(group_config)
    return registry


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
        self, mock_update_new_member, mock_context, group_config, temp_db
    ):
        sent_message = MagicMock()
        sent_message.chat_id = -1001234567890
        sent_message.message_id = 999
        mock_context.bot.send_message.return_value = sent_message

        with patch("bot.handlers.captcha.get_group_config_for_update", return_value=group_config):
            await new_member_handler(mock_update_new_member, mock_context)

        mock_context.bot.restrict_chat_member.assert_called_once()
        call_args = mock_context.bot.restrict_chat_member.call_args
        assert call_args.kwargs["chat_id"] == -1001234567890
        assert call_args.kwargs["user_id"] == 12345

    async def test_new_member_sends_captcha_message(
        self, mock_update_new_member, mock_context, group_config, temp_db
    ):
        sent_message = MagicMock()
        sent_message.chat_id = -1001234567890
        sent_message.message_id = 999
        mock_context.bot.send_message.return_value = sent_message

        with patch("bot.handlers.captcha.get_group_config_for_update", return_value=group_config):
            await new_member_handler(mock_update_new_member, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert call_args.kwargs["chat_id"] == -1001234567890
        assert "Selamat datang" in call_args.kwargs["text"]
        assert "300 detik" in call_args.kwargs["text"]
        assert call_args.kwargs["reply_markup"] is not None

    async def test_new_member_saves_to_database(
        self, mock_update_new_member, mock_context, group_config, temp_db
    ):
        from bot.database.service import get_database

        sent_message = MagicMock()
        sent_message.chat_id = -1001234567890
        sent_message.message_id = 999
        mock_context.bot.send_message.return_value = sent_message

        with patch("bot.handlers.captcha.get_group_config_for_update", return_value=group_config):
            await new_member_handler(mock_update_new_member, mock_context)

        db = get_database()
        pending = db.get_pending_captcha(12345, -1001234567890)
        assert pending is not None
        assert pending.user_id == 12345
        assert pending.group_id == -1001234567890
        assert pending.message_id == 999

    async def test_new_member_schedules_timeout(
        self, mock_update_new_member, mock_context, group_config, temp_db
    ):
        sent_message = MagicMock()
        sent_message.chat_id = -1001234567890
        sent_message.message_id = 999
        mock_context.bot.send_message.return_value = sent_message

        with patch("bot.handlers.captcha.get_group_config_for_update", return_value=group_config):
            await new_member_handler(mock_update_new_member, mock_context)

        mock_context.job_queue.run_once.assert_called_once()
        call_args = mock_context.job_queue.run_once.call_args
        assert call_args.kwargs["when"] == 300
        assert call_args.kwargs["name"] == "captcha_timeout_-1001234567890_12345"
        assert call_args.kwargs["data"]["user_id"] == 12345

    async def test_captcha_disabled_skips_check(
        self, mock_update_new_member, mock_context, temp_db
    ):
        disabled_config = GroupConfig(
            group_id=-1001234567890,
            warning_topic_id=0,
            captcha_enabled=False,
            captcha_timeout_seconds=300,
        )

        with patch("bot.handlers.captcha.get_group_config_for_update", return_value=disabled_config):
            await new_member_handler(mock_update_new_member, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_not_called()

    async def test_bot_members_skipped(
        self, mock_update_new_member, mock_context, group_config, temp_db
    ):
        mock_update_new_member.message.new_chat_members[0].is_bot = True

        with patch("bot.handlers.captcha.get_group_config_for_update", return_value=group_config):
            await new_member_handler(mock_update_new_member, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_not_called()

    async def test_no_message_does_nothing(self, mock_context):
        update = MagicMock()
        update.message = None

        await new_member_handler(update, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()

    async def test_no_new_members_does_nothing(self, mock_context):
        update = MagicMock()
        update.message = MagicMock()
        update.message.new_chat_members = None

        await new_member_handler(update, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()

    async def test_wrong_group_skipped(
        self, mock_update_new_member, mock_context, temp_db
    ):
        mock_update_new_member.effective_chat.id = -9999999999

        with patch("bot.handlers.captcha.get_group_config_for_update", return_value=None):
            await new_member_handler(mock_update_new_member, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_not_called()

    async def test_restrict_failure_continues_gracefully(
        self, mock_update_new_member, mock_context, group_config, temp_db
    ):
        mock_context.bot.restrict_chat_member.side_effect = Exception(
            "Restriction failed"
        )

        with patch("bot.handlers.captcha.get_group_config_for_update", return_value=group_config):
            await new_member_handler(mock_update_new_member, mock_context)

        mock_context.bot.send_message.assert_not_called()

    async def test_duplicate_prevention_new_member_handler(
        self, mock_update_new_member, mock_context, group_config, temp_db
    ):
        """Test that duplicate captcha is prevented in new_member_handler."""
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        with patch("bot.handlers.captcha.get_group_config_for_update", return_value=group_config):
            await new_member_handler(mock_update_new_member, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_not_called()


class TestCaptchaCallbackHandler:
    @staticmethod
    def _make_callback_query(*, user_id=12345, group_id=-1001234567890,
                             full_name="Test User", username="testuser"):
        query = MagicMock()
        query.data = f"captcha_verify_{group_id}_{user_id}"
        query.from_user = MagicMock(id=user_id, full_name=full_name, username=username)
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        return query

    async def test_captcha_callback_verifies_correct_user(
        self, mock_context, mock_registry, temp_db
    ):
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        query = self._make_callback_query()

        update = MagicMock()
        update.callback_query = query

        with (
            patch("bot.handlers.captcha.get_group_registry", return_value=mock_registry),
            patch("bot.handlers.captcha.check_user_profile", return_value=ProfileCheckResult(has_profile_photo=True, has_username=True)),
        ):
            await captcha_callback_handler(update, mock_context)

        query.answer.assert_called_once()
        assert db.get_pending_captcha(12345, -1001234567890) is None

    async def test_captcha_callback_unrestricts_user(
        self, mock_context, mock_registry, temp_db
    ):
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        query = self._make_callback_query()

        update = MagicMock()
        update.callback_query = query

        with (
            patch("bot.handlers.captcha.get_group_registry", return_value=mock_registry),
            patch("bot.handlers.captcha.unrestrict_user") as mock_unrestrict,
            patch("bot.handlers.captcha.check_user_profile", return_value=ProfileCheckResult(has_profile_photo=True, has_username=True)),
        ):
            mock_unrestrict.return_value = AsyncMock()
            await captcha_callback_handler(update, mock_context)

        mock_unrestrict.assert_called_once()
        assert mock_unrestrict.call_args.args[1] == -1001234567890
        assert mock_unrestrict.call_args.args[2] == 12345

    async def test_captcha_callback_deletes_message(
        self, mock_context, mock_registry, temp_db
    ):
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        query = self._make_callback_query()

        update = MagicMock()
        update.callback_query = query

        with (
            patch("bot.handlers.captcha.get_group_registry", return_value=mock_registry),
            patch("bot.handlers.captcha.unrestrict_user", return_value=AsyncMock()),
            patch("bot.handlers.captcha.check_user_profile", return_value=ProfileCheckResult(has_profile_photo=True, has_username=True)),
        ):
            await captcha_callback_handler(update, mock_context)

        query.edit_message_text.assert_called_once()
        call_args = query.edit_message_text.call_args
        assert "Terima kasih" in call_args.kwargs["text"]

    async def test_wrong_user_rejected(self, mock_context, mock_registry, temp_db):
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        query = MagicMock()
        query.answer = AsyncMock()
        query.from_user = MagicMock()
        query.from_user.id = 99999
        query.data = "captcha_verify_-1001234567890_12345"

        update = MagicMock()
        update.callback_query = query

        with (
            patch("bot.handlers.captcha.get_group_registry", return_value=mock_registry),
            patch("bot.handlers.captcha.unrestrict_user") as mock_unrestrict,
        ):
            await captcha_callback_handler(update, mock_context)

        query.answer.assert_called_once()
        assert "bukan untukmu" in query.answer.call_args.args[0]
        assert query.answer.call_args.kwargs["show_alert"] is True
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

    async def test_cancels_timeout_job(self, mock_context, mock_registry, temp_db):
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        mock_job = MagicMock()
        mock_job.schedule_removal = MagicMock()
        mock_context.job_queue.get_jobs_by_name.return_value = [mock_job]

        query = self._make_callback_query()

        update = MagicMock()
        update.callback_query = query

        with (
            patch("bot.handlers.captcha.get_group_registry", return_value=mock_registry),
            patch("bot.handlers.captcha.unrestrict_user", return_value=AsyncMock()),
            patch("bot.handlers.captcha.check_user_profile", return_value=ProfileCheckResult(has_profile_photo=True, has_username=True)),
        ):
            await captcha_callback_handler(update, mock_context)

        mock_context.job_queue.get_jobs_by_name.assert_called_once_with(
            "captcha_timeout_-1001234567890_12345"
        )
        mock_job.schedule_removal.assert_called_once()

    async def test_unrestrict_failure_keeps_user_restricted(
        self, mock_context, mock_registry, temp_db
    ):
        """unrestrict_user fails AFTER successful DB cleanup. User stays
        restricted on Telegram, DB row is gone (so timeout is a no-op),
        verify button is gone. User waits for admin action — we never
        reported success on a state we couldn't fully transition."""
        from bot.constants import CAPTCHA_FAILED_VERIFICATION_MESSAGE
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        mock_job = MagicMock()
        mock_job.schedule_removal = MagicMock()
        mock_context.job_queue.get_jobs_by_name.return_value = [mock_job]

        query = self._make_callback_query()

        update = MagicMock()
        update.callback_query = query

        with (
            patch("bot.handlers.captcha.get_group_registry", return_value=mock_registry),
            patch("bot.handlers.captcha.unrestrict_user", side_effect=Exception("Forbidden: bot is not an admin")),
            patch("bot.handlers.captcha.check_user_profile", return_value=ProfileCheckResult(has_profile_photo=True, has_username=True)),
        ):
            await captcha_callback_handler(update, mock_context)

        # DB was cleaned (finalization ran first in the new order).
        assert db.get_pending_captcha(12345, -1001234567890) is None
        # No success message edit.
        query.edit_message_text.assert_not_called()
        # User sees the failure alert exactly once.
        query.answer.assert_called_once_with(CAPTCHA_FAILED_VERIFICATION_MESSAGE, show_alert=True)

    async def test_db_finalization_failure_keeps_user_restricted(
        self, mock_context, mock_registry, temp_db
    ):
        """db.remove_pending_captcha raises. User stays restricted on
        Telegram, DB row preserved, timeout still armed — user can retry."""
        from bot.constants import CAPTCHA_FAILED_VERIFICATION_MESSAGE
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        query = self._make_callback_query()

        update = MagicMock()
        update.callback_query = query

        with (
            patch("bot.handlers.captcha.get_group_registry", return_value=mock_registry),
            patch("bot.handlers.captcha.check_user_profile", return_value=ProfileCheckResult(has_profile_photo=True, has_username=True)),
            patch("bot.handlers.captcha.unrestrict_user") as mock_unrestrict,
            patch.object(db, "remove_pending_captcha", side_effect=Exception("DB locked")),
        ):
            await captcha_callback_handler(update, mock_context)

        # DB cleanup failed first → user stays restricted, DB row preserved.
        assert db.get_pending_captcha(12345, -1001234567890) is not None
        # No success message edit.
        query.edit_message_text.assert_not_called()
        # User sees the failure alert exactly once.
        query.answer.assert_called_once_with(CAPTCHA_FAILED_VERIFICATION_MESSAGE, show_alert=True)
        # Telegram unrestrict was NOT called (DB failure short-circuits).
        mock_unrestrict.assert_not_called()

    async def test_edit_message_failure_in_callback_continues_gracefully(
        self, mock_context, mock_registry, temp_db
    ):
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        query = self._make_callback_query()
        query.edit_message_text.side_effect = Exception("Edit failed")

        update = MagicMock()
        update.callback_query = query

        with (
            patch("bot.handlers.captcha.get_group_registry", return_value=mock_registry),
            patch("bot.handlers.captcha.unrestrict_user", return_value=AsyncMock()),
            patch("bot.handlers.captcha.check_user_profile", return_value=ProfileCheckResult(has_profile_photo=True, has_username=True)),
        ):
            await captcha_callback_handler(update, mock_context)

        assert db.get_pending_captcha(12345, -1001234567890) is None

    async def test_incomplete_profile_blocks_verification(
        self, mock_context, mock_registry, temp_db
    ):
        """Test that incomplete profile shows alert and does not verify."""
        from bot.constants import CAPTCHA_INCOMPLETE_PROFILE_MESSAGE
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        query = MagicMock()
        query.answer = AsyncMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.from_user.username = None
        query.from_user.full_name = "Test User"
        query.data = "captcha_verify_-1001234567890_12345"
        query.edit_message_text = AsyncMock()

        update = MagicMock()
        update.callback_query = query

        incomplete_profile = ProfileCheckResult(has_profile_photo=True, has_username=False)
        with (
            patch("bot.handlers.captcha.get_group_registry", return_value=mock_registry),
            patch("bot.handlers.captcha.check_user_profile", return_value=incomplete_profile),
        ):
            await captcha_callback_handler(update, mock_context)

        query.answer.assert_called_once()
        call_args = query.answer.call_args
        expected = CAPTCHA_INCOMPLETE_PROFILE_MESSAGE.format(missing_text="username")
        assert call_args.args[0] == expected
        assert call_args.kwargs["show_alert"] is True
        query.edit_message_text.assert_not_called()
        assert db.get_pending_captcha(12345, -1001234567890) is not None

    async def test_unknown_group_in_callback_rejects(
        self, mock_context, mock_registry, temp_db
    ):
        """Test that a callback with an unregistered group_id is rejected."""
        from bot.constants import CAPTCHA_FAILED_VERIFICATION_MESSAGE
        query = MagicMock()
        query.answer = AsyncMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.data = "captcha_verify_-9999999999_12345"

        update = MagicMock()
        update.callback_query = query

        with patch("bot.handlers.captcha.get_group_registry", return_value=mock_registry):
            await captcha_callback_handler(update, mock_context)

        query.answer.assert_called_once_with(
            CAPTCHA_FAILED_VERIFICATION_MESSAGE, show_alert=True
        )

    @pytest.mark.parametrize("missing_items", [
        ["foto profil publik"],
        ["foto profil publik", "username"],
        ["username"],
    ])
    async def test_captcha_callback_incomplete_profile_rejected(
        self, mock_context, mock_registry, temp_db, missing_items
    ):
        from bot.constants import CAPTCHA_INCOMPLETE_PROFILE_MESSAGE, MISSING_ITEMS_SEPARATOR
        from bot.database.service import get_database

        has_photo = "foto profil publik" not in missing_items
        has_username = "username" not in missing_items

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        query = self._make_callback_query(username=None if not has_username else "testuser")

        update = MagicMock()
        update.callback_query = query

        with (
            patch("bot.handlers.captcha.get_group_registry", return_value=mock_registry),
            patch("bot.handlers.captcha.check_user_profile",
                  return_value=ProfileCheckResult(has_profile_photo=has_photo, has_username=has_username)),
            patch("bot.handlers.captcha.unrestrict_user") as mock_unrestrict,
        ):
            await captcha_callback_handler(update, mock_context)

        query.answer.assert_called_once()
        call_args = query.answer.call_args
        assert call_args.kwargs["show_alert"] is True
        expected = CAPTCHA_INCOMPLETE_PROFILE_MESSAGE.format(
            missing_text=MISSING_ITEMS_SEPARATOR.join(missing_items)
        )
        assert call_args.args[0] == expected
        mock_unrestrict.assert_not_called()
        assert db.get_pending_captcha(12345, -1001234567890) is not None
        mock_context.job_queue.get_jobs_by_name.assert_not_called()


    async def test_captcha_callback_profile_check_exception(
        self, mock_context, mock_registry, temp_db
    ):
        from bot.constants import CAPTCHA_PROFILE_CHECK_FAILED_MESSAGE
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        query = self._make_callback_query()

        update = MagicMock()
        update.callback_query = query

        with (
            patch("bot.handlers.captcha.get_group_registry", return_value=mock_registry),
            patch("bot.handlers.captcha.check_user_profile", side_effect=Exception("API error")),
            patch("bot.handlers.captcha.unrestrict_user") as mock_unrestrict,
        ):
            await captcha_callback_handler(update, mock_context)

        query.answer.assert_called_once_with(CAPTCHA_PROFILE_CHECK_FAILED_MESSAGE, show_alert=True)
        mock_unrestrict.assert_not_called()
        assert db.get_pending_captcha(12345, -1001234567890) is not None
        mock_context.job_queue.get_jobs_by_name.assert_not_called()

    async def test_captcha_callback_incomplete_profile_timeout_not_cancelled(
        self, mock_context, mock_registry, temp_db
    ):
        from bot.database.service import get_database

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        mock_job = MagicMock()
        mock_job.schedule_removal = MagicMock()
        mock_context.job_queue.get_jobs_by_name.return_value = [mock_job]

        query = self._make_callback_query()

        update = MagicMock()
        update.callback_query = query

        with (
            patch("bot.handlers.captcha.get_group_registry", return_value=mock_registry),
            patch("bot.handlers.captcha.check_user_profile", return_value=ProfileCheckResult(has_profile_photo=False, has_username=True)),
        ):
            await captcha_callback_handler(update, mock_context)

        mock_context.job_queue.get_jobs_by_name.assert_not_called()
        mock_job.schedule_removal.assert_not_called()

    @pytest.mark.parametrize("bad_data", [
        "captcha_verify_baddata",          # non-numeric, single token
        "captcha_verify_",                  # missing parts (IndexError)
        "captcha_verify_abc_def",           # int parse fails (ValueError)
        "captcha_verify_-100_abc",          # second part unparseable
    ])
    async def test_malformed_callback_data_rejected(self, mock_context, bad_data):
        from bot.constants import CAPTCHA_FAILED_VERIFICATION_MESSAGE
        query = MagicMock()
        query.answer = AsyncMock()
        query.from_user = MagicMock()
        query.from_user.id = 12345
        query.data = bad_data

        update = MagicMock()
        update.callback_query = query

        await captcha_callback_handler(update, mock_context)

        query.answer.assert_called_once_with(
            CAPTCHA_FAILED_VERIFICATION_MESSAGE, show_alert=True
        )
        query.edit_message_text.assert_not_called()

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
        new_member.user.username = "testuser"
        update.chat_member.new_chat_member = new_member

        update.effective_chat = MagicMock()
        update.effective_chat.id = group_id

        return update

    async def test_left_to_member_triggers_captcha(
        self, mock_context, group_config, temp_db
    ):
        """Test LEFT -> MEMBER transition triggers captcha."""
        from telegram.constants import ChatMemberStatus

        update = self.create_chat_member_update(ChatMemberStatus.LEFT, ChatMemberStatus.MEMBER)

        sent_message = MagicMock()
        sent_message.chat_id = -1001234567890
        sent_message.message_id = 999
        mock_context.bot.send_message.return_value = sent_message

        with patch("bot.handlers.captcha.get_group_config_for_update", return_value=group_config):
            await chat_member_handler(update, mock_context)

        mock_context.bot.restrict_chat_member.assert_called_once()
        mock_context.bot.send_message.assert_called_once()

    async def test_banned_to_member_triggers_captcha(
        self, mock_context, group_config, temp_db
    ):
        """Test BANNED -> MEMBER transition triggers captcha."""
        from telegram.constants import ChatMemberStatus

        update = self.create_chat_member_update(ChatMemberStatus.BANNED, ChatMemberStatus.MEMBER)

        sent_message = MagicMock()
        sent_message.chat_id = -1001234567890
        sent_message.message_id = 999
        mock_context.bot.send_message.return_value = sent_message

        with patch("bot.handlers.captcha.get_group_config_for_update", return_value=group_config):
            await chat_member_handler(update, mock_context)

        mock_context.bot.restrict_chat_member.assert_called_once()
        mock_context.bot.send_message.assert_called_once()

    async def test_member_to_administrator_no_captcha(
        self, mock_context, group_config, temp_db
    ):
        """Test MEMBER -> ADMINISTRATOR transition should NOT trigger captcha."""
        from telegram.constants import ChatMemberStatus

        update = self.create_chat_member_update(ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR)

        with patch("bot.handlers.captcha.get_group_config_for_update", return_value=group_config):
            await chat_member_handler(update, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_not_called()

    async def test_left_to_restricted_triggers_captcha(
        self, mock_context, group_config, temp_db
    ):
        """Test LEFT -> RESTRICTED transition triggers captcha (user joined but auto-restricted)."""
        from telegram.constants import ChatMemberStatus

        update = self.create_chat_member_update(ChatMemberStatus.LEFT, ChatMemberStatus.RESTRICTED)

        sent_message = MagicMock()
        sent_message.chat_id = -1001234567890
        sent_message.message_id = 999
        mock_context.bot.send_message.return_value = sent_message

        with patch("bot.handlers.captcha.get_group_config_for_update", return_value=group_config):
            await chat_member_handler(update, mock_context)

        mock_context.bot.restrict_chat_member.assert_called_once()
        mock_context.bot.send_message.assert_called_once()

    async def test_duplicate_prevention_chat_member(
        self, mock_context, group_config, temp_db
    ):
        """Test that duplicate captcha is prevented in chat_member_handler."""
        from bot.database.service import get_database
        from telegram.constants import ChatMemberStatus

        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        update = self.create_chat_member_update(ChatMemberStatus.LEFT, ChatMemberStatus.MEMBER)

        with patch("bot.handlers.captcha.get_group_config_for_update", return_value=group_config):
            await chat_member_handler(update, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_not_called()

    async def test_race_condition_handling(
        self, mock_context, group_config, temp_db
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
            patch("bot.handlers.captcha.get_group_config_for_update", return_value=group_config),
            patch("bot.database.service.DatabaseService.add_pending_captcha") as mock_add,
        ):
            mock_add.side_effect = IntegrityError(None, None, None)
            await chat_member_handler(update, mock_context)

        # Should handle gracefully and not schedule timeout job
        mock_context.job_queue.run_once.assert_not_called()

    async def test_bot_member_skipped_in_chat_member(
        self, mock_context, group_config, temp_db
    ):
        """Test that bot members are skipped in chat_member_handler."""
        from telegram.constants import ChatMemberStatus

        update = self.create_chat_member_update(ChatMemberStatus.LEFT, ChatMemberStatus.MEMBER)
        update.chat_member.new_chat_member.user.is_bot = True

        with patch("bot.handlers.captcha.get_group_config_for_update", return_value=group_config):
            await chat_member_handler(update, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_not_called()

    async def test_captcha_disabled_skips_in_chat_member(
        self, mock_context, temp_db
    ):
        """Test captcha disabled skips processing in chat_member_handler."""
        from telegram.constants import ChatMemberStatus

        disabled_config = GroupConfig(
            group_id=-1001234567890,
            warning_topic_id=0,
            captcha_enabled=False,
            captcha_timeout_seconds=300,
        )
        update = self.create_chat_member_update(ChatMemberStatus.LEFT, ChatMemberStatus.MEMBER)

        with patch("bot.handlers.captcha.get_group_config_for_update", return_value=disabled_config):
            await chat_member_handler(update, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_not_called()

    async def test_wrong_group_skipped_in_chat_member(
        self, mock_context, temp_db
    ):
        """Test wrong group is skipped in chat_member_handler."""
        from telegram.constants import ChatMemberStatus

        update = self.create_chat_member_update(
            ChatMemberStatus.LEFT, ChatMemberStatus.MEMBER, group_id=-9999999999
        )

        with patch("bot.handlers.captcha.get_group_config_for_update", return_value=None):
            await chat_member_handler(update, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_not_called()

    async def test_no_chat_member_does_nothing(self, mock_context):
        """Test that missing chat_member in update does nothing."""
        update = MagicMock()
        update.chat_member = None

        await chat_member_handler(update, mock_context)

        mock_context.bot.restrict_chat_member.assert_not_called()
