"""
Database models for the PythonID bot.

This module defines SQLModel schemas for persisting bot data to SQLite.
Currently tracks user warnings and restrictions for the progressive
enforcement system.
"""

from datetime import UTC, datetime

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
