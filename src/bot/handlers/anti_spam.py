"""
Anti-spam handlers for group content moderation.

This module enforces anti-spam rules including:
- Contact card spam detection (all members)
- Inline keyboard URL spam detection (all members)
- Probation enforcement for new users (forwards, links, external replies, stories, media)
"""

import logging
from datetime import UTC, datetime

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
    format_hours_display,
)
from bot.database.service import get_database
from bot.group_config import get_group_config_for_update
from bot.services.telegram_utils import get_user_mention, is_user_admin_or_trusted, is_url_whitelisted

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


async def _handle_group_spam(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    detector,
    label: str,
    should_restrict,
    template_restricted: str,
    template_no_restrict: str,
) -> None:
    """
    Shared helper for handling group spam detection and enforcement.

    Implements the common skeleton: guard clauses → detector check → delete
    message → conditionally restrict → send notification → raise ApplicationHandlerStop.

    Args:
        update: Telegram update containing the message.
        context: Bot context with helper methods.
        detector: Callable that takes a Message and returns bool if spam detected.
        label: Description for logging (e.g. "contact spam").
        should_restrict: Callable taking group_config and returning bool.
        template_restricted: Notification template when user is restricted.
        template_no_restrict: Notification template when user is not restricted.
    """
    if not update.message or not update.message.from_user:
        return

    group_config = get_group_config_for_update(update)
    if group_config is None:
        return

    user = update.message.from_user
    if user.is_bot:
        return

    if is_user_admin_or_trusted(context, group_config.group_id, user.id):
        return

    msg = update.message
    if not detector(msg):
        return

    user_mention = get_user_mention(user)
    logger.info(
        f"{label.capitalize()} detected: user_id={user.id}, "
        f"group_id={group_config.group_id}"
    )

    try:
        await msg.delete()
        logger.info(f"Deleted {label} from user_id={user.id}")
    except Exception:
        logger.error(
            f"Failed to delete {label}: user_id={user.id}",
            exc_info=True,
        )

    restricted = False
    if should_restrict(group_config):
        try:
            await context.bot.restrict_chat_member(
                chat_id=group_config.group_id,
                user_id=user.id,
                permissions=RESTRICTED_PERMISSIONS,
            )
            restricted = True
            logger.info(f"Restricted user_id={user.id} for {label}")
        except Exception:
            logger.error(
                f"Failed to restrict user for {label}: user_id={user.id}",
                exc_info=True,
            )

    try:
        template = template_restricted if restricted else template_no_restrict
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
        logger.info(f"Sent {label} notification for user_id={user.id}")
    except Exception:
        logger.error(
            f"Failed to send {label} notification: user_id={user.id}",
            exc_info=True,
        )

    raise ApplicationHandlerStop


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
    await _handle_group_spam(
        update,
        context,
        detector=has_contact,
        label="contact spam",
        should_restrict=lambda cfg: cfg.contact_spam_restrict,
        template_restricted=CONTACT_SPAM_NOTIFICATION,
        template_no_restrict=CONTACT_SPAM_NOTIFICATION_NO_RESTRICT,
    )


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
    await _handle_group_spam(
        update,
        context,
        detector=has_non_whitelisted_inline_keyboard_urls,
        label="inline keyboard spam",
        should_restrict=lambda cfg: True,
        template_restricted=INLINE_KEYBOARD_SPAM_NOTIFICATION,
        template_no_restrict=INLINE_KEYBOARD_SPAM_NOTIFICATION_NO_RESTRICT,
    )


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

    if is_user_admin_or_trusted(context, group_config.group_id, user.id):
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
