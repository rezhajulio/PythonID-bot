"""
Configuration module for the PythonID bot.

This module handles loading and validating configuration from environment
variables using Pydantic Settings. It supports multiple environments
(production, staging) via the BOT_ENV environment variable.
"""

import json
import logging
import os
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
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
    env_file = ".env.staging" if env == "staging" else ".env"

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
    contact_spam_restrict: bool = True
    duplicate_spam_enabled: bool = True
    duplicate_spam_window_seconds: int = 120
    duplicate_spam_threshold: int = 2
    duplicate_spam_min_length: int = 20
    duplicate_spam_similarity: float = 0.95
    bio_bait_enabled: bool = True
    bio_bait_monitor_only: bool = False
    bio_bait_alert_chat_id: int | None = None
    moderation_topic_id: int | None = None
    groups_config_path: str = "groups.json"
    logfire_token: str | None = None
    logfire_service_name: str = "pythonid-bot"
    logfire_environment: str = "production"
    logfire_enabled: bool = True
    log_level: str = "INFO"
    plugins_default: dict[str, bool] = {}

    model_config = SettingsConfigDict(
        env_file=get_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("plugins_default", mode="before")
    @classmethod
    def parse_and_validate_plugins_default(cls, v: object) -> dict[str, bool]:
        """Parse PLUGINS_DEFAULT env var as JSON object and validate keys/values."""
        if isinstance(v, dict):
            parsed = v
        elif isinstance(v, str):
            if not v.strip():
                return {}
            try:
                parsed = json.loads(v)
            except json.JSONDecodeError:
                raise ValueError("PLUGINS_DEFAULT must be a valid JSON string")
            if not isinstance(parsed, dict):
                raise ValueError("PLUGINS_DEFAULT must be a JSON object")
        elif isinstance(v, list):
            raise ValueError("PLUGINS_DEFAULT must be a JSON object, got array")
        else:
            return {}
        from bot.plugins.config import validate_plugin_map
        return validate_plugin_map(parsed)

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
        for field in (
            "group_id",
            "warning_topic_id",
            "restrict_failed_users",
            "warning_threshold",
            "warning_time_threshold_minutes",
            "database_path",
            "captcha_enabled",
            "captcha_timeout_seconds",
            "new_user_probation_hours",
            "new_user_violation_threshold",
            "bio_bait_enabled",
            "bio_bait_monitor_only",
            "bio_bait_alert_chat_id",
            "moderation_topic_id",
        ):
            logger.debug(f"{field}: {getattr(self, field)}")
        logger.debug(f"telegram_bot_token: {'***' + self.telegram_bot_token[-4:]}")
        logger.debug(f"logfire_enabled: {self.logfire_enabled}")
        logger.debug(f"logfire_environment: {self.logfire_environment}")
        logger.debug(f"plugins_default: {self.plugins_default}")


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
