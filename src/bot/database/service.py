"""
Database service for the PythonID bot.

This module provides the DatabaseService class for all database operations,
plus module-level functions for initialization and access. Uses SQLModel
with SQLite backend for persistence.
"""

import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, delete, select

from bot.database.models import (
    NewUserProbation,
    PendingCaptchaValidation,
    PhotoVerificationWhitelist,
    TrustedUser,
    UserWarning,
)

logger = logging.getLogger(__name__)


class DatabaseService:
    """
    Service class for database operations.

    Handles CRUD operations for user warnings and restrictions.
    Includes automatic migrations for schema changes.
    """

    def __init__(self, database_path: str):
        """
        Initialize database connection and create tables.

        Args:
            database_path: Path to SQLite database file.
                Parent directories are created if they don't exist.
        """
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Register datetime adapters for SQLite to avoid deprecation warnings
        # in Python 3.12+. SQLAlchemy's default datetime handling is deprecated.
        sqlite3.register_adapter(datetime, lambda val: val.isoformat())

        self._engine = create_engine(f"sqlite:///{database_path}")

        with self._engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
            conn.exec_driver_sql("PRAGMA synchronous=NORMAL;")
        logger.info("SQLite WAL mode enabled")

        SQLModel.metadata.create_all(self._engine)

        # Migrate existing tables: add new columns if missing
        self._migrate_trusted_users()

    def _migrate_trusted_users(self) -> None:
        """Add new columns to trusted_users if missing."""
        with self._engine.connect() as conn:
            columns = {
                row[1] for row in conn.exec_driver_sql(
                    "PRAGMA table_info(trusted_users)"
                ).fetchall()
            }
            for col, default in [
                ("user_full_name", "''"),
                ("username", "NULL"),
                ("admin_full_name", "''"),
                ("admin_username", "NULL"),
            ]:
                if col not in columns:
                    conn.exec_driver_sql(
                        f"ALTER TABLE trusted_users ADD COLUMN {col} TEXT DEFAULT {default}"
                    )
                    logger.info(f"Migrated trusted_users: added {col} column")
            conn.commit()

    def get_or_create_user_warning(self, user_id: int, group_id: int) -> UserWarning:
        """
        Get existing warning record or create a new one.

        Looks for an active (non-restricted) warning record for the user.
        If none exists, creates a new record with message_count=1.

        Args:
            user_id: Telegram user ID.
            group_id: Telegram group ID.

        Returns:
            UserWarning: Active warning record for the user.
        """
        with Session(self._engine) as session:
            # Look for active (non-restricted) warning record
            statement = select(UserWarning).where(
                UserWarning.user_id == user_id,
                UserWarning.group_id == group_id,
                ~UserWarning.is_restricted,
            )
            record = session.exec(statement).first()

            if record:
                logger.info(
                    f"Returning existing warning for user_id={user_id}, group_id={group_id}"
                )
                return record

            # Create new warning record
            new_record = UserWarning(
                user_id=user_id,
                group_id=group_id,
                message_count=1,
                first_warned_at=datetime.now(UTC),
                last_message_at=datetime.now(UTC),
            )
            session.add(new_record)
            session.commit()
            session.refresh(new_record)
            logger.info(
                f"Created new warning for user_id={user_id}, group_id={group_id}"
            )
            return new_record

    def increment_message_count(self, user_id: int, group_id: int) -> UserWarning:
        """
        Increment message count for an existing warning record.

        Called when user sends additional messages after first warning
        but before reaching the restriction threshold.

        Args:
            user_id: Telegram user ID.
            group_id: Telegram group ID.

        Returns:
            UserWarning: Updated warning record.

        Raises:
            ValueError: If no active warning record exists.
        """
        with Session(self._engine) as session:
            statement = select(UserWarning).where(
                UserWarning.user_id == user_id,
                UserWarning.group_id == group_id,
                ~UserWarning.is_restricted,
            )
            record = session.exec(statement).first()

            if record:
                record.message_count += 1
                record.last_message_at = datetime.now(UTC)
                session.add(record)
                session.commit()
                session.refresh(record)
                logger.info(
                    f"Incremented message count for user_id={user_id}, group_id={group_id}, new_count={record.message_count}"
                )
                return record

            raise ValueError(
                f"No warning record found for user {user_id} in group {group_id}"
            )

    def mark_user_restricted(self, user_id: int, group_id: int) -> UserWarning:
        """
        Mark user as restricted after reaching threshold.

        Sets is_restricted=True and restricted_by_bot=True to indicate
        this restriction was applied by the bot (not manually by admin).

        Args:
            user_id: Telegram user ID.
            group_id: Telegram group ID.

        Returns:
            UserWarning: Updated warning record.

        Raises:
            ValueError: If no active warning record exists.
        """
        with Session(self._engine) as session:
            statement = select(UserWarning).where(
                UserWarning.user_id == user_id,
                UserWarning.group_id == group_id,
                ~UserWarning.is_restricted,
            )
            record = session.exec(statement).first()

            if record:
                record.is_restricted = True
                record.restricted_by_bot = True
                record.last_message_at = datetime.now(UTC)
                session.add(record)
                session.commit()
                session.refresh(record)
                logger.info(
                    f"Marked user as restricted: user_id={user_id}, group_id={group_id}"
                )
                return record

            raise ValueError(
                f"No warning record found for user {user_id} in group {group_id}"
            )

    def is_user_restricted_by_bot(self, user_id: int, group_id: int) -> bool:
        """
        Check if user was restricted by this bot.

        Only returns True if user has a record where both is_restricted
        and restricted_by_bot are True. Users restricted by admins
        (not tracked in our database) will return False.

        Args:
            user_id: Telegram user ID.
            group_id: Telegram group ID.

        Returns:
            bool: True if user was restricted by this bot.
        """
        with Session(self._engine) as session:
            statement = select(UserWarning).where(
                UserWarning.user_id == user_id,
                UserWarning.group_id == group_id,
                UserWarning.is_restricted,
                UserWarning.restricted_by_bot,
            )
            record = session.exec(statement).first()
            return record is not None

    def mark_user_unrestricted(self, user_id: int, group_id: int) -> None:
        """
        Clear bot restriction flag after user is unrestricted via DM.

        Sets restricted_by_bot=False so the bot won't try to unrestrict
        the user again (e.g., if admin later restricts them manually).

        Args:
            user_id: Telegram user ID.
            group_id: Telegram group ID.
        """
        with Session(self._engine) as session:
            statement = select(UserWarning).where(
                UserWarning.user_id == user_id,
                UserWarning.group_id == group_id,
                UserWarning.is_restricted,
                UserWarning.restricted_by_bot,
            )
            record = session.exec(statement).first()

            if record:
                record.restricted_by_bot = False
                session.add(record)
                session.commit()
                logger.info(
                    f"Cleared restriction flag: user_id={user_id}, group_id={group_id}"
                )

    def delete_user_warnings(self, user_id: int, group_id: int) -> int:
        """
        Delete all warning records for a user in a specific group.

        This completely removes warning history for the user, allowing them
        to start fresh. Used when admins manually verify/whitelist users.

        Args:
            user_id: Telegram user ID.
            group_id: Telegram group ID.

        Returns:
            int: Number of warning records deleted.
        """
        with Session(self._engine) as session:
            delete_statement = delete(UserWarning).where(
                UserWarning.user_id == user_id,
                UserWarning.group_id == group_id,
            )
            result = session.exec(delete_statement)
            session.commit()
            count = result.rowcount
            logger.info(
                f"Deleted warnings: user_id={user_id}, group_id={group_id}, count={count}"
            )
            return count

    def add_photo_verification_whitelist(
        self, user_id: int, verified_by_admin_id: int, notes: str | None = None
    ) -> PhotoVerificationWhitelist:
        """
        Add user to photo verification whitelist.

        Args:
            user_id: Telegram user ID.
            verified_by_admin_id: Telegram user ID of admin performing verification.
            notes: Optional notes about the verification.

        Returns:
            PhotoVerificationWhitelist: Created whitelist record.

        Raises:
            ValueError: If user is already whitelisted.
        """
        with Session(self._engine) as session:
            statement = select(PhotoVerificationWhitelist).where(
                PhotoVerificationWhitelist.user_id == user_id
            )
            existing = session.exec(statement).first()

            if existing:
                raise ValueError(f"User {user_id} is already whitelisted")

            record = PhotoVerificationWhitelist(
                user_id=user_id,
                verified_by_admin_id=verified_by_admin_id,
                notes=notes,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            logger.info(
                f"Added to photo whitelist: user_id={user_id}, admin_id={verified_by_admin_id}"
            )
            return record

    def is_user_photo_whitelisted(self, user_id: int) -> bool:
        """
        Check if user is in photo verification whitelist.

        Args:
            user_id: Telegram user ID.

        Returns:
            bool: True if user is whitelisted.
        """
        with Session(self._engine) as session:
            statement = select(PhotoVerificationWhitelist).where(
                PhotoVerificationWhitelist.user_id == user_id
            )
            record = session.exec(statement).first()
            return record is not None

    def remove_photo_verification_whitelist(self, user_id: int) -> None:
        """
        Remove user from photo verification whitelist.

        Args:
            user_id: Telegram user ID.

        Raises:
            ValueError: If user is not in whitelist.
        """
        with Session(self._engine) as session:
            statement = select(PhotoVerificationWhitelist).where(
                PhotoVerificationWhitelist.user_id == user_id
            )
            record = session.exec(statement).first()

            if not record:
                raise ValueError(f"User {user_id} is not in whitelist")

            session.delete(record)
            session.commit()
            logger.info(f"Removed from photo whitelist: user_id={user_id}")

    def add_trusted_user(
        self,
        user_id: int,
        trusted_by_admin_id: int,
        group_id: int = 0,
        notes: str | None = None,
        user_full_name: str = "",
        username: str | None = None,
        admin_full_name: str = "",
        admin_username: str | None = None,
    ) -> TrustedUser:
        """
        Add a user to trusted list.

        Args:
            user_id: Telegram user ID.
            trusted_by_admin_id: Telegram user ID of admin granting trust.
            group_id: Trust scope ID (0 means global).
            notes: Optional admin notes.
            user_full_name: Display name of the trusted user.
            username: Username of the trusted user.
            admin_full_name: Display name of the admin.
            admin_username: Username of the admin.

        Returns:
            TrustedUser: Created trusted record.

        Raises:
            ValueError: If user is already trusted in the scope.
        """
        with Session(self._engine) as session:
            statement = select(TrustedUser).where(
                TrustedUser.user_id == user_id,
                TrustedUser.group_id == group_id,
            )
            existing = session.exec(statement).first()

            if existing:
                raise ValueError(f"User {user_id} is already trusted for scope {group_id}")

            record = TrustedUser(
                user_id=user_id,
                group_id=group_id,
                trusted_by_admin_id=trusted_by_admin_id,
                notes=notes,
                user_full_name=user_full_name,
                username=username,
                admin_full_name=admin_full_name,
                admin_username=admin_username,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            logger.info(
                f"Added trusted user: user_id={user_id}, admin_id={trusted_by_admin_id}, scope={group_id}"
            )
            return record

    def remove_trusted_user(self, user_id: int, group_id: int = 0) -> None:
        """
        Remove a user from trusted list.

        Args:
            user_id: Telegram user ID.
            group_id: Trust scope ID (0 means global).

        Raises:
            ValueError: If user is not trusted in the scope.
        """
        with Session(self._engine) as session:
            statement = select(TrustedUser).where(
                TrustedUser.user_id == user_id,
                TrustedUser.group_id == group_id,
            )
            record = session.exec(statement).first()

            if not record:
                raise ValueError(f"User {user_id} is not trusted for scope {group_id}")

            session.delete(record)
            session.commit()
            logger.info(f"Removed trusted user: user_id={user_id}, scope={group_id}")

    def update_trusted_user_names(
        self,
        user_id: int,
        user_full_name: str,
        username: str | None,
        admin_full_name: str = "",
        admin_username: str | None = None,
    ) -> None:
        """Update cached display names for a trusted user.

        Used by backfill script to populate names for users trusted
        before the cache feature was deployed.
        """
        with Session(self._engine) as session:
            statement = select(TrustedUser).where(
                TrustedUser.user_id == user_id,
                TrustedUser.group_id == 0,
            )
            record = session.exec(statement).first()
            if record:
                record.user_full_name = user_full_name
                record.username = username
                record.admin_full_name = admin_full_name
                record.admin_username = admin_username
                session.add(record)
                session.commit()

    def is_user_trusted(self, user_id: int) -> bool:
        """
        Check whether a user is trusted.

        Returns:
            bool: True if user is trusted globally.
        """
        with Session(self._engine) as session:
            statement = select(TrustedUser).where(
                TrustedUser.user_id == user_id,
                TrustedUser.group_id == 0,
            )
            record = session.exec(statement).first()
            return record is not None

    def get_trusted_user_ids(self) -> set[int]:
        """
        Get trusted user IDs.

        Returns:
            set[int]: Trusted user IDs scoped to global (group_id=0).
        """
        with Session(self._engine) as session:
            statement = select(TrustedUser.user_id).where(TrustedUser.group_id == 0)
            return set(session.exec(statement).all())

    def get_trusted_users(self) -> list[TrustedUser]:
        """
        Get trusted user records with metadata.

        Returns:
            list[TrustedUser]: Trusted user records scoped to global (group_id=0).
        """
        with Session(self._engine) as session:
            statement = (
                select(TrustedUser)
                .where(TrustedUser.group_id == 0)
                .order_by(TrustedUser.trusted_at.desc())
            )
            return list(session.exec(statement).all())

    def get_warnings_past_time_threshold_for_group(
        self, group_id: int, threshold: timedelta
    ) -> list[UserWarning]:
        """
        Find active warnings for a specific group that exceeded the time threshold.

        Args:
            group_id: Telegram group ID to filter by.
            threshold: Time duration since first warning to trigger restriction.

        Returns:
            list[UserWarning]: Warning records that should be auto-restricted.
        """
        with Session(self._engine) as session:
            cutoff_time = datetime.now(UTC) - threshold
            statement = select(UserWarning).where(
                UserWarning.group_id == group_id,
                ~UserWarning.is_restricted,
                UserWarning.first_warned_at <= cutoff_time,
            )
            records = session.exec(statement).all()
            logger.info(
                f"Found {len(records)} warnings past {threshold} threshold for group {group_id}"
            )
            return [record for record in records]

    def add_pending_captcha(
        self,
        user_id: int,
        group_id: int,
        chat_id: int,
        message_id: int,
        user_full_name: str,
    ) -> PendingCaptchaValidation:
        """
        Add a pending captcha validation record for a new user.

        Args:
            user_id: Telegram user ID.
            group_id: Telegram group ID.
            chat_id: Chat ID where the challenge message was sent.
            message_id: Message ID of the captcha challenge message.
            user_full_name: Full name of the user for constructing mentions.

        Returns:
            PendingCaptchaValidation: Created pending validation record.
        """
        with Session(self._engine) as session:
            record = PendingCaptchaValidation(
                user_id=user_id,
                group_id=group_id,
                chat_id=chat_id,
                message_id=message_id,
                user_full_name=user_full_name,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            logger.info(f"Added pending captcha: user_id={user_id}, group_id={group_id}")
            return record

    def get_pending_captcha(
        self, user_id: int, group_id: int
    ) -> PendingCaptchaValidation | None:
        """
        Get pending captcha validation for a user.

        Args:
            user_id: Telegram user ID.
            group_id: Telegram group ID.

        Returns:
            PendingCaptchaValidation | None: Pending validation record or None.
        """
        with Session(self._engine) as session:
            statement = select(PendingCaptchaValidation).where(
                PendingCaptchaValidation.user_id == user_id,
                PendingCaptchaValidation.group_id == group_id,
            )
            return session.exec(statement).first()

    def remove_pending_captcha(self, user_id: int, group_id: int) -> bool:
        """
        Remove pending captcha validation for a user.

        Args:
            user_id: Telegram user ID.
            group_id: Telegram group ID.

        Returns:
            bool: True if a record was deleted, False if no record existed.
        """
        with Session(self._engine) as session:
            statement = delete(PendingCaptchaValidation).where(
                PendingCaptchaValidation.user_id == user_id,
                PendingCaptchaValidation.group_id == group_id,
            )
            result = session.exec(statement)
            session.commit()
            success = result.rowcount > 0
            logger.info(
                f"Removed pending captcha: user_id={user_id}, group_id={group_id}, success={success}"
            )
            return success

    def get_all_pending_captchas(self) -> list[PendingCaptchaValidation]:
        """
        Get all pending captcha validations.

        Used on bot startup to recover lost timeout jobs.

        Returns:
            list[PendingCaptchaValidation]: All pending validation records.
        """
        with Session(self._engine) as session:
            statement = select(PendingCaptchaValidation)
            return list(session.exec(statement).all())

    def get_all_new_user_probations(self) -> list[NewUserProbation]:
        """
        Get all new-user probation records.

        Returns:
            list[NewUserProbation]: All probation records.
        """
        with Session(self._engine) as session:
            statement = select(NewUserProbation)
            return list(session.exec(statement).all())

    def start_new_user_probation(self, user_id: int, group_id: int) -> NewUserProbation:
        """
        Start or refresh probation for a new user.

        Called when a user joins or passes captcha verification.
        If a record exists, refreshes joined_at to current time.

        Args:
            user_id: Telegram user ID.
            group_id: Telegram group ID.

        Returns:
            NewUserProbation: Created or updated probation record.
        """
        with Session(self._engine) as session:
            statement = select(NewUserProbation).where(
                NewUserProbation.user_id == user_id,
                NewUserProbation.group_id == group_id,
            )
            record = session.exec(statement).first()

            if record:
                record.joined_at = datetime.now(UTC)
                record.violation_count = 0
                record.first_violation_at = None
                record.last_violation_at = None
            else:
                record = NewUserProbation(
                    user_id=user_id,
                    group_id=group_id,
                )
            session.add(record)
            session.commit()
            session.refresh(record)
            logger.info(f"Started probation for user_id={user_id}, group_id={group_id}")
            return record

    def get_new_user_probation(
        self, user_id: int, group_id: int
    ) -> NewUserProbation | None:
        """
        Get probation record for a user.

        Args:
            user_id: Telegram user ID.
            group_id: Telegram group ID.

        Returns:
            NewUserProbation | None: Probation record or None if not found.
        """
        with Session(self._engine) as session:
            statement = select(NewUserProbation).where(
                NewUserProbation.user_id == user_id,
                NewUserProbation.group_id == group_id,
            )
            return session.exec(statement).first()

    def increment_new_user_violation(
        self, user_id: int, group_id: int
    ) -> NewUserProbation:
        """
        Increment violation count for a user on probation atomically.

        Uses atomic SQL update to prevent race conditions when multiple
        violations occur simultaneously.

        Args:
            user_id: Telegram user ID.
            group_id: Telegram group ID.

        Returns:
            NewUserProbation: Updated probation record.

        Raises:
            ValueError: If no probation record exists.
        """
        from sqlalchemy import update as sql_update
        
        with Session(self._engine) as session:
            # First check if record exists
            select_stmt = select(NewUserProbation).where(
                NewUserProbation.user_id == user_id,
                NewUserProbation.group_id == group_id,
            )
            record = session.exec(select_stmt).first()

            if not record:
                raise ValueError(f"No probation record for user {user_id} in group {group_id}")

            now = datetime.now(UTC)
            
            # Atomic update - increment directly in SQL
            update_stmt = (
                sql_update(NewUserProbation)
                .where(NewUserProbation.id == record.id)
                .values(
                    violation_count=NewUserProbation.violation_count + 1,
                    first_violation_at=now if record.first_violation_at is None else record.first_violation_at,
                    last_violation_at=now,
                )
            )
            session.exec(update_stmt)
            session.commit()
            
            # Refresh to get updated values
            session.refresh(record)
            logger.info(
                f"Incremented violation for user_id={user_id}, group_id={group_id}, "
                f"count={record.violation_count}"
            )
            return record

    def clear_new_user_probation(self, user_id: int, group_id: int) -> None:
        """
        Remove probation record for a user (when probation expires).

        Args:
            user_id: Telegram user ID.
            group_id: Telegram group ID.
        """
        with Session(self._engine) as session:
            statement = delete(NewUserProbation).where(
                NewUserProbation.user_id == user_id,
                NewUserProbation.group_id == group_id,
            )
            session.exec(statement)
            session.commit()
            logger.info(f"Cleared probation for user_id={user_id}, group_id={group_id}")


# Module-level singleton for database service
_db_service: DatabaseService | None = None


def init_database(database_path: str) -> DatabaseService:
    """
    Initialize the database service singleton.

    Must be called once at application startup before any database operations.

    Args:
        database_path: Path to SQLite database file.

    Returns:
        DatabaseService: Initialized database service instance.
    """
    global _db_service
    _db_service = DatabaseService(database_path)
    return _db_service


def get_database() -> DatabaseService:
    """
    Get the database service singleton.

    Returns:
        DatabaseService: Database service instance.

    Raises:
        RuntimeError: If init_database() hasn't been called.
    """
    if _db_service is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _db_service


def reset_database() -> None:
    """
    Reset database service singleton (for testing).

    Clears the singleton so a new database can be initialized.
    Properly disposes of the engine to close all connections.
    """
    global _db_service
    if _db_service is not None:
        _db_service._engine.dispose()
    _db_service = None
