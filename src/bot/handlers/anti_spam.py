"""
Anti-spam handler for new users on probation.

This module enforces anti-spam rules for newly joined users. During the
probation period, users cannot send forwarded messages or links. Violations
result in message deletion, a warning on first offense, and restriction
after exceeding the threshold.
"""

import logging
from datetime import UTC, datetime
from urllib.parse import urlparse

from telegram import Message, MessageEntity, Update
from telegram.ext import ContextTypes

from bot.config import get_settings
from bot.constants import (
    NEW_USER_SPAM_RESTRICTION,
    NEW_USER_SPAM_WARNING,
    RESTRICTED_PERMISSIONS,
    WHITELISTED_URL_DOMAINS,
    format_hours_display,
)
from bot.database.service import get_database
from bot.services.telegram_utils import get_user_mention

logger = logging.getLogger(__name__)


def is_forwarded(message: Message) -> bool:
    """
    Check if a message is forwarded.

    Telegram Bot API v7+ uses forward_origin to indicate forwarded messages.

    Args:
        message: Telegram message to check.

    Returns:
        bool: True if message is forwarded.
    """
    return message.forward_origin is not None


def has_link(message: Message) -> bool:
    """
    Check if a message contains URLs or text links.

    Checks both message entities and caption entities for URL types.

    Args:
        message: Telegram message to check.

    Returns:
        bool: True if message contains links.
    """
    entities = list(message.entities or []) + list(message.caption_entities or [])
    link_types = {MessageEntity.URL, MessageEntity.TEXT_LINK}
    return any(entity.type in link_types for entity in entities)


def has_external_reply(message: Message) -> bool:
    """
    Check if a message has an external reply (quote from another chat).

    External replies occur when a user quotes/replies to a message from
    another chat or channel into the current chat.

    Args:
        message: Telegram message to check.

    Returns:
        bool: True if message has an external reply.
    """
    return message.external_reply is not None


def has_story(message: Message) -> bool:
    """
    Check if a message contains a forwarded story.

    Stories can be shared/forwarded into chats and may be used as a spam vector.

    Args:
        message: Telegram message to check.

    Returns:
        bool: True if message contains a story.
    """
    return message.story is not None


def extract_urls(message: Message) -> list[str]:
    """
    Extract all URLs from a message.

    Args:
        message: Telegram message to check.

    Returns:
        list[str]: List of URLs found in the message.
    """
    urls = []
    entities = list(message.entities or []) + list(message.caption_entities or [])
    text = message.text or message.caption or ""

    for entity in entities:
        if entity.type == MessageEntity.URL:
            urls.append(text[entity.offset : entity.offset + entity.length])
        elif entity.type == MessageEntity.TEXT_LINK and entity.url:
            urls.append(entity.url)

    return urls


def is_url_whitelisted(url: str) -> bool:
    """
    Check if a URL's domain matches any whitelisted domain.

    Uses suffix-based set lookups for O(hostname labels) performance.
    Checks if the URL's hostname exactly matches or is a subdomain of
    a whitelisted domain.

    Args:
        url: URL to check.

    Returns:
        bool: True if URL's domain is whitelisted.
    """
    try:
        # Add scheme if missing for proper parsing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        parsed = urlparse(url)
        hostname = parsed.netloc.lower()

        # Remove port if present
        if ':' in hostname:
            hostname = hostname.rsplit(':', 1)[0]

        # Check suffixes of the hostname against the set
        # e.g., "sub.example.github.com" checks:
        # "sub.example.github.com", "example.github.com", "github.com", "com"
        while hostname:
            if hostname in WHITELISTED_URL_DOMAINS:
                return True
            dot_idx = hostname.find('.')
            if dot_idx == -1:
                return False
            hostname = hostname[dot_idx + 1:]

        return False
    except Exception:
        return False


def has_non_whitelisted_link(message: Message) -> bool:
    """
    Check if a message contains non-whitelisted URLs.

    Args:
        message: Telegram message to check.

    Returns:
        bool: True if message contains non-whitelisted links.
    """
    urls = extract_urls(message)
    if not urls:
        return False

    for url in urls:
        if not is_url_whitelisted(url):
            return True

    return False


async def handle_new_user_spam(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle potential spam from users on probation.

    This handler:
    1. Checks if the user is on probation (within time window)
    2. Detects forwarded messages or links
    3. Deletes violating messages
    4. Sends warning to warning topic on first violation
    5. Restricts user after exceeding violation threshold

    Args:
        update: Telegram update containing the message.
        context: Bot context with helper methods.
    """
    if not update.message or not update.message.from_user:
        return

    settings = get_settings()
    chat = update.effective_chat
    user = update.message.from_user

    # Only process messages from the configured group
    if not chat or chat.id != settings.group_id:
        return

    # Ignore bots
    if user.is_bot:
        return

    db = get_database()
    record = db.get_new_user_probation(user.id, settings.group_id)

    # User not on probation
    if not record:
        return

    # Check if probation has expired
    # Note: SQLite returns naive datetimes, so we need to make joined_at timezone-aware
    joined_at = record.joined_at
    if joined_at.tzinfo is None:
        joined_at = joined_at.replace(tzinfo=UTC)

    now = datetime.now(UTC)
    probation_end = joined_at + settings.probation_timedelta
    if now >= probation_end:
        db.clear_new_user_probation(user.id, settings.group_id)
        logger.info(f"Probation expired for user_id={user.id}, cleared record")
        return

    msg = update.message
    user_mention = get_user_mention(user)

    # Check for violations (forwarded message or non-whitelisted link or external reply)
    if not (is_forwarded(msg) or has_non_whitelisted_link(msg) or has_external_reply(msg) or has_story(msg)):
        return  # Not a violation

    logger.info(
        f"Probation violation detected: user_id={user.id}, "
        f"forwarded={is_forwarded(msg)}, has_non_whitelisted_link={has_non_whitelisted_link(msg)}, "
        f"external_reply={has_external_reply(msg)}, has_story={has_story(msg)}"
    )

    # 1. Delete the violating message
    try:
        await msg.delete()
        logger.info(f"Deleted probation violation message from user_id={user.id}")
    except Exception:
        logger.error(
            f"Failed to delete violation message: user_id={user.id}",
            exc_info=True,
        )

    # 2. Increment violation count
    record = db.increment_new_user_violation(user.id, settings.group_id)

    # 3. First violation: send warning to warning topic
    if record.violation_count == 1:
        probation_display = format_hours_display(settings.new_user_probation_hours)
        warning_text = NEW_USER_SPAM_WARNING.format(
            user_mention=user_mention,
            probation_display=probation_display,
            rules_link=settings.rules_link,
        )
        try:
            await context.bot.send_message(
                chat_id=settings.group_id,
                message_thread_id=settings.warning_topic_id,
                text=warning_text,
                parse_mode="Markdown",
            )
            logger.info(f"Sent probation warning for user_id={user.id}")
        except Exception:
            logger.error(
                f"Failed to send probation warning: user_id={user.id}",
                exc_info=True,
            )

    # 4. Threshold reached: restrict user and notify
    if record.violation_count == settings.new_user_violation_threshold:
        try:
            await context.bot.restrict_chat_member(
                chat_id=settings.group_id,
                user_id=user.id,
                permissions=RESTRICTED_PERMISSIONS,
            )
            logger.info(
                f"Restricted user_id={user.id} after {record.violation_count} "
                f"probation violations"
            )

            # Send restriction notification to warning topic
            restriction_text = NEW_USER_SPAM_RESTRICTION.format(
                user_mention=user_mention,
                violation_count=record.violation_count,
                rules_link=settings.rules_link,
            )
            await context.bot.send_message(
                chat_id=settings.group_id,
                message_thread_id=settings.warning_topic_id,
                text=restriction_text,
                parse_mode="Markdown",
            )
            logger.info(f"Sent restriction notification for user_id={user.id}")
        except Exception:
            logger.error(
                f"Failed to restrict user: user_id={user.id}",
                exc_info=True,
            )
