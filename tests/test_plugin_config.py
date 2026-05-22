"""Tests for plugin config validation in GroupConfig and Settings."""

import json

import pytest
from pydantic import ValidationError
from pydantic_settings.exceptions import SettingsError

from bot.config import Settings
from bot.group_config import GroupConfig
from bot.plugins.definitions import PLUGIN_NAMES as KNOWN_PLUGINS


class TestKnownPlugins:
    """Verify the KNOWN_PLUGINS set matches design spec."""

    def test_known_plugins_contains_all_expected(self):
        assert "topic_guard" in KNOWN_PLUGINS
        assert "verify" in KNOWN_PLUGINS
        assert "unverify" in KNOWN_PLUGINS
        assert "check" in KNOWN_PLUGINS
        assert "trust" in KNOWN_PLUGINS
        assert "untrust" in KNOWN_PLUGINS
        assert "trusted_list" in KNOWN_PLUGINS
        assert "check_forwarded_message" in KNOWN_PLUGINS
        assert "verify_callback" in KNOWN_PLUGINS
        assert "unverify_callback" in KNOWN_PLUGINS
        assert "warn_callback" in KNOWN_PLUGINS
        assert "trust_callback" in KNOWN_PLUGINS
        assert "untrust_callback" in KNOWN_PLUGINS
        assert "captcha" in KNOWN_PLUGINS
        assert "dm" in KNOWN_PLUGINS
        assert "inline_keyboard_spam" in KNOWN_PLUGINS
        assert "bio_bait_spam" in KNOWN_PLUGINS
        assert "contact_spam" in KNOWN_PLUGINS
        assert "new_user_spam" in KNOWN_PLUGINS
        assert "duplicate_spam" in KNOWN_PLUGINS
        assert "profile_monitor" in KNOWN_PLUGINS
        assert "auto_restrict_job" in KNOWN_PLUGINS
        assert "refresh_admin_ids_job" in KNOWN_PLUGINS

    def test_known_plugins_is_frozen_set(self):
        assert isinstance(KNOWN_PLUGINS, frozenset)


class TestGroupConfigPlugins:
    """Tests for GroupConfig.plugins field validation."""

    def test_plugins_defaults_to_none(self):
        """Default plugins is None (all enabled)."""
        gc = GroupConfig(group_id=-1001234567890, warning_topic_id=42)
        assert gc.plugins is None

    def test_plugins_valid_dict(self):
        """Valid plugin dict with bool values passes."""
        gc = GroupConfig(
            group_id=-1001234567890,
            warning_topic_id=42,
            plugins={"profile_monitor": False, "captcha": True},
        )
        assert gc.plugins == {"profile_monitor": False, "captcha": True}

    def test_plugins_empty_dict(self):
        """Empty dict is valid (no overrides)."""
        gc = GroupConfig(
            group_id=-1001234567890,
            warning_topic_id=42,
            plugins={},
        )
        assert gc.plugins == {}

    def test_plugins_unknown_key_raises(self):
        """Unknown plugin key raises ValueError."""
        with pytest.raises(ValidationError) as excinfo:
            GroupConfig(
                group_id=-1001234567890,
                warning_topic_id=42,
                plugins={"nonexistent_plugin": True},
            )
        assert "Unknown plugin" in str(excinfo.value)

    def test_plugins_unknown_key_in_mixed_dict_raises(self):
        """Even with valid keys present, unknown key still fails."""
        with pytest.raises(ValidationError) as excinfo:
            GroupConfig(
                group_id=-1001234567890,
                warning_topic_id=42,
                plugins={"captcha": True, "fake_plugin": False},
            )
        assert "Unknown plugin" in str(excinfo.value)

    def test_plugins_non_bool_value_raises(self):
        """Non-bool value raises ValueError."""
        with pytest.raises(ValidationError) as excinfo:
            GroupConfig(
                group_id=-1001234567890,
                warning_topic_id=42,
                plugins={"captcha": "yes"},
            )
        assert "must be a boolean" in str(excinfo.value).lower() or "bool" in str(excinfo.value).lower()

    def test_plugins_string_value_raises(self):
        """String 'true' or 'false' not coerced to bool."""
        with pytest.raises(ValidationError) as excinfo:
            GroupConfig(
                group_id=-1001234567890,
                warning_topic_id=42,
                plugins={"captcha": "true"},
            )
        assert "must be a boolean" in str(excinfo.value).lower() or "bool" in str(excinfo.value).lower()

    def test_plugins_int_value_raises(self):
        """Integer 0/1 not coerced to bool."""
        with pytest.raises(ValidationError) as excinfo:
            GroupConfig(
                group_id=-1001234567890,
                warning_topic_id=42,
                plugins={"captcha": 1},
            )
        assert "must be a boolean" in str(excinfo.value).lower() or "bool" in str(excinfo.value).lower()

    def test_plugins_all_off(self):
        """All known plugins set to False is valid."""
        all_off = {name: False for name in KNOWN_PLUGINS}
        gc = GroupConfig(
            group_id=-1001234567890,
            warning_topic_id=42,
            plugins=all_off,
        )
        assert gc.plugins == all_off

    def test_plugins_all_on(self):
        """All known plugins set to True is valid."""
        all_on = {name: True for name in KNOWN_PLUGINS}
        gc = GroupConfig(
            group_id=-1001234567890,
            warning_topic_id=42,
            plugins=all_on,
        )
        assert gc.plugins == all_on

    def test_plugins_loaded_from_json(self):
        """Ensure plugins field works when loading from dict (e.g., groups.json)."""
        data = {
            "group_id": -1001234567890,
            "warning_topic_id": 42,
            "plugins": {"captcha": False, "dm": True},
        }
        gc = GroupConfig(**data)
        assert gc.plugins == {"captcha": False, "dm": True}


class TestSettingsPluginsDefault:
    """Tests for Settings.plugins_default field validation."""

    def test_plugins_default_defaults_to_empty(self, monkeypatch):
        """Default plugins_default is empty dict when env var not set."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")

        settings = Settings(_env_file=None)
        assert settings.plugins_default == {}

    def test_plugins_default_valid_json(self, monkeypatch):
        """Valid JSON string sets plugins_default correctly."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("PLUGINS_DEFAULT", '{"profile_monitor": false, "captcha": true}')

        settings = Settings(_env_file=None)
        assert settings.plugins_default == {"profile_monitor": False, "captcha": True}

    def test_plugins_default_unknown_key_raises(self, monkeypatch):
        """Unknown plugin key in PLUGINS_DEFAULT raises ValueError."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("PLUGINS_DEFAULT", '{"bogus_plugin": true}')

        with pytest.raises((ValueError, SettingsError), match="Unknown plugin"):
            Settings(_env_file=None)

    def test_plugins_default_non_bool_raises(self, monkeypatch):
        """Non-bool value in PLUGINS_DEFAULT raises ValueError."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("PLUGINS_DEFAULT", '{"captcha": "yes"}')

        with pytest.raises((ValueError, SettingsError), match="must be a boolean|bool"):
            Settings(_env_file=None)

    def test_plugins_default_invalid_json_raises(self, monkeypatch):
        """Invalid JSON string in PLUGINS_DEFAULT raises SettingsError."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("PLUGINS_DEFAULT", "not valid json")

        with pytest.raises(SettingsError, match="error parsing value"):
            Settings(_env_file=None)

    def test_plugins_default_json_array_raises(self, monkeypatch):
        """JSON array (not object) raises ValueError."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("PLUGINS_DEFAULT", '["captcha", "dm"]')

        with pytest.raises((ValueError, SettingsError), match="must be a JSON|got array"):
            Settings(_env_file=None)

    def test_plugins_default_empty_json_object(self, monkeypatch):
        """Empty JSON object {} is valid."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("PLUGINS_DEFAULT", "{}")

        settings = Settings(_env_file=None)
        assert settings.plugins_default == {}

    def test_plugins_default_full_set(self, monkeypatch):
        """All known plugins in PLUGINS_DEFAULT is valid."""
        full_set = {name: True for name in KNOWN_PLUGINS}
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("PLUGINS_DEFAULT", json.dumps(full_set))

        settings = Settings(_env_file=None)
        assert settings.plugins_default == full_set