"""
Shared Telegram utility functions.

This module provides common helper functions for working with
Telegram's API across different handlers and services.
"""

from telegram import Bot
from telegram.constants import ChatMemberStatus
from telegram.error import BadRequest, Forbidden


async def get_user_status(
    bot: Bot,
    group_id: int,
    user_id: int,
) -> ChatMemberStatus | None:
    """
    Get user's membership status in the group.

    Args:
        bot: Telegram bot instance.
        group_id: Telegram group ID.
        user_id: Telegram user ID.

    Returns:
        ChatMemberStatus | None: User status (MEMBER, RESTRICTED, LEFT, BANNED, etc.)
            or None if unable to fetch (e.g., bot not in group).
    """
    try:
        user_member = await bot.get_chat_member(
            chat_id=group_id,
            user_id=user_id,
        )
        return user_member.status
    except (BadRequest, Forbidden):
        return None


async def unrestrict_user(
    bot: Bot,
    group_id: int,
    user_id: int,
) -> None:
    """
    Remove restrictions from a user by applying group's default permissions.
    
    This restores the user to normal member status in the group.
    Does NOT update the database - caller must handle that separately.
    
    Args:
        bot: Telegram bot instance.
        group_id: Telegram group ID.
        user_id: Telegram user ID to unrestrict.
    
    Raises:
        BadRequest: If user not found or bot lacks permissions.
    """
    # Get group's default permissions
    chat = await bot.get_chat(group_id)
    default_permissions = chat.permissions
    
    # Apply default permissions to remove restrictions
    await bot.restrict_chat_member(
        chat_id=group_id,
        user_id=user_id,
        permissions=default_permissions,
    )


async def fetch_group_admin_ids(bot: Bot, group_id: int) -> list[int]:
    """
    Fetch all administrator user IDs from a group.

    Args:
        bot: Telegram bot instance.
        group_id: Telegram group ID.

    Returns:
        list[int]: List of admin user IDs (including creator and administrators).

    Raises:
        Exception: If unable to fetch administrators (bot not in group, etc.).
    """
    try:
        admins = await bot.get_chat_administrators(group_id)
        return [admin.user.id for admin in admins]
    except (BadRequest, Forbidden) as e:
        raise Exception(f"Failed to fetch admins from group {group_id}: {e}")
