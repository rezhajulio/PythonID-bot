"""
Shared Telegram utility functions.

This module provides common helper functions for working with
Telegram's API across different handlers and services.
"""

import asyncio
import logging
from datetime import timedelta
from urllib.parse import urlparse

from telegram import Bot, Chat, Message, Update, User
from telegram.constants import ChatMemberStatus
from telegram.error import BadRequest, Forbidden, RetryAfter
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown, mention_markdown

from bot.constants import WHITELISTED_TELEGRAM_PATHS, WHITELISTED_URL_DOMAINS
from bot.database.service import get_database

logger = logging.getLogger(__name__)

class TelegramAdminFetchError(Exception):
    """Raised when fetching admin IDs from a Telegram group fails."""
    pass

def get_user_mention(user: User | Chat) -> str:
    """
    Get a formatted mention string for a user or chat.

    Returns `@username` if the user/chat has a username, otherwise returns
    a markdown mention using the full name and ID.

    Args:
        user: Telegram User or Chat object.

    Returns:
        str: Formatted user mention (either @username or markdown mention).
    """
    return get_user_mention_by_id(user.id, user.full_name, user.username)

def get_user_mention_by_id(
    user_id: int,
    user_full_name: str,
    username: str | None = None,
) -> str:
    """
    Get a formatted mention for a user by ID and name.

    Used when only user ID and full name are available (not a full User object).

    Args:
        user_id: Telegram user ID.
        user_full_name: User's full name.
        username: Optional username to prefer @username format.

    Returns:
        str: Formatted mention string.
    """
    if username:
        escaped = escape_markdown(username.lstrip("@"), version=1)
        return f"@{escaped}"
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
        ok = await restrict_chat_member_with_retry(
            bot,
            chat_id=group_id,
            user_id=user_id,
            permissions=default_permissions,
        )
        if not ok:
            raise RuntimeError("Final RetryAfter exceeded on restrict_chat_member")
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
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        parsed = urlparse(url)
        hostname = parsed.netloc.lower()

        if ':' in hostname:
            hostname = hostname.rsplit(':', 1)[0]

        if hostname in {"t.me", "telegram.me"}:
            path = parsed.path
            if not path or path == "/":
                return False
            parts = path.strip("/").split("/")
            if not parts:
                return False
            first_segment = parts[0].lower()
            return first_segment in WHITELISTED_TELEGRAM_PATHS

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

def _get_trusted_ids(bot_data: dict) -> set[int]:
    """
    Return the cached set of trusted user IDs from ``bot_data``.

    If the ``"trusted_user_ids"`` key is missing entirely (``None``), perform a
    one-time lazy load via :func:`get_database`. If the database is not yet
    initialised (``RuntimeError``), cache an empty set so the lookup is not
    retried on every call.

    Args:
        bot_data: The application's ``bot_data`` mapping.

    Returns:
        set[int]: The cached trusted user ID set (possibly empty).
    """
    trusted_ids = bot_data.get("trusted_user_ids")
    if trusted_ids is not None:
        return trusted_ids

    try:
        loaded = set(get_database().get_trusted_user_ids())
    except RuntimeError:
        loaded = set()
    bot_data["trusted_user_ids"] = loaded
    return loaded

def is_user_admin_or_trusted(context: object, group_id: int, user_id: int) -> bool:
    """
    Check whether a user is an admin or trusted user for bypass decisions.

    Reads exclusively from in-memory caches (``group_admin_ids`` and
    ``trusted_user_ids`` stored on ``context.bot_data``). The trusted-user
    cache is lazily initialised once if missing; no database call happens on
    the hot path beyond that initial load.

    Args:
        context: Telegram callback context.
        group_id: Telegram group ID.
        user_id: Telegram user ID.

    Returns:
        bool: True if user should bypass spam checks.
    """
    bot_data = getattr(context, "bot_data", {})

    admin_ids = bot_data.get("group_admin_ids", {}).get(group_id, [])
    if user_id in admin_ids:
        return True

    trusted_ids = _get_trusted_ids(bot_data)
    return user_id in trusted_ids

def _retry_after_seconds(e: RetryAfter) -> float:
    """Extract RetryAfter.retry_after as seconds (handles int and timedelta)."""
    return e.retry_after.total_seconds() if isinstance(e.retry_after, timedelta) else e.retry_after


_MAX_RETRY_SLEEP_SECONDS = 30.0


def _clamped_retry_seconds(e: RetryAfter) -> float:
    """RetryAfter sleep capped at ``_MAX_RETRY_SLEEP_SECONDS`` so one bad
    flood-control response can't stall a per-group loop for a minute-plus."""
    return min(_retry_after_seconds(e) + 1, _MAX_RETRY_SLEEP_SECONDS)


async def send_message_with_retry(bot: Bot, *, chat_id: int, **kwargs: object) -> bool:
    """
    Send a message with one retry on RetryAfter (HTTP 429 / flood control).

    Catches ``telegram.error.RetryAfter``, sleeps ``e.retry_after + 1`` seconds,
    and retries exactly once. On a second RetryAfter it returns ``False``
    (the error is logged). All other exceptions re-raise so the caller's
    existing ``except Exception`` still catches them.

    Args:
        bot: Telegram Bot instance.
        chat_id: Target chat / group ID.
        **kwargs: Extra keyword arguments forwarded to ``bot.send_message``.

    Returns:
        bool: ``True`` if the message was sent successfully, ``False`` if a
        second consecutive RetryAfter was encountered.
    """
    try:
        await bot.send_message(chat_id=chat_id, **kwargs)
        return True
    except RetryAfter as e:
        wait_seconds = int(_retry_after_seconds(e))
        logger.warning(
            f"RetryAfter on send_message to chat {chat_id}, sleeping {wait_seconds}s before retry"
        )
        await asyncio.sleep(_clamped_retry_seconds(e))
        try:
            await bot.send_message(chat_id=chat_id, **kwargs)
            return True
        except RetryAfter:
            logger.error(
                f"RetryAfter again on send_message to chat {chat_id}, giving up"
            )
            return False


async def restrict_chat_member_with_retry(
    bot: Bot, *, chat_id: int, user_id: int, permissions: object, **kwargs: object
) -> bool:
    """
    Restrict a chat member with one retry on RetryAfter.

    Same retry strategy as :func:`send_message_with_retry` but wraps
    ``bot.restrict_chat_member``. Returns ``True`` on success, ``False`` after a
    second consecutive RetryAfter. Other exceptions re-raise.

    Args:
        bot: Telegram Bot instance.
        chat_id: Group ID.
        user_id: User ID to restrict.
        permissions: ``ChatPermissions`` to apply.
        **kwargs: Extra keyword arguments forwarded to ``bot.restrict_chat_member``.

    Returns:
        bool: ``True`` if restriction applied, ``False`` after second RetryAfter.
    """
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id, user_id=user_id, permissions=permissions, **kwargs
        )
        return True
    except RetryAfter as e:
        wait_seconds = int(_retry_after_seconds(e))
        logger.warning(
            f"RetryAfter on restrict_chat_member to chat {chat_id} (user {user_id}), sleeping {wait_seconds}s"
        )
        await asyncio.sleep(_clamped_retry_seconds(e))
        try:
            await bot.restrict_chat_member(
                chat_id=chat_id, user_id=user_id, permissions=permissions, **kwargs
            )
            return True
        except RetryAfter:
            logger.error(
                f"RetryAfter again on restrict_chat_member to chat {chat_id} (user {user_id}), giving up"
            )
            return False


async def fetch_group_admin_ids(bot: Bot, group_id: int) -> list[int]:
    """
    Fetch all human administrator user IDs from a group.

    Bot accounts are excluded from the returned list so that automated
    admin-bots do not get treated as human admins for authorization
    or bypass decisions.

    Args:
        bot: Telegram bot instance.
        group_id: Telegram group ID.

    Returns:
        list[int]: List of human admin user IDs (creator + administrators).

    Raises:
        TelegramAdminFetchError: If unable to fetch administrators (bot not in group, etc.).
    """
    try:
        admins = await bot.get_chat_administrators(
            group_id,
            api_kwargs={"return_bots": False},
        )
        admin_ids = [admin.user.id for admin in admins if not admin.user.is_bot]
        logger.info(f"Fetched {len(admin_ids)} human admins from group_id={group_id}")
        return admin_ids
    except (BadRequest, Forbidden) as e:
        logger.error(
            f"Failed to fetch admins from group_id={group_id}: {e}",
            exc_info=True,
        )
        raise TelegramAdminFetchError(f"Failed to fetch admins from group {group_id}: {e}") from e

async def require_admin_dm_target(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    usage_message: str,
    command_label: str,
) -> int | None:
    """
    Validate admin DM command prerequisites and parse target user ID.

    Performs four checks in order:
    1. Message and from_user exist
    2. Chat is private
    3. Caller is an admin
    4. Argument is a valid user ID

    Sends appropriate error replies on any failure. Returns the parsed user ID
    on success, or None after sending an error reply.

    Args:
        update: Telegram update.
        context: Bot context.
        usage_message: Full usage message to send on missing args (e.g., "❌ Penggunaan: /verify USER_ID").
        command_label: Command name for logging (e.g., "/verify command").

    Returns:
        int | None: Parsed user ID on success, None if any check failed.
    """
    if not update.message or not update.message.from_user:
        return None

    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_text(
            "❌ Perintah ini hanya bisa digunakan di chat pribadi dengan bot."
        )
        return None

    admin_user_id = update.message.from_user.id
    admin_ids = context.bot_data.get("admin_ids", [])

    if admin_user_id not in admin_ids:
        await update.message.reply_text("❌ Kamu tidak memiliki izin untuk menggunakan perintah ini.")
        logger.warning(
            f"Non-admin user {admin_user_id} ({update.message.from_user.full_name}) "
            f"attempted to use {command_label}"
        )
        return None

    if not context.args or len(context.args) == 0:
        await update.message.reply_text(usage_message)
        return None

    try:
        target_user_id = int(context.args[0])
        return target_user_id
    except ValueError:
        await update.message.reply_text("❌ User ID harus berupa angka.")
        return None
