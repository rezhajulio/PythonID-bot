"""
Shared Telegram utility functions.

This module provides common helper functions for working with
Telegram's API across different handlers and services.
"""

import logging

from telegram import Bot, Message, User
from telegram.constants import ChatMemberStatus
from telegram.error import BadRequest, Forbidden
from telegram.helpers import mention_markdown

logger = logging.getLogger(__name__)


def get_user_mention(user: User) -> str:
    """
    Get a formatted mention string for a user.

    Returns `@username` if the user has a username, otherwise returns
    a markdown mention using the user's full name and ID.

    Args:
        user: Telegram User object.

    Returns:
        str: Formatted user mention (either @username or markdown mention).
    """
    return (
        f"@{user.username}"
        if user.username
        else mention_markdown(user.id, user.full_name, version=1)
    )


def get_user_mention_by_id(user_id: int, user_full_name: str) -> str:
    """
    Get a formatted markdown mention for a user by ID and name.

    Used when only user ID and full name are available (not a full User object).

    Args:
        user_id: Telegram user ID.
        user_full_name: User's full name.

    Returns:
        str: Markdown mention string.
    """
    return mention_markdown(user_id, user_full_name, version=1)


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
    logger.info(f"Getting user status for user_id={user_id}, group_id={group_id}")
    try:
        user_member = await bot.get_chat_member(
            chat_id=group_id,
            user_id=user_id,
        )
        return user_member.status
    except (BadRequest, Forbidden) as e:
        logger.error(
            f"Failed to get user status for user_id={user_id}, group_id={group_id}: {e}",
            exc_info=True,
        )
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
    logger.info(f"Unrestricting user_id={user_id} in group_id={group_id}")
    try:
        # Get group's default permissions
        chat = await bot.get_chat(group_id)
        default_permissions = chat.permissions
        
        # Apply default permissions to remove restrictions
        await bot.restrict_chat_member(
            chat_id=group_id,
            user_id=user_id,
            permissions=default_permissions,
        )
    except Exception as e:
        logger.error(
            f"Failed to unrestrict user_id={user_id} in group_id={group_id}: {e}",
            exc_info=True,
        )
        raise


def extract_forwarded_user(message: Message) -> tuple[int, str] | None:
    """
    Extract user ID and name from a forwarded message.
    
    Args:
        message: Telegram Message object that was forwarded.
        
    Returns:
        Tuple of (user_id, user_name) if extraction successful, None otherwise.
    """
    forwarded_user = None
    if message.forward_origin:
        if hasattr(message.forward_origin, 'sender_user'):
            forwarded_user = message.forward_origin.sender_user
    elif message.forward_from:
        forwarded_user = message.forward_from

    if not forwarded_user:
        return None
    
    user_id = forwarded_user.id
    user_name = forwarded_user.full_name if hasattr(forwarded_user, 'full_name') else forwarded_user.first_name
    return user_id, user_name


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
        admin_ids = [admin.user.id for admin in admins]
        logger.info(f"Fetched {len(admin_ids)} admins from group_id={group_id}")
        return admin_ids
    except (BadRequest, Forbidden) as e:
        logger.error(
            f"Failed to fetch admins from group_id={group_id}: {e}",
            exc_info=True,
        )
        raise Exception(f"Failed to fetch admins from group {group_id}: {e}")
