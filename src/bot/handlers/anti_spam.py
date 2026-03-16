"""
Anti-spam handlers for group content moderation.

This module enforces anti-spam rules including:
- Contact card spam detection (all members)
- Inline keyboard URL spam detection (all members)
- Probation enforcement for new users (forwards, links, external replies, stories, media)
"""

import logging
from datetime import UTC, datetime
from urllib.parse import urlparse

from telegram import Message, MessageEntity, Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from bot.constants import (
    CONTACT_SPAM_NOTIFICATION,
    CONTACT_SPAM_NOTIFICATION_NO_RESTRICT,
    INLINE_KEYBOARD_SPAM_NOTIFICATION,
    INLINE_KEYBOARD_SPAM_NOTIFICATION_NO_RESTRICT,
    NEW_USER_SPAM_RESTRICTION,
    NEW_USER_SPAM_WARNING,
    RESTRICTED_PERMISSIONS,
    WHITELISTED_URL_DOMAINS,
    WHITELISTED_TELEGRAM_PATHS,
    format_hours_display,
)
from bot.database.service import get_database
from bot.group_config import get_group_config_for_update
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


def has_media(message: Message) -> bool:
    """
    Check if a message contains media attachments.

    Media elements (photos, videos, animations, audio, voice, and video
    notes) are often used in spam or can be disruptive when sent by brand
    new users before they have passed their probation period.

    Args:
        message: Telegram message to check.

    Returns:
        bool: True if message contains a photo, video, animation, audio,
              voice, or video note.
    """
    return any([
        message.photo,
        message.video,
        message.animation,
        message.audio,
        message.voice,
        message.video_note,
    ])


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

        # Specific logic for Telegram links
        # Check against WHITELISTED_TELEGRAM_PATHS instead of WHITELISTED_URL_DOMAINS
        if hostname in {"t.me", "telegram.me"}:
            path = parsed.path
            if not path or path == "/":
                return False

            # Extract the first segment of the path (the username/channel name)
            # e.g., "/PythonID/123" -> "pythonid"
            parts = path.strip("/").split("/")
            if not parts:
                return False

            first_segment = parts[0].lower()
            return first_segment in WHITELISTED_TELEGRAM_PATHS

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


def has_non_whitelisted_inline_keyboard_urls(message: Message) -> bool:
    """
    Check if a message contains inline keyboard buttons with non-whitelisted URLs.

    Regular Telegram users cannot create inline keyboards from the client.
    Messages with inline keyboard URL buttons pointing to non-whitelisted
    domains are considered spam. Checks url, login_url, and web_app button types.

    Args:
        message: Telegram message to check.

    Returns:
        bool: True if any inline keyboard button has a non-whitelisted URL.
    """
    rm = getattr(message, "reply_markup", None)
    keyboard = getattr(rm, "inline_keyboard", None)
    if not keyboard:
        return False

    for row in keyboard:
        if not row:
            continue
        for button in row:
            if not button:
                continue

            candidates: list[str] = []
            if getattr(button, "url", None):
                candidates.append(button.url)

            login_url = getattr(button, "login_url", None)
            if getattr(login_url, "url", None):
                candidates.append(login_url.url)

            web_app = getattr(button, "web_app", None)
            if getattr(web_app, "url", None):
                candidates.append(web_app.url)

            for u in candidates:
                if not is_url_whitelisted(u):
                    return True

    return False


def has_contact(message: Message) -> bool:
    """
    Check if a message contains a contact card.

    Args:
        message: Telegram message to check.

    Returns:
        bool: True if message contains a contact.
    """
    return message.contact is not None


async def handle_contact_spam(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle contact card sharing in monitored groups.

    Blocks ALL non-admin members from sending contact cards.
    Deletes the message and sends a notification to the warning topic.

    Args:
        update: Telegram update containing the message.
        context: Bot context with helper methods.
    """
    if not update.message or not update.message.from_user:
        return

    group_config = get_group_config_for_update(update)
    if group_config is None:
        return

    user = update.message.from_user
    if user.is_bot:
        return

    admin_ids = context.bot_data.get("group_admin_ids", {}).get(group_config.group_id, [])
    if user.id in admin_ids:
        return

    msg = update.message
    if not has_contact(msg):
        return

    user_mention = get_user_mention(user)
    logger.info(
        f"Contact spam detected: user_id={user.id}, "
        f"group_id={group_config.group_id}"
    )

    try:
        await msg.delete()
        logger.info(f"Deleted contact spam from user_id={user.id}")
    except Exception:
        logger.error(
            f"Failed to delete contact spam: user_id={user.id}",
            exc_info=True,
        )

    restricted = False
    if group_config.contact_spam_restrict:
        try:
            await context.bot.restrict_chat_member(
                chat_id=group_config.group_id,
                user_id=user.id,
                permissions=RESTRICTED_PERMISSIONS,
            )
            restricted = True
            logger.info(f"Restricted user_id={user.id} for contact spam")
        except Exception:
            logger.error(
                f"Failed to restrict user for contact spam: user_id={user.id}",
                exc_info=True,
            )

    try:
        template = (
            CONTACT_SPAM_NOTIFICATION if restricted
            else CONTACT_SPAM_NOTIFICATION_NO_RESTRICT
        )
        notification_text = template.format(
            user_mention=user_mention,
            rules_link=group_config.rules_link,
        )
        await context.bot.send_message(
            chat_id=group_config.group_id,
            message_thread_id=group_config.warning_topic_id,
            text=notification_text,
            parse_mode="Markdown",
        )
        logger.info(f"Sent contact spam notification for user_id={user.id}")
    except Exception:
        logger.error(
            f"Failed to send contact spam notification: user_id={user.id}",
            exc_info=True,
        )

    raise ApplicationHandlerStop


async def handle_inline_keyboard_spam(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle spam messages containing inline keyboard buttons with non-whitelisted URLs.

    Regular users cannot create inline keyboards from the Telegram client.
    Any group message with inline keyboard URL buttons pointing to
    non-whitelisted domains is treated as spam.

    Args:
        update: Telegram update containing the message.
        context: Bot context with helper methods.
    """
    if not update.message or not update.message.from_user:
        return

    group_config = get_group_config_for_update(update)
    if group_config is None:
        return

    user = update.message.from_user
    if user.is_bot:
        return

    admin_ids = context.bot_data.get("group_admin_ids", {}).get(group_config.group_id, [])
    if user.id in admin_ids:
        return

    msg = update.message
    if not has_non_whitelisted_inline_keyboard_urls(msg):
        return

    user_mention = get_user_mention(user)
    logger.info(
        f"Inline keyboard spam detected: user_id={user.id}, "
        f"group_id={group_config.group_id}"
    )

    try:
        await msg.delete()
        logger.info(f"Deleted inline keyboard spam from user_id={user.id}")
    except Exception:
        logger.error(
            f"Failed to delete inline keyboard spam: user_id={user.id}",
            exc_info=True,
        )

    restricted = False
    try:
        await context.bot.restrict_chat_member(
            chat_id=group_config.group_id,
            user_id=user.id,
            permissions=RESTRICTED_PERMISSIONS,
        )
        restricted = True
        logger.info(f"Restricted user_id={user.id} for inline keyboard spam")
    except Exception:
        logger.error(
            f"Failed to restrict user for inline keyboard spam: user_id={user.id}",
            exc_info=True,
        )

    try:
        template = (
            INLINE_KEYBOARD_SPAM_NOTIFICATION if restricted
            else INLINE_KEYBOARD_SPAM_NOTIFICATION_NO_RESTRICT
        )
        notification_text = template.format(
            user_mention=user_mention,
            rules_link=group_config.rules_link,
        )
        await context.bot.send_message(
            chat_id=group_config.group_id,
            message_thread_id=group_config.warning_topic_id,
            text=notification_text,
            parse_mode="Markdown",
        )
        logger.info(f"Sent inline keyboard spam notification for user_id={user.id}")
    except Exception:
        logger.error(
            f"Failed to send inline keyboard spam notification: user_id={user.id}",
            exc_info=True,
        )

    raise ApplicationHandlerStop


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

    group_config = get_group_config_for_update(update)
    user = update.message.from_user

    # Only process messages from monitored groups
    if group_config is None:
        return

    # Ignore bots
    if user.is_bot:
        return

    db = get_database()
    record = db.get_new_user_probation(user.id, group_config.group_id)

    # User not on probation
    if not record:
        return

    # Check if probation has expired
    # Note: SQLite returns naive datetimes, so we need to make joined_at timezone-aware
    joined_at = record.joined_at
    if joined_at.tzinfo is None:
        joined_at = joined_at.replace(tzinfo=UTC)

    now = datetime.now(UTC)
    probation_end = joined_at + group_config.probation_timedelta
    if now >= probation_end:
        db.clear_new_user_probation(user.id, group_config.group_id)
        logger.info(f"Probation expired for user_id={user.id}, cleared record")
        return

    msg = update.message
    user_mention = get_user_mention(user)

    # Check for violations (forwarded message or non-whitelisted link or external reply or media)
    if not (
        is_forwarded(msg)
        or has_non_whitelisted_link(msg)
        or has_external_reply(msg)
        or has_story(msg)
        or has_non_whitelisted_inline_keyboard_urls(msg)
        or has_media(msg)
    ):
        return  # Not a violation

    logger.info(
        f"Probation violation detected: user_id={user.id}, "
        f"forwarded={is_forwarded(msg)}, has_non_whitelisted_link={has_non_whitelisted_link(msg)}, "
        f"external_reply={has_external_reply(msg)}, has_story={has_story(msg)}, "
        f"inline_keyboard_spam={has_non_whitelisted_inline_keyboard_urls(msg)}, "
        f"has_media={has_media(msg)}"
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
    record = db.increment_new_user_violation(user.id, group_config.group_id)

    # 3. First violation: send warning to warning topic
    if record.violation_count == 1:
        probation_display = format_hours_display(group_config.new_user_probation_hours)
        warning_text = NEW_USER_SPAM_WARNING.format(
            user_mention=user_mention,
            probation_display=probation_display,
            rules_link=group_config.rules_link,
        )
        try:
            await context.bot.send_message(
                chat_id=group_config.group_id,
                message_thread_id=group_config.warning_topic_id,
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
    if record.violation_count >= group_config.new_user_violation_threshold:
        try:
            await context.bot.restrict_chat_member(
                chat_id=group_config.group_id,
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
                rules_link=group_config.rules_link,
            )
            await context.bot.send_message(
                chat_id=group_config.group_id,
                message_thread_id=group_config.warning_topic_id,
                text=restriction_text,
                parse_mode="Markdown",
            )
            logger.info(f"Sent restriction notification for user_id={user.id}")
        except Exception:
            logger.error(
                f"Failed to restrict user: user_id={user.id}",
                exc_info=True,
            )

    raise ApplicationHandlerStop
