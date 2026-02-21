"""
Warning topic guard for the PythonID bot.

This module protects the warning topic by deleting messages from
non-admin users. Only group administrators and the bot itself can
post in the warning topic.
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.group_config import get_group_config_for_update

logger = logging.getLogger(__name__)


async def guard_warning_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Delete messages from non-admins in the warning topic.

    This handler runs with group=-1 (before other handlers) and deletes
    any messages in the warning topic that aren't from:
    - The bot itself
    - Group administrators or the group creator

    This keeps the warning topic clean for bot notifications only.

    Args:
        update: Telegram update containing the message.
        context: Bot context with helper methods.
    """
    try:
        # Skip if no message or sender
        if not update.message or not update.message.from_user:
            logger.info("No message or no sender, skipping")
            return

        group_config = get_group_config_for_update(update)
        user = update.message.from_user
        chat_id = update.effective_chat.id if update.effective_chat else None
        thread_id = update.message.message_thread_id

        logger.info(
            f"Topic guard called: user_id={user.id}, chat_id={chat_id}, thread_id={thread_id}"
        )

        # Only process messages from monitored groups
        if group_config is None:
            logger.info(
                f"Chat not monitored (chat_id={chat_id}), skipping"
            )
            return

        # Only guard the warning topic, not other topics
        if thread_id != group_config.warning_topic_id:
            logger.info(
                f"Wrong topic (thread_id={thread_id}, expected {group_config.warning_topic_id}), skipping"
            )
            return

        bot_id = context.bot.id

        # Allow bot's own messages
        if user.id == bot_id:
            logger.info(f"Allowing bot's own message (bot_id={bot_id})")
            return

        # Check if user is an admin or creator
        logger.info(f"Checking admin status for user {user.id} ({user.full_name})")
        chat_member = await context.bot.get_chat_member(
            chat_id=group_config.group_id,
            user_id=user.id,
        )

        admin_statuses = ("administrator", "creator")
        if chat_member.status in admin_statuses:
            logger.info(
                f"Allowing message from {chat_member.status} {user.id} ({user.full_name})"
            )
            return

        # Delete message from non-admin user
        logger.info(
            f"Deleting message from non-admin user {user.id} ({user.full_name}) "
            f"in warning topic (group_id={group_config.group_id}, thread_id={thread_id})"
        )
        await update.message.delete()

    except Exception as e:
        logger.error(
            f"Error in topic guard handler: {e}",
            exc_info=True,
        )
