"""
Configuration module for the PythonID bot.

This module handles loading and validating configuration from environment
variables using Pydantic Settings. It supports multiple environments
(production, staging) via the BOT_ENV environment variable.
"""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def get_env_file() -> str:
    """
    Determine which .env file to load based on BOT_ENV environment variable.

    Returns:
        str: Path to the environment file.
            - "production" or default -> ".env"
            - "staging" -> ".env.staging"
    """
    env = os.getenv("BOT_ENV", "production")
    env_files = {
        "production": ".env",
        "staging": ".env.staging",
    }
    return env_files.get(env, ".env")


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

    model_config = SettingsConfigDict(
        env_file=get_env_file(),
        env_file_encoding="utf-8",
    )


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
