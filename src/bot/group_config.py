"""
Multi-group configuration for the PythonID bot.

This module provides per-group settings via GroupConfig and a GroupRegistry
that allows a single bot instance to manage multiple Telegram groups.
Groups can be configured via a groups.json file or fall back to the
single-group .env configuration for backward compatibility.
"""

import json
import logging
from datetime import timedelta
from pathlib import Path

from pydantic import BaseModel, field_validator
from telegram import Update

logger = logging.getLogger(__name__)


class GroupConfig(BaseModel):
    """
    Per-group configuration settings.

    Each monitored group has its own set of feature flags and thresholds.
    """

    group_id: int
    warning_topic_id: int
    restrict_failed_users: bool = False
    warning_threshold: int = 3
    warning_time_threshold_minutes: int = 180
    captcha_enabled: bool = False
    captcha_timeout_seconds: int = 120
    new_user_probation_hours: int = 72
    new_user_violation_threshold: int = 3
    rules_link: str = "https://t.me/pythonID/290029/321799"

    @field_validator("group_id")
    @classmethod
    def group_id_must_be_negative(cls, v: int) -> int:
        if v >= 0:
            raise ValueError("group_id must be negative (Telegram supergroup IDs are negative)")
        return v

    @field_validator("warning_threshold")
    @classmethod
    def warning_threshold_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("warning_threshold must be greater than 0")
        return v

    @field_validator("warning_time_threshold_minutes")
    @classmethod
    def warning_time_threshold_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("warning_time_threshold_minutes must be greater than 0")
        return v

    @field_validator("captcha_timeout_seconds")
    @classmethod
    def captcha_timeout_must_be_in_range(cls, v: int) -> int:
        if not (10 <= v <= 600):
            raise ValueError("captcha_timeout_seconds must be between 10 and 600 seconds")
        return v

    @field_validator("new_user_probation_hours")
    @classmethod
    def probation_hours_must_be_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("new_user_probation_hours must be >= 0")
        return v

    @property
    def probation_timedelta(self) -> timedelta:
        return timedelta(hours=self.new_user_probation_hours)

    @property
    def warning_time_threshold_timedelta(self) -> timedelta:
        return timedelta(minutes=self.warning_time_threshold_minutes)

    @property
    def captcha_timeout_timedelta(self) -> timedelta:
        return timedelta(seconds=self.captcha_timeout_seconds)


class GroupRegistry:
    """
    Registry of monitored groups.

    Provides O(1) lookup by group_id and iteration over all groups.
    """

    def __init__(self) -> None:
        self._groups: dict[int, GroupConfig] = {}

    def register(self, config: GroupConfig) -> None:
        if config.group_id in self._groups:
            raise ValueError(f"Duplicate group_id: {config.group_id}")
        self._groups[config.group_id] = config
        logger.info(f"Registered group {config.group_id} (warning_topic={config.warning_topic_id})")

    def get(self, group_id: int) -> GroupConfig | None:
        return self._groups.get(group_id)

    def all_groups(self) -> list[GroupConfig]:
        return list(self._groups.values())

    def is_monitored(self, group_id: int) -> bool:
        return group_id in self._groups


def load_groups_from_json(path: str) -> list[GroupConfig]:
    """
    Parse a groups.json file into a list of GroupConfig objects.

    Args:
        path: Path to the JSON file.

    Returns:
        List of GroupConfig instances.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        json.JSONDecodeError: If the file is not valid JSON.
        ValueError: If the JSON structure is invalid.
    """
    with open(path) as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("groups.json must contain a JSON array of group objects")

    if not data:
        raise ValueError("groups.json must contain at least one group")

    configs = [GroupConfig(**item) for item in data]

    # Check for duplicate group_ids
    seen_ids: set[int] = set()
    for config in configs:
        if config.group_id in seen_ids:
            raise ValueError(f"Duplicate group_id in groups.json: {config.group_id}")
        seen_ids.add(config.group_id)

    return configs


def build_group_registry(settings: object) -> GroupRegistry:
    """
    Build a GroupRegistry from settings.

    If groups.json exists at the configured path, loads from it.
    Otherwise creates a single GroupConfig from .env fields (backward compatible).

    Args:
        settings: Application Settings instance.

    Returns:
        Populated GroupRegistry.
    """
    registry = GroupRegistry()
    groups_path = getattr(settings, "groups_config_path", "groups.json")

    if Path(groups_path).exists():
        logger.info(f"Loading group configuration from {groups_path}")
        configs = load_groups_from_json(groups_path)
        for config in configs:
            registry.register(config)
        logger.info(f"Loaded {len(configs)} group(s) from {groups_path}")
    else:
        logger.info("No groups.json found, using single-group config from .env")
        config = GroupConfig(
            group_id=settings.group_id,
            warning_topic_id=settings.warning_topic_id,
            restrict_failed_users=settings.restrict_failed_users,
            warning_threshold=settings.warning_threshold,
            warning_time_threshold_minutes=settings.warning_time_threshold_minutes,
            captcha_enabled=settings.captcha_enabled,
            captcha_timeout_seconds=settings.captcha_timeout_seconds,
            new_user_probation_hours=settings.new_user_probation_hours,
            new_user_violation_threshold=settings.new_user_violation_threshold,
            rules_link=settings.rules_link,
        )
        registry.register(config)

    return registry


def get_group_config_for_update(update: Update) -> GroupConfig | None:
    """
    Get the GroupConfig for the group in the given Update.

    Returns None if the update's chat is not a monitored group.

    Args:
        update: Telegram Update object.

    Returns:
        GroupConfig if the chat is monitored, None otherwise.
    """
    if not update.effective_chat:
        return None
    return get_group_registry().get(update.effective_chat.id)


# Module-level singleton
_registry: GroupRegistry | None = None


def init_group_registry(settings: object) -> GroupRegistry:
    """
    Initialize the global group registry singleton.

    Must be called once at application startup.

    Args:
        settings: Application Settings instance.

    Returns:
        Initialized GroupRegistry.
    """
    global _registry
    _registry = build_group_registry(settings)
    return _registry


def get_group_registry() -> GroupRegistry:
    """
    Get the global group registry singleton.

    Returns:
        GroupRegistry instance.

    Raises:
        RuntimeError: If init_group_registry() hasn't been called.
    """
    if _registry is None:
        raise RuntimeError("Group registry not initialized. Call init_group_registry() first.")
    return _registry


def reset_group_registry() -> None:
    """Reset the group registry singleton (for testing)."""
    global _registry
    _registry = None
