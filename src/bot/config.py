"""
Configuration module for the PythonID bot.

This module handles loading and validating configuration from environment
variables using Pydantic Settings. It supports multiple environments
(production, staging) via the BOT_ENV environment variable.
"""

import logging
import os
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def get_env_file() -> str | None:
    """
    Determine which .env file to load based on BOT_ENV environment variable.

    Returns:
        str | None: Path to the environment file if it exists, None otherwise.
            - "production" or default -> ".env" (if exists)
            - "staging" -> ".env.staging" (if exists)
    """
    env = os.getenv("BOT_ENV", "production")
    env_files = {
        "production": ".env",
        "staging": ".env.staging",
    }
    env_file = env_files.get(env, ".env")
    
    # Return path only if file exists, otherwise return None
    # Pydantic will load from environment variables if no .env file
    if Path(env_file).exists():
        logger.debug(f"Loading configuration from: {env_file}")
        return env_file
    else:
        logger.debug(f"No .env file found at {env_file}, loading from environment variables")
        return None


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Attributes:
        telegram_bot_token: Bot token from @BotFather (required).
        group_id: Telegram group ID to monitor (required, negative number).
        warning_topic_id: Topic ID where warnings are posted (required).
        restrict_failed_users: Enable progressive restriction mode.
        warning_threshold: Number of messages before restricting user.
        warning_time_threshold_minutes: Minutes before auto-restricting user.
        database_path: Path to SQLite database file.
        rules_link: URL to group rules message.
        captcha_enabled: Feature flag to enable/disable captcha verification.
        captcha_timeout: Seconds before auto-ban if user doesn't verify.
        new_user_probation_hours: Hours new users are on probation (no links/forwards).
        new_user_violation_threshold: Violations before restricting user.
        logfire_token: Logfire API token (optional, required for production logging).
        logfire_service_name: Service name for Logfire traces.
        logfire_environment: Environment name (production/staging).
        logfire_enabled: Enable/disable Logfire logging.
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """

    telegram_bot_token: str
    group_id: int
    warning_topic_id: int
    restrict_failed_users: bool = False
    warning_threshold: int = 3
    warning_time_threshold_minutes: int = 180
    database_path: str = "data/bot.db"
    rules_link: str = "https://t.me/pythonID/290029/321799"
    captcha_enabled: bool = False
    captcha_timeout_seconds: int = 120
    new_user_probation_hours: int = 72  # 3 days default
    new_user_violation_threshold: int = 3  # restrict after this many violations
    groups_config_path: str = "groups.json"
    logfire_token: str | None = None
    logfire_service_name: str = "pythonid-bot"
    logfire_environment: str = "production"
    logfire_enabled: bool = True
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=get_env_file(),
        env_file_encoding="utf-8",
    )

    def model_post_init(self, __context):
        """Validate and log non-sensitive configuration values after initialization."""
        if self.group_id >= 0:
            raise ValueError("group_id must be negative (Telegram supergroup IDs are negative)")
        if self.warning_threshold <= 0:
            raise ValueError("warning_threshold must be greater than 0")
        if self.new_user_probation_hours < 0:
            raise ValueError("new_user_probation_hours must be >= 0")
        if not (10 <= self.captcha_timeout_seconds <= 600):
            raise ValueError("captcha_timeout_seconds must be between 10 and 600 seconds")
        if self.warning_time_threshold_minutes <= 0:
            raise ValueError("warning_time_threshold_minutes must be greater than 0")

        # Set logfire_environment based on BOT_ENV if not explicitly set
        env = os.getenv("BOT_ENV", "production")
        if self.logfire_environment == "production" and env == "staging":
            self.logfire_environment = "staging"
        
        logger.info("Configuration loaded successfully")
        logger.debug(f"group_id: {self.group_id}")
        logger.debug(f"warning_topic_id: {self.warning_topic_id}")
        logger.debug(f"restrict_failed_users: {self.restrict_failed_users}")
        logger.debug(f"warning_threshold: {self.warning_threshold}")
        logger.debug(f"warning_time_threshold_minutes: {self.warning_time_threshold_minutes}")
        logger.debug(f"database_path: {self.database_path}")
        logger.debug(f"captcha_enabled: {self.captcha_enabled}")
        logger.debug(f"captcha_timeout_seconds: {self.captcha_timeout_seconds}")
        logger.debug(f"new_user_probation_hours: {self.new_user_probation_hours}")
        logger.debug(f"new_user_violation_threshold: {self.new_user_violation_threshold}")
        logger.debug(f"telegram_bot_token: {'***' + self.telegram_bot_token[-4:]}")  # Mask sensitive token
        logger.debug(f"logfire_enabled: {self.logfire_enabled}")
        logger.debug(f"logfire_environment: {self.logfire_environment}")

    @property
    def probation_timedelta(self) -> timedelta:
        return timedelta(hours=self.new_user_probation_hours)

    @property
    def warning_time_threshold_timedelta(self) -> timedelta:
        return timedelta(minutes=self.warning_time_threshold_minutes)

    @property
    def captcha_timeout_timedelta(self) -> timedelta:
        return timedelta(seconds=self.captcha_timeout_seconds)


@lru_cache
def get_settings() -> Settings:
    """
    Get cached application settings.

    Settings are loaded once and cached for subsequent calls.
    Use lru_cache to avoid re-reading environment on every access.

    Returns:
        Settings: Application configuration instance.
    """
    return Settings()
