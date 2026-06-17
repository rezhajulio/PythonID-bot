import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bot.database.models import UserWarning
from bot.database.service import (
    DatabaseService,
    get_database,
    init_database,
    reset_database,
)


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_database(str(db_path))
        yield db_path
        reset_database()


@pytest.fixture
def db_service(temp_db) -> DatabaseService:
    return get_database()


class TestDatabaseService:
    def test_creates_database_file(self, temp_db):
        assert temp_db.exists()

    def test_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "nested" / "path" / "test.db"
            init_database(str(db_path))
            assert db_path.exists()
            reset_database()


class TestGetOrCreateUserWarning:
    def test_creates_new_record(self, db_service):
        record = db_service.get_or_create_user_warning(user_id=123, group_id=-100999)

        assert record.user_id == 123
        assert record.group_id == -100999
        assert record.message_count == 1
        assert record.is_restricted is False

    def test_returns_existing_record(self, db_service):
        record1 = db_service.get_or_create_user_warning(user_id=123, group_id=-100999)
        record2 = db_service.get_or_create_user_warning(user_id=123, group_id=-100999)

        assert record1.id == record2.id
        assert record2.message_count == 1

    def test_different_users_get_different_records(self, db_service):
        record1 = db_service.get_or_create_user_warning(user_id=123, group_id=-100999)
        record2 = db_service.get_or_create_user_warning(user_id=456, group_id=-100999)

        assert record1.id != record2.id

    def test_creates_new_record_if_previous_was_restricted(self, db_service):
        record1 = db_service.get_or_create_user_warning(user_id=123, group_id=-100999)
        db_service.mark_user_restricted(user_id=123, group_id=-100999)

        record2 = db_service.get_or_create_user_warning(user_id=123, group_id=-100999)

        assert record1.id != record2.id
        assert record2.message_count == 1


class TestIncrementMessageCount:
    def test_increments_count(self, db_service):
        db_service.get_or_create_user_warning(user_id=123, group_id=-100999)

        record = db_service.increment_message_count(user_id=123, group_id=-100999)

        assert record.message_count == 2

    def test_increments_multiple_times(self, db_service):
        db_service.get_or_create_user_warning(user_id=123, group_id=-100999)

        db_service.increment_message_count(user_id=123, group_id=-100999)
        db_service.increment_message_count(user_id=123, group_id=-100999)
        record = db_service.increment_message_count(user_id=123, group_id=-100999)

        assert record.message_count == 4

    def test_raises_error_if_no_record(self, db_service):
        with pytest.raises(ValueError):
            db_service.increment_message_count(user_id=999, group_id=-100999)


class TestMarkUserRestricted:
    def test_marks_as_restricted(self, db_service):
        db_service.get_or_create_user_warning(user_id=123, group_id=-100999)

        record = db_service.mark_user_restricted(user_id=123, group_id=-100999)

        assert record.is_restricted is True

    def test_raises_error_if_no_record(self, db_service):
        with pytest.raises(ValueError):
            db_service.mark_user_restricted(user_id=999, group_id=-100999)

    def test_raises_error_if_already_restricted(self, db_service):
        db_service.get_or_create_user_warning(user_id=123, group_id=-100999)
        db_service.mark_user_restricted(user_id=123, group_id=-100999)

        with pytest.raises(ValueError):
            db_service.mark_user_restricted(user_id=123, group_id=-100999)

    def test_sets_restricted_by_bot_flag(self, db_service):
        db_service.get_or_create_user_warning(user_id=123, group_id=-100999)

        record = db_service.mark_user_restricted(user_id=123, group_id=-100999)

        assert record.restricted_by_bot is True


class TestIsUserRestrictedByBot:
    def test_returns_true_for_bot_restricted_user(self, db_service):
        db_service.get_or_create_user_warning(user_id=123, group_id=-100999)
        db_service.mark_user_restricted(user_id=123, group_id=-100999)

        assert db_service.is_user_restricted_by_bot(user_id=123, group_id=-100999) is True

    def test_returns_false_for_non_restricted_user(self, db_service):
        db_service.get_or_create_user_warning(user_id=123, group_id=-100999)

        assert db_service.is_user_restricted_by_bot(user_id=123, group_id=-100999) is False

    def test_returns_false_for_non_existent_user(self, db_service):
        assert db_service.is_user_restricted_by_bot(user_id=999, group_id=-100999) is False


class TestMarkUserUnrestricted:
    def test_clears_restricted_by_bot_flag(self, db_service):
        db_service.get_or_create_user_warning(user_id=123, group_id=-100999)
        db_service.mark_user_restricted(user_id=123, group_id=-100999)

        db_service.mark_user_unrestricted(user_id=123, group_id=-100999)

        assert db_service.is_user_restricted_by_bot(user_id=123, group_id=-100999) is False

    def test_does_nothing_for_non_existent_record(self, db_service):
        # Should not raise error
        db_service.mark_user_unrestricted(user_id=999, group_id=-100999)


class TestGetWarningsPastTimeThreshold:
    def test_returns_expired_warnings(self, db_service):
        # Create record with old timestamp
        old_time = datetime.now(UTC) - timedelta(minutes=1500)  # 25 hours
        record = db_service.get_or_create_user_warning(user_id=123, group_id=-100999)
        # Manually update to simulate old warning (in real tests, would mock time)
        from sqlmodel import Session, select

        with Session(db_service._engine) as session:
            stmt = select(UserWarning).where(UserWarning.id == record.id)
            db_record = session.exec(stmt).first()
            db_record.first_warned_at = old_time
            session.add(db_record)
            session.commit()

        # Should find the expired warning (1440 minutes = 24 hours)
        expired = db_service.get_warnings_past_time_threshold(timedelta(minutes=1440))
        assert len(expired) == 1
        assert expired[0].user_id == 123

    def test_ignores_recent_warnings(self, db_service):
        # Create record with recent timestamp (default)
        db_service.get_or_create_user_warning(user_id=123, group_id=-100999)

        # Should not find recent warnings
        expired = db_service.get_warnings_past_time_threshold(timedelta(minutes=1440))
        assert len(expired) == 0

    def test_ignores_restricted_users(self, db_service):
        # Create and restrict a user
        db_service.get_or_create_user_warning(user_id=123, group_id=-100999)
        db_service.mark_user_restricted(user_id=123, group_id=-100999)

        # Should not find restricted users even if old
        expired = db_service.get_warnings_past_time_threshold(timedelta(minutes=0))
        assert len(expired) == 0

    def test_returns_multiple_expired_warnings(self, db_service):
        # Create multiple old records
        for user_id in [123, 456, 789]:
            record = db_service.get_or_create_user_warning(
                user_id=user_id, group_id=-100999
            )
            from sqlmodel import Session, select

            with Session(db_service._engine) as session:
                stmt = select(UserWarning).where(UserWarning.id == record.id)
                db_record = session.exec(stmt).first()
                db_record.first_warned_at = datetime.now(UTC) - timedelta(minutes=1500)
                session.add(db_record)
                session.commit()

        expired = db_service.get_warnings_past_time_threshold(timedelta(minutes=1440))
        assert len(expired) == 3


class TestDeleteUserWarnings:
    def test_delete_user_warnings(self, db_service):
        # Create multiple warnings for same user
        db_service.get_or_create_user_warning(user_id=12345, group_id=-100111)
        db_service.increment_message_count(user_id=12345, group_id=-100111)
        db_service.mark_user_restricted(user_id=12345, group_id=-100111)

        # Verify warning exists
        assert db_service.is_user_restricted_by_bot(12345, -100111) is True

        # Delete warnings
        deleted_count = db_service.delete_user_warnings(user_id=12345, group_id=-100111)

        assert deleted_count == 1
        assert db_service.is_user_restricted_by_bot(12345, -100111) is False

    def test_delete_user_warnings_returns_zero_if_no_warnings(self, db_service):
        deleted_count = db_service.delete_user_warnings(user_id=99999, group_id=-100111)
        assert deleted_count == 0


class TestModuleLevelFunctions:
    def test_get_database_raises_error_before_init(self):
        """Test that get_database raises RuntimeError if init_database not called."""
        reset_database()

        with pytest.raises(RuntimeError, match="Database not initialized"):
            get_database()

    def test_init_database_returns_service(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            service = init_database(str(db_path))

            assert isinstance(service, DatabaseService)
            reset_database()

    def test_get_database_returns_same_instance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            init_database(str(db_path))

            service1 = get_database()
            service2 = get_database()

            assert service1 is service2
            reset_database()


class TestNewUserProbation:
    """Tests for new user probation CRUD operations."""

    def test_start_new_user_probation_creates_record(self, db_service: DatabaseService):
        """Test that start_new_user_probation creates a new record."""
        record = db_service.start_new_user_probation(user_id=1001, group_id=-100)

        assert record is not None
        assert record.user_id == 1001
        assert record.group_id == -100
        assert record.violation_count == 0
        assert record.first_violation_at is None
        assert record.last_violation_at is None

    def test_start_new_user_probation_resets_existing(self, db_service: DatabaseService):
        """Test that start_new_user_probation resets an existing record."""
        db_service.start_new_user_probation(user_id=1001, group_id=-100)
        db_service.increment_new_user_violation(user_id=1001, group_id=-100)

        record = db_service.start_new_user_probation(user_id=1001, group_id=-100)

        assert record.violation_count == 0
        assert record.first_violation_at is None

    def test_get_new_user_probation_returns_record(self, db_service: DatabaseService):
        """Test that get_new_user_probation returns existing record."""
        db_service.start_new_user_probation(user_id=1001, group_id=-100)

        record = db_service.get_new_user_probation(user_id=1001, group_id=-100)

        assert record is not None
        assert record.user_id == 1001

    def test_get_new_user_probation_returns_none_if_not_exists(
        self, db_service: DatabaseService
    ):
        """Test that get_new_user_probation returns None for non-existent user."""
        record = db_service.get_new_user_probation(user_id=9999, group_id=-100)

        assert record is None

    def test_increment_new_user_violation(self, db_service: DatabaseService):
        """Test that increment_new_user_violation updates count and timestamps."""
        db_service.start_new_user_probation(user_id=1001, group_id=-100)

        record = db_service.increment_new_user_violation(user_id=1001, group_id=-100)

        assert record.violation_count == 1
        assert record.first_violation_at is not None
        assert record.last_violation_at is not None

    def test_increment_new_user_violation_multiple_times(
        self, db_service: DatabaseService
    ):
        """Test that violations accumulate correctly."""
        db_service.start_new_user_probation(user_id=1001, group_id=-100)

        db_service.increment_new_user_violation(user_id=1001, group_id=-100)
        record = db_service.increment_new_user_violation(user_id=1001, group_id=-100)

        assert record.violation_count == 2

    def test_increment_new_user_violation_raises_if_no_record(
        self, db_service: DatabaseService
    ):
        """Test that increment raises ValueError if no probation record exists."""
        with pytest.raises(ValueError):
            db_service.increment_new_user_violation(user_id=9999, group_id=-100)

    def test_clear_new_user_probation(self, db_service: DatabaseService):
        """Test that clear_new_user_probation removes the record."""
        db_service.start_new_user_probation(user_id=1001, group_id=-100)

        db_service.clear_new_user_probation(user_id=1001, group_id=-100)

        record = db_service.get_new_user_probation(user_id=1001, group_id=-100)
        assert record is None


class TestGetWarningsPastTimeThresholdForGroup:
    def test_returns_empty_when_no_warnings(self, db_service):
        result = db_service.get_warnings_past_time_threshold_for_group(
            group_id=-100999, threshold=timedelta(minutes=1440)
        )
        assert result == []

    def test_returns_warnings_past_threshold_for_group(self, db_service):
        old_time = datetime.now(UTC) - timedelta(minutes=1500)
        record = db_service.get_or_create_user_warning(user_id=123, group_id=-100999)

        from sqlmodel import Session, select

        with Session(db_service._engine) as session:
            stmt = select(UserWarning).where(UserWarning.id == record.id)
            db_record = session.exec(stmt).first()
            db_record.first_warned_at = old_time
            session.add(db_record)
            session.commit()

        result = db_service.get_warnings_past_time_threshold_for_group(
            group_id=-100999, threshold=timedelta(minutes=1440)
        )
        assert len(result) == 1
        assert result[0].user_id == 123

    def test_does_not_return_warnings_from_different_group(self, db_service):
        old_time = datetime.now(UTC) - timedelta(minutes=1500)
        record = db_service.get_or_create_user_warning(user_id=123, group_id=-100999)

        from sqlmodel import Session, select

        with Session(db_service._engine) as session:
            stmt = select(UserWarning).where(UserWarning.id == record.id)
            db_record = session.exec(stmt).first()
            db_record.first_warned_at = old_time
            session.add(db_record)
            session.commit()

        result = db_service.get_warnings_past_time_threshold_for_group(
            group_id=-200888, threshold=timedelta(minutes=1440)
        )
        assert result == []

    def test_does_not_return_restricted_warnings(self, db_service):
        db_service.get_or_create_user_warning(user_id=123, group_id=-100999)
        db_service.mark_user_restricted(user_id=123, group_id=-100999)

        result = db_service.get_warnings_past_time_threshold_for_group(
            group_id=-100999, threshold=timedelta(minutes=0)
        )
        assert result == []


class TestTrustedUsers:
    def test_add_trusted_user_and_check_true(self, db_service: DatabaseService):
        db_service.add_trusted_user(user_id=123, trusted_by_admin_id=999)

        assert db_service.is_user_trusted(user_id=123) is True

    def test_add_trusted_user_duplicate_raises(self, db_service: DatabaseService):
        db_service.add_trusted_user(user_id=123, trusted_by_admin_id=999)

        with pytest.raises(ValueError):
            db_service.add_trusted_user(user_id=123, trusted_by_admin_id=999)

    def test_remove_trusted_user(self, db_service: DatabaseService):
        db_service.add_trusted_user(user_id=123, trusted_by_admin_id=999)

        db_service.remove_trusted_user(user_id=123)

        assert db_service.is_user_trusted(user_id=123) is False

    def test_remove_missing_trusted_user_raises(self, db_service: DatabaseService):
        with pytest.raises(ValueError):
            db_service.remove_trusted_user(user_id=123)

    def test_get_trusted_user_ids(self, db_service: DatabaseService):
        db_service.add_trusted_user(user_id=1001, trusted_by_admin_id=999)
        db_service.add_trusted_user(user_id=1002, trusted_by_admin_id=999)

        trusted_ids = db_service.get_trusted_user_ids()

        assert trusted_ids == {1001, 1002}

    def test_get_trusted_users_returns_metadata(self, db_service: DatabaseService):
        db_service.add_trusted_user(
            user_id=2001, trusted_by_admin_id=9001,
            user_full_name="Alice", username="alice",
            admin_full_name="Admin Alpha", admin_username="admin_alpha",
        )
        db_service.add_trusted_user(
            user_id=2002, trusted_by_admin_id=9002,
            user_full_name="Bob", username=None,
            admin_full_name="Admin Beta", admin_username=None,
        )

        trusted_users = db_service.get_trusted_users()

        assert len(trusted_users) == 2
        assert {u.user_id for u in trusted_users} == {2001, 2002}
        assert {u.trusted_by_admin_id for u in trusted_users} == {9001, 9002}
        by_id = {u.user_id: u for u in trusted_users}
        assert by_id[2001].user_full_name == "Alice"
        assert by_id[2001].username == "alice"
        assert by_id[2002].user_full_name == "Bob"
        assert by_id[2002].username is None
        assert by_id[2001].admin_full_name == "Admin Alpha"
        assert by_id[2001].admin_username == "admin_alpha"
        assert by_id[2002].admin_full_name == "Admin Beta"
        assert by_id[2002].admin_username is None

    def test_update_trusted_user_names(self, db_service: DatabaseService):
        """Backfill path: update_trusted_user_names writes all 4 cached fields."""
        db_service.add_trusted_user(
            user_id=2003, trusted_by_admin_id=9003,
            user_full_name="", username=None,
            admin_full_name="", admin_username=None,
        )

        db_service.update_trusted_user_names(
            user_id=2003,
            user_full_name="Carol", username="carol",
            admin_full_name="Admin Gamma", admin_username="admin_gamma",
        )

        record = next(r for r in db_service.get_trusted_users() if r.user_id == 2003)
        assert record.user_full_name == "Carol"
        assert record.username == "carol"
        assert record.admin_full_name == "Admin Gamma"
        assert record.admin_username == "admin_gamma"

    def test_update_trusted_user_names_missing_user_is_noop(
        self, db_service: DatabaseService
    ):
        """Backfill on unknown user_id must not raise (per the loop's per-record isolation)."""
        db_service.update_trusted_user_names(
            user_id=99999,
            user_full_name="X", username="x",
            admin_full_name="Y", admin_username="y",
        )
        assert db_service.is_user_trusted(99999) is False

    def test_update_trusted_user_names_destructive_overwrite(
        self, db_service: DatabaseService
    ):
        """Every call overwrites all 4 fields with caller-supplied values (default empty/None)."""
        db_service.add_trusted_user(
            user_id=2004, trusted_by_admin_id=9004,
            user_full_name="Real Name", username="real_user",
            admin_full_name="Real Admin", admin_username="real_admin",
        )

        # Caller only intends to touch user_full_name; other fields fall to defaults.
        # username is required-positional in the service signature, so pass it
        # explicitly as None; the test still pins destructive-overwrite for the
        # remaining 3 fields.
        db_service.update_trusted_user_names(
            user_id=2004, user_full_name="New Name", username=None,
        )

        record = next(r for r in db_service.get_trusted_users() if r.user_id == 2004)
        # Destructive: user_full_name updated, everything else clobbered to defaults.
        assert record.user_full_name == "New Name"
        assert record.username is None
        assert record.admin_full_name == ""
        assert record.admin_username is None

    def test_is_user_trusted_non_zero_group_raises(
        self, db_service: DatabaseService
    ):
        with pytest.raises(NotImplementedError):
            db_service.is_user_trusted(user_id=123, group_id=123)

    def test_get_trusted_user_ids_non_zero_group_raises(
        self, db_service: DatabaseService
    ):
        with pytest.raises(NotImplementedError):
            db_service.get_trusted_user_ids(group_id=123)

    def test_get_trusted_users_non_zero_group_raises(
        self, db_service: DatabaseService
    ):
        with pytest.raises(NotImplementedError):
            db_service.get_trusted_users(group_id=123)

    def test_trusted_user_reads_none_and_zero_group_equivalent(
        self, db_service: DatabaseService
    ):
        db_service.add_trusted_user(user_id=3001, trusted_by_admin_id=9001)
        db_service.add_trusted_user(user_id=3002, trusted_by_admin_id=9002)

        assert db_service.is_user_trusted(
            user_id=3001, group_id=None
        ) == db_service.is_user_trusted(user_id=3001, group_id=0)
        assert db_service.is_user_trusted(
            user_id=3001, group_id=None
        ) is True

        assert db_service.get_trusted_user_ids(
            group_id=None
        ) == db_service.get_trusted_user_ids(group_id=0)
        assert db_service.get_trusted_user_ids(group_id=None) == {3001, 3002}

        users_none = db_service.get_trusted_users(group_id=None)
        users_zero = db_service.get_trusted_users(group_id=0)
        assert [u.user_id for u in users_none] == [u.user_id for u in users_zero]
