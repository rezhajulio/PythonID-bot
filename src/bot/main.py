"""
Main entry point for the PythonID bot.

This module initializes the bot application, registers all message handlers,
and starts the polling loop. Handler registration order matters:
1. Topic guard (group -1): Runs first to delete unauthorized messages
2. DM handler: Processes private messages for unrestriction flow
3. Message handler: Monitors group messages for profile compliance
"""

import logging

import logfire
from telegram.error import NetworkError, TimedOut
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from bot.config import get_settings
from bot.database.service import get_database, init_database
from bot.group_config import get_group_registry, init_group_registry
from bot.handlers import captcha
from bot.handlers.anti_spam import handle_contact_spam, handle_inline_keyboard_spam, handle_new_user_spam
from bot.handlers.bio_bait import BIO_BAIT_FILTER, handle_bio_bait_spam
from bot.handlers.duplicate_spam import handle_duplicate_spam
from bot.handlers.dm import handle_dm
from bot.handlers.message import handle_message
from bot.handlers.topic_guard import guard_warning_topic
from bot.handlers.verify import (
    handle_unverify_callback,
    handle_unverify_command,
    handle_verify_callback,
    handle_verify_command,
)
from bot.handlers.check import (
    handle_check_command,
    handle_check_forwarded_message,
    handle_warn_callback,
)
from bot.handlers.trust import (
    handle_trust_callback,
    handle_trust_command,
    handle_trusted_list_command,
    handle_untrust_callback,
    handle_untrust_command,
)
from bot.services.scheduler import auto_restrict_expired_warnings
from bot.services.telegram_utils import fetch_group_admin_ids


def configure_logging() -> None:
    """
    Configure logging with Logfire integration.

    Uses minimal instrumentation to conserve Logfire quota:
    - Configurable log level via LOG_LEVEL environment variable
    - Disables database query tracing
    - Disables auto-instrumentation for less critical operations
    - Suppresses verbose HTTP request logs from httpx/httpcore libraries
    - In local dev: console output only (send_to_logfire=False)
    - In production: sends to Logfire only if LOGFIRE_TOKEN is set
    """
    # Configure basic logging FIRST to capture Settings initialization logs
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
        force=True,  # Override any existing config
    )

    # Now load settings (this will trigger model_post_init logging)
    settings = get_settings()

    # Get log level from settings and convert to logging constant
    log_level_str = settings.log_level.upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # Determine if we should send to Logfire
    # Only send if enabled AND token is provided
    send_to_logfire = settings.logfire_enabled and settings.logfire_token is not None

    # Map log level to Logfire console min_log_level
    logfire_min_level = log_level_str.lower()

    # Configure Logfire with minimal instrumentation
    logfire.configure(
        token=settings.logfire_token,
        service_name=settings.logfire_service_name,
        environment=settings.logfire_environment,
        send_to_logfire=send_to_logfire,
        console=logfire.ConsoleOptions(
            colors="auto",
            include_timestamps=True,
            min_log_level=logfire_min_level,
        ),
        # Disable auto-instrumentation to save quota
        inspect_arguments=False,
    )

    # Reconfigure logging with Logfire handler and configured level
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=log_level,
        handlers=[logfire.LogfireLoggingHandler()],
        force=True,  # Override previous config
    )

    # Suppress verbose HTTP logs from httpx/httpcore used by python-telegram-bot
    # These libraries log every HTTP request at INFO level, flooding logs with Telegram API polling requests
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info(f"Logging level set to {log_level_str}")
    if send_to_logfire:
        logger.info(f"Logfire enabled - sending logs to {settings.logfire_environment}")
    else:
        logger.info("Logfire disabled - console output only")


logger = logging.getLogger(__name__)


async def refresh_admin_ids(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Periodically refresh cached admin IDs for all monitored groups.

    Called by JobQueue every 10 minutes to keep admin rosters up to date
    when promotions/demotions happen after startup.
    """
    registry = get_group_registry()
    group_admin_ids: dict[int, list[int]] = {}
    all_admin_ids: set[int] = set()

    for gc in registry.all_groups():
        try:
            ids = await fetch_group_admin_ids(context.bot, gc.group_id)
            group_admin_ids[gc.group_id] = ids
            all_admin_ids.update(ids)
        except Exception as e:
            logger.error(f"Failed to refresh admin IDs for group {gc.group_id}: {e}")
            existing = context.bot_data.get("group_admin_ids", {}).get(gc.group_id, [])
            group_admin_ids[gc.group_id] = existing
            all_admin_ids.update(existing)

    context.bot_data["group_admin_ids"] = group_admin_ids
    context.bot_data["admin_ids"] = list(all_admin_ids)
    logger.info(f"Refreshed admin IDs: {len(all_admin_ids)} unique admin(s) across {len(group_admin_ids)} group(s)")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle errors in the bot.

    Logs the error and continues operation. Network timeouts are logged
    at warning level since they're transient issues.
    """
    error = context.error

    if isinstance(error, TimedOut):
        logger.warning(f"Request timed out: {error}")
        return

    if isinstance(error, NetworkError):
        logger.warning(f"Network error: {error}")
        return

    logger.error("Unhandled exception:", exc_info=context.error)


async def post_init(application: Application) -> None:  # type: ignore[type-arg]
    """
    Post-initialization callback to fetch and cache group admin IDs.

    This runs once after the bot starts and before polling begins.
    Fetches admin list from all monitored groups and stores per-group
    and union admin IDs in bot_data. Also recovers pending captchas.

    Args:
        application: The Application instance.
    """
    logger.info("Starting post_init: fetching admin IDs and recovering captcha state")
    registry = get_group_registry()

    # Fetch admin IDs for all monitored groups
    group_admin_ids: dict[int, list[int]] = {}
    all_admin_ids: set[int] = set()

    for gc in registry.all_groups():
        logger.info(f"Fetching admin IDs for group {gc.group_id}")
        try:
            ids = await fetch_group_admin_ids(application.bot, gc.group_id)  # type: ignore[arg-type]
            group_admin_ids[gc.group_id] = ids
            all_admin_ids.update(ids)
            logger.info(f"Fetched {len(ids)} admin(s) from group {gc.group_id}")
        except Exception as e:
            logger.error(f"Failed to fetch admin IDs for group {gc.group_id}: {e}")
            group_admin_ids[gc.group_id] = []

    application.bot_data["group_admin_ids"] = group_admin_ids  # type: ignore[index]
    application.bot_data["admin_ids"] = list(all_admin_ids)  # type: ignore[index]
    logger.info(f"Total unique admins across all groups: {len(all_admin_ids)}")

    # Preload trusted users cache
    db = get_database()
    trusted_ids = db.get_trusted_user_ids()
    application.bot_data["trusted_user_ids"] = trusted_ids  # type: ignore[index]
    logger.info(f"Loaded {len(trusted_ids)} trusted user(s) into cache")

    # Recover pending captcha verifications for groups with captcha enabled
    has_captcha = any(gc.captcha_enabled for gc in registry.all_groups())
    if has_captcha:
        logger.info("Recovering pending captcha verifications from database")
        from bot.services.captcha_recovery import recover_pending_captchas
        await recover_pending_captchas(application)


def main() -> None:
    """
    Initialize and run the bot.

    This function:
    1. Configures logging with Logfire integration
    2. Loads configuration from environment
    3. Initializes the group registry (from groups.json or .env fallback)
    4. Initializes the SQLite database
    5. Registers message handlers in priority order
    6. Starts JobQueue for periodic tasks
    7. Starts the bot polling loop
    """
    # Configure logging first
    configure_logging()

    settings = get_settings()

    # Initialize group registry
    registry = init_group_registry(settings)
    group_count = len(registry.all_groups())
    logger.info(f"Starting PythonID bot (environment: {settings.logfire_environment}, groups: {group_count})")
    for gc in registry.all_groups():
        logger.info(
            f"  Group {gc.group_id}: warning_topic={gc.warning_topic_id}, "
            f"restrict={gc.restrict_failed_users}, captcha={gc.captcha_enabled}"
        )

    # Initialize database (creates tables if they don't exist)
    init_database(settings.database_path)
    logger.info(f"Database initialized at {settings.database_path}")

    # Build the bot application with the token and post_init callback
    application = Application.builder().token(settings.telegram_bot_token).post_init(post_init).build()
    application.add_error_handler(error_handler)
    logger.info("Application built successfully")

    # Handler 1: Topic guard - runs first (group -1) to delete unauthorized
    # messages in the warning topic before other handlers process them
    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE | filters.UpdateType.EDITED_MESSAGE,
            guard_warning_topic,
        ),
        group=-1,
    )
    logger.info("Registered handler: topic_guard (group=-1, message + edited_message)")

    # Handler 2: /verify command - allows admins to whitelist users in DM
    application.add_handler(
        CommandHandler("verify", handle_verify_command)
    )
    logger.info("Registered handler: verify_command (group=0)")

    # Handler 3: /unverify command - allows admins to remove users from whitelist in DM
    application.add_handler(
        CommandHandler("unverify", handle_unverify_command)
    )
    logger.info("Registered handler: unverify_command (group=0)")

    # Handler: /check command - allows admins to check user profiles in DM
    application.add_handler(
        CommandHandler("check", handle_check_command)
    )
    logger.info("Registered handler: check_command (group=0)")

    # Handler: /trust command - allows admins to trust users for spam bypass in DM
    application.add_handler(
        CommandHandler("trust", handle_trust_command)
    )
    logger.info("Registered handler: trust_command (group=0)")

    # Handler: /untrust command - allows admins to remove users from trusted list in DM
    application.add_handler(
        CommandHandler("untrust", handle_untrust_command)
    )
    logger.info("Registered handler: untrust_command (group=0)")

    # Handler: /trusted command - list all trusted users in DM
    application.add_handler(
        CommandHandler("trusted", handle_trusted_list_command)
    )
    logger.info("Registered handler: trusted_list_command (group=0)")

    # Handler: Forwarded message handler - allows admins to check profiles via forward
    application.add_handler(
        MessageHandler(
            filters.FORWARDED & filters.ChatType.PRIVATE,
            handle_check_forwarded_message
        )
    )
    logger.info("Registered handler: check_forwarded_message (group=0)")

    # Handler 5: Callback handlers for verify/unverify buttons
    application.add_handler(
        CallbackQueryHandler(handle_verify_callback, pattern=r"^verify:\d+$")
    )
    logger.info("Registered handler: verify_callback (group=0)")
    application.add_handler(
        CallbackQueryHandler(handle_unverify_callback, pattern=r"^unverify:\d+$")
    )
    logger.info("Registered handler: unverify_callback (group=0)")
    application.add_handler(
        CallbackQueryHandler(handle_warn_callback, pattern=r"^warn:\d+:")
    )
    logger.info("Registered handler: warn_callback (group=0)")
    application.add_handler(
        CallbackQueryHandler(handle_trust_callback, pattern=r"^trust:\d+$")
    )
    logger.info("Registered handler: trust_callback (group=0)")
    application.add_handler(
        CallbackQueryHandler(handle_untrust_callback, pattern=r"^untrust:\d+$")
    )
    logger.info("Registered handler: untrust_callback (group=0)")

    # Handler 6: Captcha handlers - new member verification
    for handler in captcha.get_handlers():
        application.add_handler(handler)
    logger.info("Registered handler: captcha_handlers (group=0)")

    # Handler 7: DM handler - processes private messages (including /start)
    # for the unrestriction flow. Must be registered before group handler
    # to prevent group handler from catching private messages first.
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT,
            handle_dm,
        )
    )
    logger.info("Registered handler: dm_handler (group=0)")

    # Handler 8: Inline keyboard spam handler - catches messages with
    # non-whitelisted URL buttons in inline keyboards (spam from bots/forwards).
    # Each spam handler runs in its own group so they all independently process
    # every group message. They raise ApplicationHandlerStop to prevent later
    # groups from running when spam IS detected.
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS,
            handle_inline_keyboard_spam,
        ),
        group=1,
    )
    logger.info("Registered handler: inline_keyboard_spam_handler (group=1)")

    # Handler: Bio bait spam handler - catches "cek bio aku" / "lihat byoh" style
    # messages where spammers point users to their profile bio (which contains
    # external promo/scam links).
    application.add_handler(
        MessageHandler(
            BIO_BAIT_FILTER,
            handle_bio_bait_spam,
        ),
        group=2,
    )
    logger.info("Registered handler: bio_bait_spam_handler (group=2)")

    # Handler: Contact spam handler - blocks contact card sharing for all members
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & filters.CONTACT,
            handle_contact_spam,
        ),
        group=3,
    )
    logger.info("Registered handler: contact_spam_handler (group=3)")

    # Handler 9: New-user anti-spam handler - checks for forwards/links from users on probation
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS,
            handle_new_user_spam,
        ),
        group=4,
    )
    logger.info("Registered handler: anti_spam_handler (group=4)")

    # Handler 10: Duplicate message spam handler - detects repeated identical messages
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & ~filters.COMMAND,
            handle_duplicate_spam,
        ),
        group=5,
    )
    logger.info("Registered handler: duplicate_spam_handler (group=5)")

    # Handler 11: Group message handler - monitors messages in monitored
    # groups and warns/restricts users with incomplete profiles
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & ~filters.COMMAND,
            handle_message,
        ),
        group=6,
    )
    logger.info("Registered handler: message_handler (group=6)")

    # Register auto-restriction job to run every 5 minutes
    if application.job_queue:
        application.job_queue.run_repeating(
            auto_restrict_expired_warnings,
            interval=300,
            first=300,
            name="auto_restrict_job"
        )
        logger.info("JobQueue registered: auto_restrict_job (every 5 minutes, first run in 5 minutes)")

        application.job_queue.run_repeating(
            refresh_admin_ids,
            interval=600,
            first=600,
            name="refresh_admin_ids_job"
        )
        logger.info("JobQueue registered: refresh_admin_ids_job (every 10 minutes)")

    logger.info(f"Starting bot polling for {group_count} group(s)")
    logger.info("All handlers registered successfully")

    application.run_polling(allowed_updates=["message", "edited_message", "callback_query", "chat_member"])


if __name__ == "__main__":
    main()
