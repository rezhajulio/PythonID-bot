import logging
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session, text

from bot.database.service import get_database, init_database, reset_database
from bot.services.captcha_recovery import (
    handle_captcha_expiration,
    recover_pending_captchas,
)


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.group_id = -1001234567890
    settings.captcha_timeout_seconds = 300
    settings.captcha_timeout_timedelta = timedelta(seconds=300)
    return settings


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_database(str(db_path))
        yield db_path
        reset_database()


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.edit_message_text = AsyncMock()
    return bot


@pytest.fixture
def mock_application(mock_bot):
    app = MagicMock()
    app.bot = mock_bot
    app.job_queue = MagicMock()
    app.job_queue.run_once = MagicMock()
    return app


class TestHandleCaptchaExpiration:
    async def test_handle_captcha_expiration_success(
        self, mock_bot, temp_db, caplog
    ):
        caplog.set_level(logging.INFO)
        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        with patch("bot.services.captcha_recovery.BotInfoCache.get_username") as mock_username:
            mock_username.return_value = "testbot"
            
            await handle_captcha_expiration(
                bot=mock_bot,
                user_id=12345,
                group_id=-1001234567890,
                chat_id=-1001234567890,
                message_id=999,
                user_full_name="Test User",
            )

        mock_bot.edit_message_text.assert_called_once()
        call_args = mock_bot.edit_message_text.call_args
        assert call_args.kwargs["chat_id"] == -1001234567890
        assert call_args.kwargs["message_id"] == 999
        assert call_args.kwargs["parse_mode"] == "Markdown"
        assert "tidak menyelesaikan verifikasi" in call_args.kwargs["text"]

        assert db.get_pending_captcha(12345, -1001234567890) is None

        assert "User 12345 captcha timeout - kept restricted" in caplog.text

    async def test_handle_captcha_expiration_already_verified(
        self, mock_bot, temp_db, caplog
    ):
        caplog.set_level(logging.DEBUG)
        await handle_captcha_expiration(
            bot=mock_bot,
            user_id=12345,
            group_id=-1001234567890,
            chat_id=-1001234567890,
            message_id=999,
            user_full_name="Test User",
        )

        mock_bot.edit_message_text.assert_not_called()
        assert "No pending captcha for user 12345, already verified" in caplog.text

    async def test_handle_captcha_expiration_message_edit_fails(
        self, mock_bot, temp_db, caplog
    ):
        caplog.set_level(logging.ERROR)
        db = get_database()
        db.add_pending_captcha(12345, -1001234567890, -1001234567890, 999, "Test User")

        mock_bot.edit_message_text.side_effect = Exception("Edit failed")

        with patch("bot.services.captcha_recovery.BotInfoCache.get_username") as mock_username:
            mock_username.return_value = "testbot"
            
            await handle_captcha_expiration(
                bot=mock_bot,
                user_id=12345,
                group_id=-1001234567890,
                chat_id=-1001234567890,
                message_id=999,
                user_full_name="Test User",
            )

        assert "Failed to edit captcha timeout message: Edit failed" in caplog.text
        assert db.get_pending_captcha(12345, -1001234567890) is None


class TestRecoverPendingCaptchas:
    async def test_recover_pending_captchas_no_records(
        self, mock_application, mock_settings, temp_db, caplog
    ):
        caplog.set_level(logging.INFO)
        with patch("bot.services.captcha_recovery.get_settings", return_value=mock_settings):
            await recover_pending_captchas(mock_application)

        assert "No pending captcha verifications to recover" in caplog.text
        mock_application.job_queue.run_once.assert_not_called()

    async def test_recover_pending_captchas_expired_timeout(
        self, mock_application, mock_settings, temp_db, caplog
    ):
        caplog.set_level(logging.INFO)
        db = get_database()
        
        # Create a record that expired 100 seconds ago
        old_time = datetime.now(UTC) - timedelta(seconds=400)
        record = db.add_pending_captcha(
            12345, -1001234567890, -1001234567890, 999, "Test User"
        )
        
        # Manually update created_at to simulate old record
        with Session(db._engine) as session:
            stmt = text("UPDATE pending_validations SET created_at = :created_at WHERE id = :id")
            session.execute(stmt, {"created_at": old_time, "id": record.id})
            session.commit()

        with (
            patch("bot.services.captcha_recovery.get_settings", return_value=mock_settings),
            patch("bot.services.captcha_recovery.handle_captcha_expiration") as mock_expire,
        ):
            mock_expire.return_value = AsyncMock()
            await recover_pending_captchas(mock_application)

        mock_expire.assert_called_once_with(
            bot=mock_application.bot,
            user_id=12345,
            group_id=-1001234567890,
            chat_id=-1001234567890,
            message_id=999,
            user_full_name="Test User",
        )

        assert "Recovering 1 pending captcha verification(s)" in caplog.text
        assert "Expiring captcha for user 12345" in caplog.text
        assert "timeout passed" in caplog.text
        assert "Captcha recovery complete" in caplog.text

    async def test_recover_pending_captchas_reschedule_timeout(
        self, mock_application, mock_settings, temp_db, caplog
    ):
        caplog.set_level(logging.INFO)
        db = get_database()
        
        # Create a record with 150 seconds remaining (150 seconds ago)
        recent_time = datetime.now(UTC) - timedelta(seconds=150)
        record = db.add_pending_captcha(
            12345, -1001234567890, -1001234567890, 999, "Test User"
        )
        
        # Manually update created_at
        with Session(db._engine) as session:
            stmt = text("UPDATE pending_validations SET created_at = :created_at WHERE id = :id")
            session.execute(stmt, {"created_at": recent_time, "id": record.id})
            session.commit()

        with (
            patch("bot.services.captcha_recovery.get_settings", return_value=mock_settings),
            patch("bot.services.captcha_recovery.captcha_timeout_callback") as mock_callback,
        ):
            await recover_pending_captchas(mock_application)

        mock_application.job_queue.run_once.assert_called_once()
        call_args = mock_application.job_queue.run_once.call_args
        
        assert call_args.args[0] == mock_callback
        assert 149 <= call_args.kwargs["when"] <= 151  # Allow 1 second tolerance
        assert call_args.kwargs["name"] == "captcha_timeout_-1001234567890_12345"
        assert call_args.kwargs["data"]["user_id"] == 12345
        assert call_args.kwargs["data"]["group_id"] == -1001234567890
        assert call_args.kwargs["data"]["chat_id"] == -1001234567890
        assert call_args.kwargs["data"]["message_id"] == 999
        assert call_args.kwargs["data"]["user_full_name"] == "Test User"

        assert "Recovering 1 pending captcha verification(s)" in caplog.text
        assert "Rescheduling captcha timeout for user 12345" in caplog.text
        assert "remaining:" in caplog.text

    async def test_recover_pending_captchas_handles_errors(
        self, mock_application, mock_settings, temp_db, caplog
    ):
        caplog.set_level(logging.INFO)
        db = get_database()
        
        # Create a record
        record = db.add_pending_captcha(
            12345, -1001234567890, -1001234567890, 999, "Test User"
        )

        with (
            patch("bot.services.captcha_recovery.get_settings", return_value=mock_settings),
            patch("bot.services.captcha_recovery.handle_captcha_expiration") as mock_expire,
        ):
            mock_expire.side_effect = Exception("Something went wrong")
            
            # Manually update to make it expired
            old_time = datetime.now(UTC) - timedelta(seconds=400)
            with Session(db._engine) as session:
                stmt = text("UPDATE pending_validations SET created_at = :created_at WHERE id = :id")
                session.execute(stmt, {"created_at": old_time, "id": record.id})
                session.commit()
            
            await recover_pending_captchas(mock_application)

        assert "Failed to recover captcha for user 12345: Something went wrong" in caplog.text
        assert "Captcha recovery complete" in caplog.text

    async def test_recover_pending_captchas_multiple_records(
        self, mock_application, mock_settings, temp_db, caplog
    ):
        caplog.set_level(logging.INFO)
        db = get_database()
        
        # Create expired record
        old_time = datetime.now(UTC) - timedelta(seconds=400)
        record1 = db.add_pending_captcha(
            12345, -1001234567890, -1001234567890, 999, "User One"
        )
        
        # Create pending record
        recent_time = datetime.now(UTC) - timedelta(seconds=150)
        record2 = db.add_pending_captcha(
            67890, -1001234567890, -1001234567890, 888, "User Two"
        )
        
        # Manually update created_at for both
        with Session(db._engine) as session:
            stmt = text("UPDATE pending_validations SET created_at = :created_at WHERE id = :id")
            session.execute(stmt, {"created_at": old_time, "id": record1.id})
            session.execute(stmt, {"created_at": recent_time, "id": record2.id})
            session.commit()

        with (
            patch("bot.services.captcha_recovery.get_settings", return_value=mock_settings),
            patch("bot.services.captcha_recovery.handle_captcha_expiration") as mock_expire,
            patch("bot.services.captcha_recovery.captcha_timeout_callback"),
        ):
            mock_expire.return_value = AsyncMock()
            await recover_pending_captchas(mock_application)

        # Should expire the first one
        mock_expire.assert_called_once()
        assert mock_expire.call_args.kwargs["user_id"] == 12345
        
        # Should reschedule the second one
        mock_application.job_queue.run_once.assert_called_once()
        call_args = mock_application.job_queue.run_once.call_args
        assert call_args.kwargs["data"]["user_id"] == 67890

        assert "Recovering 2 pending captcha verification(s)" in caplog.text
        assert "Expiring captcha for user 12345" in caplog.text
        assert "Rescheduling captcha timeout for user 67890" in caplog.text
        assert "Captcha recovery complete" in caplog.text
