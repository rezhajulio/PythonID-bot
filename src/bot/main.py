"""
Main entry point for the PythonID bot.

This module initializes the bot application, registers all message handlers,
and starts the polling loop. Handler registration order matters:
1. Topic guard (group -1): Runs first to delete unauthorized messages
2. DM handler: Processes private messages for unrestriction flow
3. Message handler: Monitors group messages for profile compliance
"""

import logging

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from bot.config import get_settings
from bot.database.service import init_database
from bot.handlers import captcha
from bot.handlers.dm import handle_dm
from bot.handlers.message import handle_message
from bot.handlers.topic_guard import guard_warning_topic
from bot.handlers.verify import handle_verify_command, handle_unverify_command
from bot.services.scheduler import auto_restrict_expired_warnings
from bot.services.telegram_utils import fetch_group_admin_ids

# Configure logging format for the application
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
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
    settings = get_settings()
    try:
        admin_ids = await fetch_group_admin_ids(application.bot, settings.group_id)  # type: ignore[arg-type]
        application.bot_data["admin_ids"] = admin_ids  # type: ignore[index]
        logger.info(f"Fetched {len(admin_ids)} admin(s) from group {settings.group_id}")
    except Exception as e:
        logger.error(f"Failed to fetch admin IDs: {e}")
        application.bot_data["admin_ids"] = []  # type: ignore[index]

    # Recover pending captcha verifications
    if settings.captcha_enabled:
        from bot.services.captcha_recovery import recover_pending_captchas
        await recover_pending_captchas(application)


def main() -> None:
    """
    Initialize and run the bot.

    This function:
    1. Loads configuration from environment
    2. Initializes the SQLite database
    3. Registers message handlers in priority order
    4. Starts JobQueue for periodic tasks
    5. Starts the bot polling loop
    """
    settings = get_settings()

    # Initialize database (creates tables if they don't exist)
    init_database(settings.database_path)

    # Build the bot application with the token
    application = Application.builder().token(settings.telegram_bot_token).build()

    # Set post_init callback to fetch admin IDs on startup
    application.post_init = post_init

    # Handler 1: Topic guard - runs first (group -1) to delete unauthorized
    # messages in the warning topic before other handlers process them
    application.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
            guard_warning_topic,
        ),
        group=-1,
    )

    # Handler 2: /verify command - allows admins to whitelist users in DM
    application.add_handler(
        CommandHandler("verify", handle_verify_command)
    )

    # Handler 3: /unverify command - allows admins to remove users from whitelist in DM
    application.add_handler(
        CommandHandler("unverify", handle_unverify_command)
    )

    # Handler 4: Captcha handlers - new member verification
    for handler in captcha.get_handlers():
        application.add_handler(handler)

    # Handler 5: DM handler - processes private messages (including /start)
    # for the unrestriction flow. Must be registered before group handler
    # to prevent group handler from catching private messages first.
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT,
            handle_dm,
        )
    )

    # Handler 6: Group message handler - monitors messages in the configured
    # group and warns/restricts users with incomplete profiles
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    # Register auto-restriction job to run every 5 minutes
    if application.job_queue:
        application.job_queue.run_repeating(
            auto_restrict_expired_warnings,
            interval=300,
            first=300,
            name="auto_restrict_job"
        )

    logger.info(f"Bot started. Monitoring group {settings.group_id}")
    logger.info("JobQueue started with auto-restriction job (every 5 minutes)")
    
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
