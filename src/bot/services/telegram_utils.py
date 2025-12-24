"""
Shared Telegram utility functions.

This module provides common helper functions for working with
Telegram's API across different handlers and services.
"""

from telegram import Bot
from telegram.constants import ChatMemberStatus
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes


async def get_user_status(
    bot: Bot | ContextTypes.DEFAULT_TYPE,
    group_id: int,
    user_id: int,
) -> ChatMemberStatus | None:
    """
    Get user's membership status in the group.

    Args:
        bot: Telegram bot instance or context.
        group_id: Telegram group ID.
        user_id: Telegram user ID.

    Returns:
        ChatMemberStatus | None: User status (MEMBER, RESTRICTED, LEFT, BANNED, etc.)
            or None if unable to fetch (e.g., bot not in group).
    """
    try:
        # Handle both Bot and ContextTypes
        actual_bot = bot.bot if hasattr(bot, "bot") else bot
        user_member = await actual_bot.get_chat_member(
            chat_id=group_id,
            user_id=user_id,
        )
        return user_member.status
    except (BadRequest, Forbidden):
        return None
