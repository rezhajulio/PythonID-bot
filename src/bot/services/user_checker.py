"""
User profile checker service for the PythonID bot.

This module provides utilities for checking if a Telegram user has
a complete profile (public photo and username set).
"""

from dataclasses import dataclass

from telegram import Bot, User

from bot.database.service import get_database


@dataclass
class ProfileCheckResult:
    """
    Result of a user profile completeness check.

    Attributes:
        has_profile_photo: True if user has at least one public profile photo.
        has_username: True if user has a username set.
    """

    has_profile_photo: bool
    has_username: bool

    @property
    def is_complete(self) -> bool:
        """
        Check if profile is complete (has both photo and username).

        Returns:
            bool: True if both photo and username are present.
        """
        return self.has_profile_photo and self.has_username

    def get_missing_items(self) -> list[str]:
        """
        Get list of missing profile items in Indonesian.

        Returns:
            list[str]: List of missing items (e.g., ["foto profil publik", "username"]).
        """
        missing = []
        if not self.has_profile_photo:
            missing.append("foto profil publik")
        if not self.has_username:
            missing.append("username")
        return missing


async def check_user_profile(bot: Bot, user: User) -> ProfileCheckResult:
    """
    Check if a user's profile is complete.

    A complete profile requires:
    1. At least one public profile photo (or whitelisted)
    2. A username set

    Note: Profile photos are fetched via API as they're not included
    in the User object. This makes one API call per check unless user
    is in the whitelist.

    Args:
        bot: Telegram bot instance for API calls.
        user: User object to check.

    Returns:
        ProfileCheckResult: Result containing photo and username status.
    """
    has_username = user.username is not None

    db = get_database()
    if db.is_user_photo_whitelisted(user.id):
        has_profile_photo = True
    else:
        photos = await bot.get_user_profile_photos(user.id, limit=1)
        has_profile_photo = photos.total_count > 0

    return ProfileCheckResult(
        has_profile_photo=has_profile_photo,
        has_username=has_username,
    )
