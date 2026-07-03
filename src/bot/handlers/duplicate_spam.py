"""
Duplicate message spam detection handler.

This module detects users who spam by repeatedly posting the same or
very similar messages within a short time window. When the threshold
is reached, duplicate messages are deleted and the user is restricted.

Uses an in-memory rolling window per (group_id, user_id) to track
recent messages. No database state is needed — restrictions applied
here are NOT reversible via the DM unrestriction flow (no UserWarning
record is created).
"""

import logging
import re
import unicodedata
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from bot.constants import (
    DUPLICATE_SPAM_RESTRICTION,
    DUPLICATE_SPAM_RESTRICTION_NO_RESTRICT,
    RESTRICTED_PERMISSIONS,
)
from bot.group_config import GroupConfig, get_group_config_for_update
from bot.services.telegram_utils import get_user_mention, is_user_admin_or_trusted

logger = logging.getLogger(__name__)

RECENT_MESSAGES_KEY = "duplicate_spam_recent"


@dataclass
class RecentMessage:
    """A recent message entry for duplicate detection."""

    timestamp: datetime
    normalized_text: str
    message_id: int


def normalize_text(text: str) -> str:
    """
    Normalize text for duplicate comparison.

    Lowercases, strips whitespace, collapses runs of whitespace,
    removes emoji/symbol unicode categories, and strips punctuation.
    """
    text = text.lower()
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    return text


def is_similar(a: str, b: str, threshold: float = 0.95) -> bool:
    """Check if two normalized texts are similar enough to be considered duplicates."""
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= threshold


def _get_recent_messages(
    context: ContextTypes.DEFAULT_TYPE, group_id: int, user_id: int
) -> deque[RecentMessage]:
    """Get or create the recent messages deque for a (group, user) pair."""
    store: dict[tuple[int, int], deque[RecentMessage]] = context.bot_data.setdefault(
        RECENT_MESSAGES_KEY, {}
    )
    key = (group_id, user_id)
    if key not in store:
        store[key] = deque()
    return store[key]


def _prune_old_messages(
    dq: deque[RecentMessage], window_seconds: int, now: datetime
) -> None:
    """Remove messages older than the window from the deque."""
    while dq and (now - dq[0].timestamp).total_seconds() > window_seconds:
        dq.popleft()


async def handle_duplicate_spam(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Detect and handle duplicate message spam.

    Tracks recent messages per (group_id, user_id) in memory. When the
    count of similar messages within the time window reaches the threshold,
    deletes the message and restricts the user.
    """
    if not update.message or not update.message.from_user:
        return

    group_config = get_group_config_for_update(update)
    if group_config is None:
        return

    if not group_config.duplicate_spam_enabled:
        return

    user = update.message.from_user
    if user.is_bot:
        return

    if is_user_admin_or_trusted(context, group_config.group_id, user.id):
        return

    text = update.message.text or update.message.caption
    if not text:
        return

    normalized = normalize_text(text)
    if len(normalized) < group_config.duplicate_spam_min_length:
        return

    now = datetime.now(UTC)
    dq = _get_recent_messages(context, group_config.group_id, user.id)
    _prune_old_messages(dq, group_config.duplicate_spam_window_seconds, now)

    similar_messages = [
        m for m in dq
        if is_similar(normalized, m.normalized_text, group_config.duplicate_spam_similarity)
    ]

    dq.append(
        RecentMessage(
            timestamp=now,
            normalized_text=normalized,
            message_id=update.message.message_id,
        )
    )

    if len(similar_messages) < group_config.duplicate_spam_threshold - 1:
        return

    total_count = len(similar_messages) + 1
    user_mention = get_user_mention(user)

    logger.info(
        f"Duplicate spam detected: user_id={user.id}, "
        f"group_id={group_config.group_id}, count={total_count}"
    )

    message_ids = [m.message_id for m in similar_messages] + [update.message.message_id]
    for message_id in message_ids:
        try:
            await context.bot.delete_message(
                chat_id=group_config.group_id, message_id=message_id
            )
            logger.info(
                f"Deleted duplicate spam message_id={message_id} from user_id={user.id}"
            )
        except Exception:
            logger.error(
                f"Failed to delete duplicate spam message_id={message_id}: user_id={user.id}",
                exc_info=True,
            )

    await _enforce_restriction(context, group_config, user, user_mention, total_count)

    raise ApplicationHandlerStop


async def _enforce_restriction(
    context: ContextTypes.DEFAULT_TYPE,
    group_config: GroupConfig,
    user: object,
    user_mention: str,
    count: int,
) -> None:
    """Restrict the user and send notification to warning topic."""
    restricted = False
    try:
        await context.bot.restrict_chat_member(
            chat_id=group_config.group_id,
            user_id=user.id,
            permissions=RESTRICTED_PERMISSIONS,
        )
        restricted = True
        logger.info(f"Restricted user_id={user.id} for duplicate spam")
    except Exception:
        logger.error(
            f"Failed to restrict user for duplicate spam: user_id={user.id}",
            exc_info=True,
        )

    try:
        template = (
            DUPLICATE_SPAM_RESTRICTION if restricted
            else DUPLICATE_SPAM_RESTRICTION_NO_RESTRICT
        )
        notification_text = template.format(
            user_mention=user_mention,
            count=count,
            rules_link=group_config.rules_link,
        )
        await context.bot.send_message(
            chat_id=group_config.group_id,
            message_thread_id=group_config.warning_topic_id,
            text=notification_text,
            parse_mode="Markdown",
        )
        logger.info(f"Sent duplicate spam notification for user_id={user.id}")
    except Exception:
        logger.error(
            f"Failed to send duplicate spam notification: user_id={user.id}",
            exc_info=True,
        )
