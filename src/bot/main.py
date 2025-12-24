"""
Main entry point for the PythonID bot.

This module initializes the bot application, registers all message handlers,
and starts the polling loop. Handler registration order matters:
1. Topic guard (group -1): Runs first to delete unauthorized messages
2. DM handler: Processes private messages for unrestriction flow
3. Message handler: Monitors group messages for profile compliance
"""

import logging

from telegram.ext import Application, MessageHandler, filters

from bot.config import get_settings
from bot.database.service import init_database
from bot.handlers.dm import handle_dm
from bot.handlers.message import handle_message
from bot.handlers.topic_guard import guard_warning_topic
from bot.services.scheduler import auto_restrict_expired_warnings

# Configure logging format for the application
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


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

    # Handler 1: Topic guard - runs first (group -1) to delete unauthorized
    # messages in the warning topic before other handlers process them
    application.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
            guard_warning_topic,
        ),
        group=-1,
    )

    # Handler 2: DM handler - processes private messages (including /start)
    # for the unrestriction flow. Must be registered before group handler
    # to prevent group handler from catching private messages first.
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT,
            handle_dm,
        )
    )

    # Handler 3: Group message handler - monitors messages in the configured
    # group and warns/restricts users with incomplete profiles
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    # Register auto-restriction job to run every 5 minutes
    application.job_queue.run_repeating(
        auto_restrict_expired_warnings,
        interval=300,
        first=300,
        name="auto_restrict_job"
    )

    logger.info(f"Bot started. Monitoring group {settings.group_id}")
    logger.info("JobQueue started with auto-restriction job (every 5 minutes)")
    
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
