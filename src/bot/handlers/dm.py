"""
DM (Direct Message) handler for the PythonID bot.

This module handles private messages to the bot, primarily for the
unrestriction flow. When a restricted user DMs the bot:
1. Check if user is in any monitored group
2. Check if user has an active pending captcha (redirect to group)
3. Check if user's profile is complete
4. If profile-restricted by bot and profile complete, unrestrict them
   in the groups where they are restricted

Supports deep-link payloads via /start verify_<group_id> for group-specific
recovery. The DM message uses the target group's rules_link instead of
the global settings fallback.
"""

import logging

from telegram import Update
from telegram.constants import ChatMemberStatus
from telegram.ext import ContextTypes

from bot.constants import (
    CAPTCHA_PENDING_DM_GROUP_LINE,
    CAPTCHA_PENDING_DM_MESSAGE,
    DM_ALREADY_UNRESTRICTED_MESSAGE,
    DM_INCOMPLETE_PROFILE_MESSAGE,
    DM_NOT_IN_GROUP_MESSAGE,
    DM_NO_RESTRICTION_MESSAGE,
    DM_UNRESTRICTION_NOTIFICATION,
    DM_UNRESTRICTION_SUCCESS_MESSAGE,
    MISSING_ITEMS_SEPARATOR,
)
from bot.database.service import get_database
from bot.group_config import get_group_registry
from bot.services.telegram_utils import (
    get_user_mention,
    get_user_status,
    send_message_with_retry,
    unrestrict_user,
)
from bot.services.user_checker import check_user_profile

logger = logging.getLogger(__name__)

_VERIFY_DEEP_LINK_PREFIX = "verify_"


def _parse_deep_link_payload(text: str) -> int | None:
    """Extract a group_id from a /start deep-link payload.

    Supports payloads like ``verify_-1001234567890`` (from
    ``https://t.me/BotUsername?start=verify_-1001234567890``).

    Returns the group_id as int, or None if the payload is not a
    verify deep link.
    """
    if not text:
        return None
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    payload = parts[1].strip()
    if not payload.startswith(_VERIFY_DEEP_LINK_PREFIX):
        return None
    group_id_str = payload[len(_VERIFY_DEEP_LINK_PREFIX):]
    try:
        return int(group_id_str)
    except ValueError:
        return None


async def _unrestrict_in_groups(
    context: ContextTypes.DEFAULT_TYPE,
    user,
    restricted_groups: list,
) -> int:
    """Unrestrict user in all groups where restricted. Returns success count."""
    db = get_database()
    success_count = 0

    for gc, user_status in restricted_groups:
        if user_status != ChatMemberStatus.RESTRICTED:
            db.mark_all_bot_restrictions_unrestricted(user.id, gc.group_id)
            logger.info(
                f"User {user.id} ({user.full_name}) already unrestricted in group {gc.group_id} - clearing record"
            )
            continue

        logger.info(f"Unrestricting user_id={user.id} ({user.full_name}) in group_id={gc.group_id}")
        try:
            await unrestrict_user(context.bot, gc.group_id, user.id)
            db.mark_all_bot_restrictions_unrestricted(user.id, gc.group_id)
            success_count += 1

            user_mention = get_user_mention(user)
            notification_message = DM_UNRESTRICTION_NOTIFICATION.format(
                user_mention=user_mention
            )
            await send_message_with_retry(
                context.bot,
                chat_id=gc.group_id,
                message_thread_id=gc.warning_topic_id,
                text=notification_message,
                parse_mode="Markdown",
            )
            logger.info(
                f"Unrestricted user {user.id} ({user.full_name}) via DM (group_id={gc.group_id})"
            )
        except Exception:
            logger.error(
                f"Failed to unrestrict user {user.id} ({user.full_name}) via DM (group_id={gc.group_id})",
                exc_info=True,
            )

    return success_count


async def handle_dm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle direct messages to the bot for unrestriction flow.

    This handler processes DMs (including /start with deep-link payloads) and:
    1. Checks if user is a member of any monitored group
    2. Checks if user has an active pending captcha (redirect to group)
    3. Checks if user's profile is complete (photo + username)
    4. If user was restricted by the bot and now has complete profile,
       removes the restriction in the groups where restricted

    If a /start deep-link with ``verify_<group_id>`` is provided, the
    handler prioritizes that group for recovery messaging and uses
    that group's rules_link.

    Args:
        update: Telegram update containing the message.
        context: Bot context with helper methods.
    """
    if not update.message or not update.message.from_user:
        logger.info("Skipping DM handler - no message or sender")
        return

    if update.effective_chat and update.effective_chat.type != "private":
        logger.info(f"Skipping non-private chat type: {update.effective_chat.type}")
        return

    user = update.message.from_user
    registry = get_group_registry()
    db = get_database()

    logger.info(f"DM handler called for user_id={user.id} ({user.full_name})")

    # Parse deep-link payload (e.g., /start verify_-1001234567890)
    deep_link_group_id = _parse_deep_link_payload(update.message.text or "")

    # Check user's membership across all monitored groups
    member_groups = []
    for gc in registry.all_groups():
        logger.info(f"Checking user status in group_id={gc.group_id} for user_id={user.id}")
        try:
            user_status = await get_user_status(context.bot, gc.group_id, user.id)
        except Exception:
            logger.warning(
                f"Failed to check user status in group {gc.group_id} for user {user.id}",
                exc_info=True,
            )
            continue
        if user_status is not None and user_status not in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
            member_groups.append((gc, user_status))

    # User not in any monitored group
    if not member_groups:
        await update.message.reply_text(DM_NOT_IN_GROUP_MESSAGE)
        logger.info(f"DM from user {user.id} ({user.full_name}) - not in any monitored group")
        return

    # Check if user has an active pending captcha in any group
    pending_groups = []
    for gc, _ in member_groups:
        pending_captcha = db.get_pending_captcha(user.id, gc.group_id)
        if pending_captcha:
            pending_groups.append(gc.group_id)

    if pending_groups:
        group_lines = "\n".join(
            CAPTCHA_PENDING_DM_GROUP_LINE.format(group_id=gid) for gid in pending_groups
        )
        await update.message.reply_text(
            CAPTCHA_PENDING_DM_MESSAGE.format(group_list=group_lines)
        )
        logger.info(
            f"DM from user {user.id} ({user.full_name}) - has pending captcha in groups: {pending_groups}"
        )
        return

    # Check if user's profile is complete
    logger.info(f"Checking user profile completeness for user_id={user.id} ({user.full_name})")
    result = await check_user_profile(context.bot, user)

    # Profile still incomplete - tell them what's missing
    if not result.is_complete:
        missing = result.get_missing_items()
        missing_text = MISSING_ITEMS_SEPARATOR.join(missing)

        # Use the deep-linked group's rules_link, or fall back to the first
        # member group's rules_link, or the first member group's config
        rules_link_gc = None
        if deep_link_group_id is not None:
            rules_link_gc = registry.get(deep_link_group_id)
        if rules_link_gc is None and member_groups:
            rules_link_gc = member_groups[0][0]
        rules_link = rules_link_gc.rules_link if rules_link_gc else ""

        reply_message = DM_INCOMPLETE_PROFILE_MESSAGE.format(
            missing_text=missing_text,
            rules_link=rules_link,
        )
        await update.message.reply_text(reply_message, parse_mode="Markdown")
        logger.info(
            f"DM from user {user.id} ({user.full_name}) - missing: {missing_text}"
        )
        return

    # Find all groups where user is restricted by bot
    restricted_groups = []
    for gc, user_status in member_groups:
        logger.info(f"Checking bot restriction status for user_id={user.id} in group_id={gc.group_id}")
        if db.is_user_restricted_by_bot(user.id, gc.group_id):
            restricted_groups.append((gc, user_status))

    # User not restricted by bot in any group
    if not restricted_groups:
        await update.message.reply_text(DM_NO_RESTRICTION_MESSAGE)
        logger.info(
            f"DM from user {user.id} ({user.full_name}) - no bot restriction in any group"
        )
        return

    # Unrestrict user from all groups where restricted by bot
    had_any_restricted = any(status == ChatMemberStatus.RESTRICTED for _, status in restricted_groups)
    success_count = await _unrestrict_in_groups(context, user, restricted_groups)

    if success_count > 0:
        await update.message.reply_text(DM_UNRESTRICTION_SUCCESS_MESSAGE)
    elif not had_any_restricted:
        await update.message.reply_text(DM_ALREADY_UNRESTRICTED_MESSAGE)
    else:
        logger.error(f"Failed to unrestrict user {user.id} in any group")
        await update.message.reply_text(
            "❌ Gagal membuka pembatasan. Silakan hubungi admin grup."
        )
