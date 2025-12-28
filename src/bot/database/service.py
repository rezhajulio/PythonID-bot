"""
Database service for the PythonID bot.

This module provides the DatabaseService class for all database operations,
plus module-level functions for initialization and access. Uses SQLModel
with SQLite backend for persistence.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, delete, select

from bot.database.models import (
    PendingCaptchaValidation,
    PhotoVerificationWhitelist,
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

        self._engine = create_engine(f"sqlite:///{database_path}")
        SQLModel.metadata.create_all(self._engine)

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
            # First count records to be deleted
            count_statement = select(UserWarning).where(
                UserWarning.user_id == user_id,
                UserWarning.group_id == group_id,
            )
            count = len(session.exec(count_statement).all())

            # Bulk delete using SQLModel delete statement
            delete_statement = delete(UserWarning).where(
                UserWarning.user_id == user_id,
                UserWarning.group_id == group_id,
            )
            session.exec(delete_statement)
            session.commit()
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

    def get_warnings_past_time_threshold(
        self, minutes_threshold: int
    ) -> list[UserWarning]:
        """
        Find all active warnings that have exceeded the time threshold.

        Looks for non-restricted warning records where the time elapsed
        since first_warned_at exceeds the threshold, regardless of message count.

        Args:
            minutes_threshold: Number of minutes since first warning to trigger restriction.

        Returns:
            list[UserWarning]: List of warning records that should be auto-restricted.
        """
        from datetime import timedelta

        with Session(self._engine) as session:
            cutoff_time = datetime.now(UTC) - timedelta(minutes=minutes_threshold)
            statement = select(UserWarning).where(
                ~UserWarning.is_restricted,
                UserWarning.first_warned_at <= cutoff_time,
            )
            records = session.exec(statement).all()
            logger.info(
                f"Found {len(records)} warnings past {minutes_threshold}min threshold"
            )
            # Detach from session before returning
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
