"""
Database models for the PythonID bot.

This module defines SQLModel schemas for persisting bot data to SQLite.
Currently tracks user warnings and restrictions for the progressive
enforcement system.
"""

from datetime import UTC, datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class UserWarning(SQLModel, table=True):
    """
    Tracks warning state for users with incomplete profiles.

    Each record represents a warning cycle for a user in a specific group.
    When a user is restricted and later unrestricted, the record is marked
    as no longer bot-restricted, and a new record is created if they
    violate rules again.

    Attributes:
        id: Primary key (auto-generated).
        user_id: Telegram user ID (indexed for fast lookups).
        group_id: Telegram group ID where the warning occurred.
        message_count: Number of messages sent since first warning.
        first_warned_at: Timestamp of first warning.
        last_message_at: Timestamp of most recent message.
        is_restricted: Whether user has been restricted (muted).
        restricted_by_bot: True if restriction was applied by this bot
            (vs manually by an admin). Only bot-created restrictions
            can be lifted via DM.
    """

    __tablename__ = "user_warnings"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    group_id: int = Field(index=True)
    message_count: int = Field(default=1)
    first_warned_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_message_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_restricted: bool = Field(default=False)
    restricted_by_bot: bool = Field(default=False)


class PhotoVerificationWhitelist(SQLModel, table=True):
    """
    Whitelist for users who have verified profile pictures but privacy settings
    prevent the bot from seeing them.

    This table allows admins to manually verify users whose profile pictures
    are hidden due to Telegram privacy settings, bypassing the automatic
    profile photo check.

    Attributes:
        id: Primary key (auto-generated).
        user_id: Telegram user ID (indexed, unique).
        verified_by_admin_id: Telegram user ID of the admin who verified.
        verified_at: Timestamp when verification was granted.
        notes: Optional notes about the verification.
    """

    __tablename__ = "photo_verification_whitelist"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, unique=True)
    verified_by_admin_id: int
    verified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: str | None = Field(default=None)


class PendingCaptchaValidation(SQLModel, table=True):
    """
    Tracks users who need to complete captcha verification.

    When a user joins or triggers verification, a challenge message is sent.
    This record tracks the pending verification so the bot can clean up
    the challenge message and take action if verification times out.

    Attributes:
        id: Primary key (auto-generated).
        user_id: Telegram user ID (indexed for fast lookups).
        group_id: Telegram group ID where the verification is required.
        chat_id: Telegram chat ID where the challenge was issued.
        message_id: ID of the challenge message to delete later.
        user_full_name: Full name of the user for constructing mentions.
        created_at: Timestamp when the challenge was issued.
    """

    __tablename__ = "pending_validations"
    __table_args__ = (
        UniqueConstraint('user_id', 'group_id', name='uix_user_group'),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    group_id: int = Field(index=True)
    chat_id: int = Field(index=True)
    message_id: int
    user_full_name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class NewUserProbation(SQLModel, table=True):
    """
    Tracks anti-spam probation for new users.

    Users under probation cannot send links or forwarded messages
    for a configurable period after joining. Violations are tracked
    and users are restricted after exceeding the threshold.

    Attributes:
        id: Primary key (auto-generated).
        user_id: Telegram user ID (indexed for fast lookups).
        group_id: Telegram group ID where probation applies.
        joined_at: Timestamp when probation started (after captcha verification).
        violation_count: Number of spam violations (forward/link messages).
        first_violation_at: Timestamp of first violation (for warnings).
        last_violation_at: Timestamp of most recent violation.
    """

    __tablename__ = "new_user_probation"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    group_id: int = Field(index=True)
    joined_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    violation_count: int = Field(default=0)
    first_violation_at: datetime | None = Field(default=None)
    last_violation_at: datetime | None = Field(default=None)
