import pytest

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
