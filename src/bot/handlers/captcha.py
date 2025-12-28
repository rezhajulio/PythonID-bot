"""
Captcha verification handler for the PythonID bot.

This module handles captcha verification for new group members. When a user
joins the group, they are restricted and presented with a captcha button.
If they don't verify within the timeout period, they remain restricted.
"""

import logging

from sqlalchemy.exc import IntegrityError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, User
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    CallbackQueryHandler,
    ChatMemberHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.config import Settings, get_settings
from bot.constants import (
    CAPTCHA_FAILED_VERIFICATION_MESSAGE,
    CAPTCHA_VERIFIED_MESSAGE,
    CAPTCHA_WELCOME_MESSAGE,
    CAPTCHA_WRONG_USER_MESSAGE,
    RESTRICTED_PERMISSIONS,
)
from bot.database.service import get_database
from bot.services.telegram_utils import get_user_mention, unrestrict_user

logger = logging.getLogger(__name__)


def get_captcha_job_name(group_id: int, user_id: int) -> str:
    """
    Generate consistent job name for captcha timeout.

    Args:
        group_id: Telegram group ID.
        user_id: Telegram user ID.

    Returns:
        str: Standardized job name for captcha timeout.
    """
    return f"captcha_timeout_{group_id}_{user_id}"


async def _initiate_captcha_challenge(
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
    chat_id: int,
    settings: Settings,
) -> None:
    """
    Initiate captcha challenge for a new member.

    Sends captcha message with keyboard, stores in database, and schedules timeout job.

    Args:
        context: Bot context with helper methods and job queue.
        user: The user to challenge.
        chat_id: The group chat ID.
        settings: Bot settings.
    """
    user_id = user.id
    user_mention = get_user_mention(user)

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=RESTRICTED_PERMISSIONS,
        )
        logger.info(f"Restricted new member {user_id} ({user.full_name}) for captcha")
    except Exception as e:
        logger.error(f"Failed to restrict new member {user_id}: {e}")
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "✅ Saya bukan robot",
            callback_data=f"captcha_verify_{user_id}",
        )]
    ])

    welcome_message = CAPTCHA_WELCOME_MESSAGE.format(
        user_mention=user_mention,
        timeout=settings.captcha_timeout_seconds,
    )

    sent_message = await context.bot.send_message(
        chat_id=chat_id,
        message_thread_id=settings.warning_topic_id,
        text=welcome_message,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )

    db = get_database()
    try:
        db.add_pending_captcha(
            user_id=user_id,
            group_id=settings.group_id,
            chat_id=sent_message.chat_id,
            message_id=sent_message.message_id,
            user_full_name=user.full_name,
        )
    except IntegrityError:
        logger.info(f"Captcha already exists for user {user_id} (race condition handled)")
        return

    job_name = get_captcha_job_name(settings.group_id, user_id)
    context.job_queue.run_once(
        captcha_timeout_callback,
        when=settings.captcha_timeout_seconds,
        name=job_name,
        data={
            "user_id": user_id,
            "group_id": settings.group_id,
            "chat_id": sent_message.chat_id,
            "message_id": sent_message.message_id,
            "user_full_name": user.full_name,
        },
    )

    logger.info(
        f"Sent captcha challenge to user {user_id} ({user.full_name}), "
        f"timeout in {settings.captcha_timeout_seconds}s"
    )


async def new_member_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle new chat member events.

    When a new user joins the group, restrict their permissions and send
    a captcha challenge message with an inline button. Schedules a timeout
    job to ban the user if they don't verify in time.

    Args:
        update: Telegram update containing the new member info.
        context: Bot context with helper methods and job queue.
    """
    if not update.message or not update.message.new_chat_members:
        logger.info("No message or no new chat members, skipping")
        return

    settings = get_settings()

    if not settings.captcha_enabled:
        logger.info("Captcha is disabled, skipping")
        return

    if update.effective_chat and update.effective_chat.id != settings.group_id:
        logger.info(f"Message from wrong chat {update.effective_chat.id}, expected {settings.group_id}, skipping")
        return
    
    logger.info(f"Processing new members: {len(update.message.new_chat_members)} member(s)")

    for new_member in update.message.new_chat_members:
        if new_member.is_bot:
            continue

        user_id = new_member.id

        db = get_database()
        if db.get_pending_captcha(user_id, settings.group_id):
            logger.info(f"Captcha already pending for user {user_id}, skipping duplicate (new_member_handler)")
            continue

        await _initiate_captcha_challenge(context, new_member, settings.group_id, settings)


async def chat_member_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle chat member updates to detect new members.

    This handler uses ChatMemberUpdated events to detect when users join,
    which works even when "Hide Join Messages" is enabled in the group.
    When a new user joins, restrict their permissions and send a captcha challenge.

    Args:
        update: Telegram update containing chat member changes.
        context: Bot context with helper methods and job queue.
    """
    if not update.chat_member:
        logger.info("No chat_member in update, skipping")
        return

    settings = get_settings()

    if not settings.captcha_enabled:
        logger.info("Captcha is disabled, skipping")
        return

    if update.effective_chat and update.effective_chat.id != settings.group_id:
        logger.info(f"Update from wrong chat {update.effective_chat.id}, expected {settings.group_id}, skipping")
        return

    old_status = update.chat_member.old_chat_member.status
    new_status = update.chat_member.new_chat_member.status

    # Detect if this is a join event: user was not a member and now is a member
    left_statuses = {ChatMemberStatus.LEFT, ChatMemberStatus.BANNED}
    member_statuses = {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.RESTRICTED,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    }

    if old_status not in left_statuses or new_status not in member_statuses:
        logger.info(f"Not a join event: {old_status} -> {new_status}, skipping")
        return

    new_member = update.chat_member.new_chat_member.user

    if new_member.is_bot:
        logger.info(f"New member {new_member.id} is a bot, skipping captcha")
        return

    logger.info(f"Detected new member via ChatMemberUpdated: {new_member.id} ({new_member.full_name})")

    user_id = new_member.id

    db = get_database()
    if db.get_pending_captcha(user_id, settings.group_id):
        logger.info(f"Captcha already pending for user {user_id}, skipping duplicate (chat_member_handler)")
        return

    await _initiate_captcha_challenge(context, new_member, settings.group_id, settings)


async def captcha_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle captcha verification button press.

    Verifies that the user clicking the button is the same user who needs
    to verify. If valid, removes restrictions and cleans up.

    Args:
        update: Telegram update containing the callback query.
        context: Bot context with helper methods.
    """
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()

    callback_user_id = query.from_user.id
    target_user_id = int(query.data.split("_")[-1])

    if callback_user_id != target_user_id:
        await query.answer(CAPTCHA_WRONG_USER_MESSAGE, show_alert=True)
        return

    settings = get_settings()

    job_name = get_captcha_job_name(settings.group_id, target_user_id)
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()
        logger.info(f"Cancelled timeout job for user {target_user_id}")

    try:
        await unrestrict_user(context.bot, settings.group_id, target_user_id)
        logger.info(f"Unrestricted verified user {target_user_id}")
    except Exception as e:
        logger.error(f"Failed to unrestrict user {target_user_id}: {e}")
        await query.answer(CAPTCHA_FAILED_VERIFICATION_MESSAGE, show_alert=True)
        return  # Stop execution here so user can retry

    db = get_database()
    db.remove_pending_captcha(target_user_id, settings.group_id)

    user_mention = get_user_mention(query.from_user)

    try:
        await query.edit_message_text(
            text=CAPTCHA_VERIFIED_MESSAGE.format(user_mention=user_mention),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Failed to edit captcha message: {e}")

    logger.info(f"User {target_user_id} ({query.from_user.full_name}) verified successfully")


async def captcha_timeout_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Job callback for captcha timeout.

    Called when the timeout period expires without user verification.
    Keeps the user restricted and provides a DM link to unrestrict.

    Args:
        context: Bot context containing job data.
    """
    from bot.services.captcha_recovery import handle_captcha_expiration

    job = context.job
    if not job or not job.data:
        return

    data = job.data
    user_id = data["user_id"]
    group_id = data["group_id"]
    chat_id = data["chat_id"]
    message_id = data["message_id"]
    user_full_name = data.get("user_full_name", f"User {user_id}")

    await handle_captcha_expiration(
        bot=context.bot,
        user_id=user_id,
        group_id=group_id,
        chat_id=chat_id,
        message_id=message_id,
        user_full_name=user_full_name,
    )


def get_handlers() -> list:
    """
    Return list of handlers to register for captcha verification.

    Returns:
        list: List containing chat member handler, message handler (fallback), 
              and callback query handler.
    """
    return [
        # Primary handler: ChatMemberUpdated - works even with hidden join messages
        ChatMemberHandler(
            chat_member_handler,
            chat_member_types=ChatMemberHandler.CHAT_MEMBER,
        ),
        # Fallback handler: StatusUpdate - for groups with visible join messages
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            new_member_handler,
        ),
        CallbackQueryHandler(
            captcha_callback_handler,
            pattern=r"^captcha_verify_\d+$",
        ),
    ]
