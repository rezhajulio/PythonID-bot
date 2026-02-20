"""Tests for the group_config module."""

import json
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from bot.group_config import (
    GroupConfig,
    GroupRegistry,
    build_group_registry,
    get_group_config_for_update,
    get_group_registry,
    init_group_registry,
    load_groups_from_json,
    reset_group_registry,
)


class TestGroupConfig:
    def test_minimal_config(self):
        gc = GroupConfig(group_id=-1001234567890, warning_topic_id=42)
        assert gc.group_id == -1001234567890
        assert gc.warning_topic_id == 42
        assert gc.restrict_failed_users is False
        assert gc.warning_threshold == 3
        assert gc.captcha_enabled is False

    def test_full_config(self):
        gc = GroupConfig(
            group_id=-1001234567890,
            warning_topic_id=42,
            restrict_failed_users=True,
            warning_threshold=5,
            warning_time_threshold_minutes=60,
            captcha_enabled=True,
            captcha_timeout_seconds=180,
            new_user_probation_hours=168,
            new_user_violation_threshold=2,
            rules_link="https://t.me/mygroup/rules",
        )
        assert gc.restrict_failed_users is True
        assert gc.warning_threshold == 5
        assert gc.captcha_timeout_seconds == 180

    def test_group_id_must_be_negative(self):
        with pytest.raises(ValidationError, match="group_id must be negative"):
            GroupConfig(group_id=123, warning_topic_id=42)

    def test_group_id_zero_rejected(self):
        with pytest.raises(ValidationError, match="group_id must be negative"):
            GroupConfig(group_id=0, warning_topic_id=42)

    def test_warning_threshold_must_be_positive(self):
        with pytest.raises(ValidationError, match="warning_threshold must be greater than 0"):
            GroupConfig(group_id=-1, warning_topic_id=42, warning_threshold=0)

    def test_warning_time_threshold_must_be_positive(self):
        with pytest.raises(ValidationError, match="warning_time_threshold_minutes must be greater than 0"):
            GroupConfig(group_id=-1, warning_topic_id=42, warning_time_threshold_minutes=0)

    def test_captcha_timeout_must_be_in_range(self):
        with pytest.raises(ValidationError, match="captcha_timeout_seconds must be between 10 and 600"):
            GroupConfig(group_id=-1, warning_topic_id=42, captcha_timeout_seconds=5)
        with pytest.raises(ValidationError, match="captcha_timeout_seconds must be between 10 and 600"):
            GroupConfig(group_id=-1, warning_topic_id=42, captcha_timeout_seconds=601)

    def test_probation_hours_must_be_non_negative(self):
        with pytest.raises(ValidationError, match="new_user_probation_hours must be >= 0"):
            GroupConfig(group_id=-1, warning_topic_id=42, new_user_probation_hours=-1)

    def test_probation_hours_zero_is_valid(self):
        gc = GroupConfig(group_id=-1, warning_topic_id=42, new_user_probation_hours=0)
        assert gc.new_user_probation_hours == 0

    def test_probation_timedelta(self):
        gc = GroupConfig(group_id=-1, warning_topic_id=42, new_user_probation_hours=72)
        assert gc.probation_timedelta == timedelta(hours=72)

    def test_warning_time_threshold_timedelta(self):
        gc = GroupConfig(group_id=-1, warning_topic_id=42, warning_time_threshold_minutes=180)
        assert gc.warning_time_threshold_timedelta == timedelta(minutes=180)

    def test_captcha_timeout_timedelta(self):
        gc = GroupConfig(group_id=-1, warning_topic_id=42, captcha_timeout_seconds=120)
        assert gc.captcha_timeout_timedelta == timedelta(seconds=120)


class TestGroupRegistry:
    def test_register_and_get(self):
        registry = GroupRegistry()
        gc = GroupConfig(group_id=-100, warning_topic_id=1)
        registry.register(gc)
        assert registry.get(-100) == gc

    def test_get_returns_none_for_unknown(self):
        registry = GroupRegistry()
        assert registry.get(-999) is None

    def test_is_monitored(self):
        registry = GroupRegistry()
        gc = GroupConfig(group_id=-100, warning_topic_id=1)
        registry.register(gc)
        assert registry.is_monitored(-100) is True
        assert registry.is_monitored(-999) is False

    def test_all_groups(self):
        registry = GroupRegistry()
        gc1 = GroupConfig(group_id=-100, warning_topic_id=1)
        gc2 = GroupConfig(group_id=-200, warning_topic_id=2)
        registry.register(gc1)
        registry.register(gc2)
        groups = registry.all_groups()
        assert len(groups) == 2
        assert gc1 in groups
        assert gc2 in groups

    def test_duplicate_group_id_raises(self):
        registry = GroupRegistry()
        gc = GroupConfig(group_id=-100, warning_topic_id=1)
        registry.register(gc)
        with pytest.raises(ValueError, match="Duplicate group_id"):
            registry.register(gc)

    def test_empty_registry(self):
        registry = GroupRegistry()
        assert registry.all_groups() == []
        assert registry.get(-100) is None
        assert registry.is_monitored(-100) is False


class TestLoadGroupsFromJson:
    def test_load_valid_json(self):
        data = [
            {"group_id": -100, "warning_topic_id": 1},
            {"group_id": -200, "warning_topic_id": 2},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            configs = load_groups_from_json(f.name)

        assert len(configs) == 2
        assert configs[0].group_id == -100
        assert configs[1].group_id == -200

    def test_load_with_all_fields(self):
        data = [
            {
                "group_id": -100,
                "warning_topic_id": 1,
                "restrict_failed_users": True,
                "warning_threshold": 5,
                "captcha_enabled": True,
                "captcha_timeout_seconds": 180,
                "rules_link": "https://example.com/rules",
            }
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            configs = load_groups_from_json(f.name)

        assert configs[0].restrict_failed_users is True
        assert configs[0].warning_threshold == 5

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_groups_from_json("/nonexistent/path.json")

    def test_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not json")
            f.flush()
            with pytest.raises(json.JSONDecodeError):
                load_groups_from_json(f.name)

    def test_not_array(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"group_id": -100}, f)
            f.flush()
            with pytest.raises(ValueError, match="must contain a JSON array"):
                load_groups_from_json(f.name)

    def test_empty_array(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([], f)
            f.flush()
            with pytest.raises(ValueError, match="must contain at least one group"):
                load_groups_from_json(f.name)

    def test_duplicate_group_ids(self):
        data = [
            {"group_id": -100, "warning_topic_id": 1},
            {"group_id": -100, "warning_topic_id": 2},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            with pytest.raises(ValueError, match="Duplicate group_id"):
                load_groups_from_json(f.name)

    def test_invalid_group_config(self):
        data = [{"group_id": 123, "warning_topic_id": 1}]  # Positive group_id
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            with pytest.raises(ValidationError, match="group_id must be negative"):
                load_groups_from_json(f.name)


class TestBuildGroupRegistry:
    def test_builds_from_json_file(self):
        data = [
            {"group_id": -100, "warning_topic_id": 1},
            {"group_id": -200, "warning_topic_id": 2},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()

            settings = MagicMock()
            settings.groups_config_path = f.name

            registry = build_group_registry(settings)

        assert len(registry.all_groups()) == 2
        assert registry.is_monitored(-100)
        assert registry.is_monitored(-200)

    def test_falls_back_to_env(self):
        settings = MagicMock()
        settings.groups_config_path = "/nonexistent/groups.json"
        settings.group_id = -1001234567890
        settings.warning_topic_id = 42
        settings.restrict_failed_users = False
        settings.warning_threshold = 3
        settings.warning_time_threshold_minutes = 180
        settings.captcha_enabled = False
        settings.captcha_timeout_seconds = 120
        settings.new_user_probation_hours = 72
        settings.new_user_violation_threshold = 3
        settings.rules_link = "https://t.me/test/rules"

        registry = build_group_registry(settings)

        assert len(registry.all_groups()) == 1
        gc = registry.get(-1001234567890)
        assert gc is not None
        assert gc.warning_topic_id == 42
        assert gc.rules_link == "https://t.me/test/rules"


class TestGetGroupConfigForUpdate:
    def test_returns_config_for_monitored_group(self):
        gc = GroupConfig(group_id=-100, warning_topic_id=1)
        registry = GroupRegistry()
        registry.register(gc)

        update = MagicMock()
        update.effective_chat = MagicMock()
        update.effective_chat.id = -100

        with patch("bot.group_config.get_group_registry", return_value=registry):
            result = get_group_config_for_update(update)

        assert result == gc

    def test_returns_none_for_unmonitored_group(self):
        registry = GroupRegistry()

        update = MagicMock()
        update.effective_chat = MagicMock()
        update.effective_chat.id = -999

        with patch("bot.group_config.get_group_registry", return_value=registry):
            result = get_group_config_for_update(update)

        assert result is None

    def test_returns_none_when_no_effective_chat(self):
        update = MagicMock()
        update.effective_chat = None

        result = get_group_config_for_update(update)
        assert result is None


class TestSingleton:
    def setup_method(self):
        reset_group_registry()

    def teardown_method(self):
        reset_group_registry()

    def test_get_before_init_raises(self):
        with pytest.raises(RuntimeError, match="not initialized"):
            get_group_registry()

    def test_init_and_get(self):
        settings = MagicMock()
        settings.groups_config_path = "/nonexistent/groups.json"
        settings.group_id = -100
        settings.warning_topic_id = 1
        settings.restrict_failed_users = False
        settings.warning_threshold = 3
        settings.warning_time_threshold_minutes = 180
        settings.captcha_enabled = False
        settings.captcha_timeout_seconds = 120
        settings.new_user_probation_hours = 72
        settings.new_user_violation_threshold = 3
        settings.rules_link = "https://t.me/test/rules"

        registry = init_group_registry(settings)
        assert registry is get_group_registry()
        assert registry.is_monitored(-100)

    def test_reset_clears_registry(self):
        settings = MagicMock()
        settings.groups_config_path = "/nonexistent/groups.json"
        settings.group_id = -100
        settings.warning_topic_id = 1
        settings.restrict_failed_users = False
        settings.warning_threshold = 3
        settings.warning_time_threshold_minutes = 180
        settings.captcha_enabled = False
        settings.captcha_timeout_seconds = 120
        settings.new_user_probation_hours = 72
        settings.new_user_violation_threshold = 3
        settings.rules_link = "https://t.me/test/rules"

        init_group_registry(settings)
        reset_group_registry()

        with pytest.raises(RuntimeError, match="not initialized"):
            get_group_registry()
