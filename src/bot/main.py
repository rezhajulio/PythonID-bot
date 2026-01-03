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
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from bot.config import get_settings
from bot.database.service import init_database
from bot.handlers import captcha
from bot.handlers.anti_spam import handle_new_user_spam
from bot.handlers.dm import handle_dm
from bot.handlers.message import handle_message
from bot.handlers.topic_guard import guard_warning_topic
from bot.handlers.verify import (
    handle_forwarded_message,
    handle_unverify_callback,
    handle_unverify_command,
    handle_verify_callback,
    handle_verify_command,
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


async def post_init(application: Application) -> None:  # type: ignore[type-arg]
    """
    Post-initialization callback to fetch and cache group admin IDs.

    This runs once after the bot starts and before polling begins.
    Fetches admin list from the monitored group and stores it in bot_data.
    Also recovers any pending captcha verifications from database.

    Args:
        application: The Application instance.
    """
    logger.info("Starting post_init: fetching admin IDs and recovering captcha state")
    settings = get_settings()
    
    logger.info(f"Fetching admin IDs for group {settings.group_id}")
    try:
        admin_ids = await fetch_group_admin_ids(application.bot, settings.group_id)  # type: ignore[arg-type]
        application.bot_data["admin_ids"] = admin_ids  # type: ignore[index]
        logger.info(f"Fetched {len(admin_ids)} admin(s) from group {settings.group_id}")
    except Exception as e:
        logger.error(f"Failed to fetch admin IDs: {e}")
        application.bot_data["admin_ids"] = []  # type: ignore[index]

    # Recover pending captcha verifications
    if settings.captcha_enabled:
        logger.info("Recovering pending captcha verifications from database")
        from bot.services.captcha_recovery import recover_pending_captchas
        await recover_pending_captchas(application)


def main() -> None:
    """
    Initialize and run the bot.

    This function:
    1. Configures logging with Logfire integration
    2. Loads configuration from environment
    3. Initializes the SQLite database
    4. Registers message handlers in priority order
    5. Starts JobQueue for periodic tasks
    6. Starts the bot polling loop
    """
    # Configure logging first
    configure_logging()
    
    settings = get_settings()
    logger.info(f"Starting PythonID bot (environment: {settings.logfire_environment}, group_id: {settings.group_id})")

    # Initialize database (creates tables if they don't exist)
    init_database(settings.database_path)
    logger.info(f"Database initialized at {settings.database_path}")

    # Build the bot application with the token
    application = Application.builder().token(settings.telegram_bot_token).build()
    logger.info("Application built successfully")

    # Set post_init callback to fetch admin IDs on startup
    application.post_init = post_init

    # Handler 1: Topic guard - runs first (group -1) to delete unauthorized
    # messages in the warning topic before other handlers process them
    application.add_handler(
        MessageHandler(
            filters.ALL,
            guard_warning_topic,
        ),
        group=-1,
    )
    logger.info("Registered handler: topic_guard (group=-1)")

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

    # Handler 4: Forwarded message handler - allows admins to verify/unverify via buttons
    application.add_handler(
        MessageHandler(
            filters.FORWARDED & filters.ChatType.PRIVATE,
            handle_forwarded_message
        )
    )
    logger.info("Registered handler: forwarded_message (group=0)")

    # Handler 5: Callback handlers for verify/unverify buttons
    application.add_handler(
        CallbackQueryHandler(handle_verify_callback, pattern=r"^verify:\d+$")
    )
    logger.info("Registered handler: verify_callback (group=0)")
    application.add_handler(
        CallbackQueryHandler(handle_unverify_callback, pattern=r"^unverify:\d+$")
    )
    logger.info("Registered handler: unverify_callback (group=0)")

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

    # Handler 8: New-user anti-spam handler - checks for forwards/links from users on probation
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS,
            handle_new_user_spam,
        )
    )
    logger.info("Registered handler: anti_spam_handler (group=0)")

    # Handler 9: Group message handler - monitors messages in the configured
    # group and warns/restricts users with incomplete profiles
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & ~filters.COMMAND,
            handle_message,
        ),
        group=1,
    )
    logger.info("Registered handler: message_handler (group=1)")

    # Register auto-restriction job to run every 5 minutes
    if application.job_queue:
        application.job_queue.run_repeating(
            auto_restrict_expired_warnings,
            interval=300,
            first=300,
            name="auto_restrict_job"
        )
        logger.info("JobQueue registered: auto_restrict_job (every 5 minutes, first run in 5 minutes)")

    logger.info(f"Starting bot polling for group {settings.group_id}")
    logger.info("All handlers registered successfully")
    
    application.run_polling(allowed_updates=["message", "callback_query", "chat_member"])


if __name__ == "__main__":
    main()
