"""Tests for the config module."""

import pytest
from pydantic_settings.exceptions import SettingsError

from bot.config import Settings, get_settings, get_env_file


class TestGetEnvFile:
    def test_default_production(self, monkeypatch, tmp_path):
        monkeypatch.delenv("BOT_ENV", raising=False)
        monkeypatch.chdir(tmp_path)
        tmp_path.joinpath(".env").touch()
        assert get_env_file() == ".env"

    def test_production_explicit(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BOT_ENV", "production")
        monkeypatch.chdir(tmp_path)
        tmp_path.joinpath(".env").touch()
        assert get_env_file() == ".env"

    def test_staging_environment(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BOT_ENV", "staging")
        monkeypatch.chdir(tmp_path)
        tmp_path.joinpath(".env.staging").touch()
        assert get_env_file() == ".env.staging"

    def test_unknown_environment_falls_back_to_default(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BOT_ENV", "unknown")
        monkeypatch.chdir(tmp_path)
        tmp_path.joinpath(".env").touch()
        assert get_env_file() == ".env"

    def test_no_env_file_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.delenv("BOT_ENV", raising=False)
        monkeypatch.chdir(tmp_path)
        assert get_env_file() is None

class TestSettings:
    def test_settings_from_env(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token_123")
        monkeypatch.setenv("GROUP_ID", "-1001234567890")
        monkeypatch.setenv("WARNING_TOPIC_ID", "42")

        settings = Settings(_env_file=None)

        assert settings.telegram_bot_token == "test_token_123"
        assert settings.group_id == -1001234567890
        assert settings.warning_topic_id == 42

    def test_settings_missing_required_field(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("GROUP_ID", raising=False)
        monkeypatch.delenv("WARNING_TOPIC_ID", raising=False)

        with pytest.raises(Exception):
            Settings(_env_file=None)

    def test_get_settings_cached(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "cached_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")

        get_settings.cache_clear()

        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2

    def test_logfire_environment_auto_detection_staging(self, monkeypatch):
        """Test that logfire_environment is set to 'staging' when BOT_ENV=staging."""
        monkeypatch.setenv("BOT_ENV", "staging")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")

        settings = Settings(_env_file=None)

        assert settings.logfire_environment == "staging"

    def test_logfire_environment_defaults_to_production(self, monkeypatch):
        """Test that logfire_environment defaults to production when BOT_ENV is not set."""
        monkeypatch.delenv("BOT_ENV", raising=False)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")

        settings = Settings(_env_file=None)

        assert settings.logfire_environment == "production"

    def test_duplicate_spam_defaults(self, monkeypatch):
        """Test that duplicate_spam fields have correct defaults."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")

        settings = Settings(_env_file=None)

        assert settings.duplicate_spam_enabled is True
        assert settings.duplicate_spam_window_seconds == 120
        assert settings.duplicate_spam_threshold == 2
        assert settings.duplicate_spam_min_length == 20

    def test_duplicate_spam_from_env(self, monkeypatch):
        """Test that duplicate_spam fields are read from environment variables."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("DUPLICATE_SPAM_ENABLED", "false")
        monkeypatch.setenv("DUPLICATE_SPAM_WINDOW_SECONDS", "300")
        monkeypatch.setenv("DUPLICATE_SPAM_THRESHOLD", "5")
        monkeypatch.setenv("DUPLICATE_SPAM_MIN_LENGTH", "50")

        settings = Settings(_env_file=None)

        assert settings.duplicate_spam_enabled is False
        assert settings.duplicate_spam_window_seconds == 300
        assert settings.duplicate_spam_threshold == 5
        assert settings.duplicate_spam_min_length == 50

    def test_bio_bait_monitor_defaults(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")

        settings = Settings(_env_file=None)

        assert settings.bio_bait_monitor_only is False
        assert settings.bio_bait_alert_chat_id is None

    def test_bio_bait_monitor_from_env(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("BIO_BAIT_MONITOR_ONLY", "true")
        monkeypatch.setenv("BIO_BAIT_ALERT_CHAT_ID", "57747812")

        settings = Settings(_env_file=None)

        assert settings.bio_bait_monitor_only is True
        assert settings.bio_bait_alert_chat_id == 57747812

    def test_guest_bot_whitelist_from_env(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("GUEST_BOT_WHITELIST", "@somebot,anotherbot")

        settings = Settings(_env_file=None)

        assert settings.guest_bot_whitelist == ["somebot", "anotherbot"]

    def test_guest_bot_whitelist_empty_env(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("GUEST_BOT_WHITELIST", "")

        settings = Settings(_env_file=None)

        assert settings.guest_bot_whitelist == []

class TestPluginsDefault:
    def test_default_empty_dict(self, monkeypatch):
        """Test plugins_default defaults to empty dict when not set."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")

        settings = Settings(_env_file=None)

        assert settings.plugins_default == {}

    def test_valid_json_string(self, monkeypatch):
        """Test valid JSON string with known plugins."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("PLUGINS_DEFAULT", '{"captcha": true, "dm": false}')

        settings = Settings(_env_file=None)

        assert settings.plugins_default == {"captcha": True, "dm": False}

    def test_empty_string_raises_from_env(self, monkeypatch):
        """Test empty string env var raises SettingsError from env source.

        Note: Pydantic's EnvSettingsSource raises before the validator runs.
        This is consistent behavior for env vars - empty strings are not valid JSON.
        The validator handles empty strings correctly for direct constructor calls.
        """
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("PLUGINS_DEFAULT", "")

        with pytest.raises(SettingsError, match="error parsing value"):
            Settings(_env_file=None)

    def test_whitespace_only_string_raises_from_env(self, monkeypatch):
        """Test whitespace-only string env var raises SettingsError from env source.

        Note: Pydantic's EnvSettingsSource raises before the validator runs.
        This is consistent behavior for env vars - empty strings are not valid JSON.
        The validator handles empty strings correctly for direct constructor calls.
        """
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("PLUGINS_DEFAULT", "   ")

        with pytest.raises(SettingsError, match="error parsing value"):
            Settings(_env_file=None)

    def test_empty_string_from_constructor_returns_empty_dict(self, monkeypatch):
        """Test empty string from constructor returns empty dict.

        The validator handles empty strings correctly when called directly.
        """
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")

        settings = Settings(_env_file=None, plugins_default="")
        assert settings.plugins_default == {}

    def test_single_plugin(self, monkeypatch):
        """Test single plugin entry."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("PLUGINS_DEFAULT", '{"captcha": false}')

        settings = Settings(_env_file=None)

        assert settings.plugins_default == {"captcha": False}

    def test_all_known_plugins(self, monkeypatch):
        """Test dict with all known plugin names (using a subset)."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv(
            "PLUGINS_DEFAULT",
            '{"captcha": true, "dm": true, "verify": false, "check": true}',
        )

        settings = Settings(_env_file=None)

        assert settings.plugins_default == {
            "captcha": True,
            "dm": True,
            "verify": False,
            "check": True,
        }

    def test_invalid_json_string_raises(self, monkeypatch):
        """Test invalid JSON string env var raises SettingsError."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("PLUGINS_DEFAULT", "not valid json")

        with pytest.raises(SettingsError, match="error parsing value"):
            Settings(_env_file=None)

    def test_invalid_json_string_via_constructor_raises(self, monkeypatch):
        """Test invalid JSON string passed via constructor raises our ValueError."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")

        with pytest.raises(ValueError, match="PLUGINS_DEFAULT must be a valid JSON string"):
            Settings(_env_file=None, plugins_default="not valid json")

    def test_empty_string_via_constructor_is_accepted(self, monkeypatch):
        """Test empty string passed via constructor is accepted (bypasses env source)."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")

        settings = Settings(_env_file=None, plugins_default="")
        assert settings.plugins_default == {}

    def test_json_array_raises(self, monkeypatch):
        """Test JSON array raises ValueError (must be object)."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("PLUGINS_DEFAULT", '["captcha", "dm"]')

        with pytest.raises(ValueError, match="PLUGINS_DEFAULT must be a JSON object"):
            Settings(_env_file=None)

    def test_unknown_plugin_key_raises(self, monkeypatch):
        """Test unknown plugin key raises ValueError."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("PLUGINS_DEFAULT", '{"nonexistent_plugin": true}')

        with pytest.raises(ValueError, match="Unknown plugin key.*nonexistent_plugin"):
            Settings(_env_file=None)

    def test_non_bool_value_raises(self, monkeypatch):
        """Test non-boolean value raises ValueError."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("PLUGINS_DEFAULT", '{"captcha": "yes"}')

        with pytest.raises(ValueError, match="must be a boolean"):
            Settings(_env_file=None)

    def test_integer_value_raises(self, monkeypatch):
        """Test integer value raises ValueError (must be boolean)."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("PLUGINS_DEFAULT", '{"captcha": 1}')

        with pytest.raises(ValueError, match="must be a boolean"):
            Settings(_env_file=None)

    def test_null_value_raises(self, monkeypatch):
        """Test null value raises ValueError."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("PLUGINS_DEFAULT", '{"captcha": null}')

        with pytest.raises(ValueError, match="must be a boolean"):
            Settings(_env_file=None)

class TestSettingsValidation:
    def test_group_id_must_be_negative(self, monkeypatch):
        """Test that group_id must be a negative number."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "123456")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")

        with pytest.raises(ValueError, match="group_id must be negative"):
            Settings(_env_file=None)

    def test_warning_threshold_must_be_positive(self, monkeypatch):
        """Test that warning_threshold must be greater than 0."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("WARNING_THRESHOLD", "0")

        with pytest.raises(ValueError, match="warning_threshold must be greater than 0"):
            Settings(_env_file=None)

    def test_new_user_probation_hours_must_be_non_negative(self, monkeypatch):
        """Test that new_user_probation_hours must be >= 0."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("NEW_USER_PROBATION_HOURS", "-1")

        with pytest.raises(ValueError, match="new_user_probation_hours must be >= 0"):
            Settings(_env_file=None)

    def test_captcha_timeout_must_be_in_range_too_low(self, monkeypatch):
        """Test that captcha_timeout_seconds must be at least 10."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("CAPTCHA_TIMEOUT_SECONDS", "5")

        with pytest.raises(ValueError, match="captcha_timeout_seconds must be between 10 and 600"):
            Settings(_env_file=None)

    def test_captcha_timeout_must_be_in_range_too_high(self, monkeypatch):
        """Test that captcha_timeout_seconds must be at most 600."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("CAPTCHA_TIMEOUT_SECONDS", "700")

        with pytest.raises(ValueError, match="captcha_timeout_seconds must be between 10 and 600"):
            Settings(_env_file=None)

    def test_warning_time_threshold_must_be_positive(self, monkeypatch):
        """Test that warning_time_threshold_minutes must be greater than 0."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("GROUP_ID", "-100999")
        monkeypatch.setenv("WARNING_TOPIC_ID", "1")
        monkeypatch.setenv("WARNING_TIME_THRESHOLD_MINUTES", "0")

        with pytest.raises(ValueError, match="warning_time_threshold_minutes must be greater than 0"):
            Settings(_env_file=None)
