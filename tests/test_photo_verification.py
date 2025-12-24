import tempfile
from pathlib import Path

import pytest

from bot.database.models import PhotoVerificationWhitelist
from bot.database.service import get_database, init_database, reset_database


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_database(str(db_path))
        yield db_path
        reset_database()


@pytest.fixture
def db_service(temp_db):
    return get_database()


class TestPhotoVerificationWhitelist:
    def test_add_user_to_whitelist(self, db_service):
        record = db_service.add_photo_verification_whitelist(
            user_id=12345,
            verified_by_admin_id=99999,
            notes="Privacy settings hide photo",
        )

        assert record.user_id == 12345
        assert record.verified_by_admin_id == 99999
        assert record.notes == "Privacy settings hide photo"
        assert record.verified_at is not None

    def test_add_user_without_notes(self, db_service):
        record = db_service.add_photo_verification_whitelist(
            user_id=12345, verified_by_admin_id=99999
        )

        assert record.user_id == 12345
        assert record.notes is None

    def test_duplicate_user_raises_error(self, db_service):
        db_service.add_photo_verification_whitelist(
            user_id=12345, verified_by_admin_id=99999
        )

        with pytest.raises(ValueError, match="already whitelisted"):
            db_service.add_photo_verification_whitelist(
                user_id=12345, verified_by_admin_id=88888
            )

    def test_is_user_photo_whitelisted_returns_true(self, db_service):
        db_service.add_photo_verification_whitelist(
            user_id=12345, verified_by_admin_id=99999
        )

        assert db_service.is_user_photo_whitelisted(12345) is True

    def test_is_user_photo_whitelisted_returns_false(self, db_service):
        assert db_service.is_user_photo_whitelisted(99999) is False

    def test_multiple_users_whitelisted(self, db_service):
        db_service.add_photo_verification_whitelist(
            user_id=111, verified_by_admin_id=99999
        )
        db_service.add_photo_verification_whitelist(
            user_id=222, verified_by_admin_id=99999
        )
        db_service.add_photo_verification_whitelist(
            user_id=333, verified_by_admin_id=88888
        )

        assert db_service.is_user_photo_whitelisted(111) is True
        assert db_service.is_user_photo_whitelisted(222) is True
        assert db_service.is_user_photo_whitelisted(333) is True
        assert db_service.is_user_photo_whitelisted(444) is False

    def test_remove_user_from_whitelist(self, db_service):
        db_service.add_photo_verification_whitelist(
            user_id=12345, verified_by_admin_id=99999
        )

        db_service.remove_photo_verification_whitelist(user_id=12345)

        assert db_service.is_user_photo_whitelisted(12345) is False

    def test_remove_non_existent_user_raises_error(self, db_service):
        with pytest.raises(ValueError, match="not in whitelist"):
            db_service.remove_photo_verification_whitelist(user_id=99999)

    def test_remove_then_readd_user(self, db_service):
        db_service.add_photo_verification_whitelist(
            user_id=12345, verified_by_admin_id=99999
        )

        db_service.remove_photo_verification_whitelist(user_id=12345)
        assert db_service.is_user_photo_whitelisted(12345) is False

        db_service.add_photo_verification_whitelist(
            user_id=12345, verified_by_admin_id=88888
        )
        assert db_service.is_user_photo_whitelisted(12345) is True
