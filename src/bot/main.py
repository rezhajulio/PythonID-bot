"""
Main entry point for the PythonID bot.

This module initializes the bot application, registers all message handlers
via the plugin system, and starts the polling loop.
"""

import logging
from typing import Literal

import logfire
from telegram.error import NetworkError, TimedOut
from telegram.ext import Application, ContextTypes

from bot.config import get_settings
from bot.database.service import get_database, init_database
from bot.group_config import get_group_registry, init_group_registry
from bot.plugins.manager import PluginManager
from bot.services.admin_cache import preload_admin_ids

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
    logfire_min_level: Literal["trace", "debug", "info", "notice", "warn", "warning", "error", "fatal"] = log_level_str.lower()  # type: ignore[assignment]

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
    Uses ``preload_admin_ids`` which preserves existing cached data
    for groups that fail to fetch, preventing admin cache wipe on
    startup failures.
    """
    logger.info("Starting post_init: fetching admin IDs and recovering captcha state")
    registry = get_group_registry()

    # Use preload_admin_ids which preserves cache on failures
    await preload_admin_ids(application)

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
    5. Registers all handlers and jobs via PluginManager in MANIFEST_ORDER
    6. Computes per-group effective plugin toggle map for runtime gating
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

    # Register all handlers and jobs via PluginManager in deterministic order
    pm = PluginManager()
    plugin_handlers = pm.register_all(application)

    logger.info(f"Registered {sum(len(h) for h in plugin_handlers.values())} handler(s) across {len(plugin_handlers)} plugin(s)")

    # Compute and store per-group effective plugin toggle map for runtime gating
    pm.compute_effective_map(settings, registry, application)
    logger.info("Computed per-group effective plugin toggle map")

    logger.info(f"Starting bot polling for {group_count} group(s)")
    logger.info("All handlers registered successfully")

    application.run_polling(allowed_updates=["message", "edited_message", "callback_query", "chat_member"])

if __name__ == "__main__":
    main()