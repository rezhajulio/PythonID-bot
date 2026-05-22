"""Tests for plugin toggle resolver and plugin contracts."""

from bot.group_config import KNOWN_PLUGINS
from bot.plugins import base
from bot.plugins.config import is_plugin_enabled, resolve_plugin_toggles


class TestResolvePluginToggles:
    """Resolver: defaults True, group override wins."""

    def test_defaults_true_when_no_overrides(self):
        """All plugins True when no overrides specified."""
        toggles = resolve_plugin_toggles({}, None)
        for name in KNOWN_PLUGINS:
            assert toggles[name] is True

    def test_env_default_applied_when_no_group_overrides(self):
        """Env defaults apply to listed plugins; others stay True."""
        env_defaults = {"captcha": False, "dm": False}
        toggles = resolve_plugin_toggles(env_defaults, None)
        assert toggles["captcha"] is False
        assert toggles["dm"] is False
        assert toggles["verify"] is True
        assert toggles["profile_monitor"] is True

    def test_group_override_wins_over_env_default(self):
        """Group override takes precedence over env default."""
        toggles = resolve_plugin_toggles(
            {"captcha": False, "dm": True},
            {"captcha": True},
        )
        assert toggles["captcha"] is True  # group wins
        assert toggles["dm"] is True       # from env

    def test_group_override_empty_falls_to_env(self):
        """Empty group overrides dict falls through to env defaults."""
        toggles = resolve_plugin_toggles({"captcha": False}, {})
        assert toggles["captcha"] is False
        assert toggles["verify"] is True  # not in env either

    def test_empty_env_and_empty_group_all_true(self):
        """Empty env defaults + empty group overrides = all True."""
        toggles = resolve_plugin_toggles({}, {})
        for name in KNOWN_PLUGINS:
            assert toggles[name] is True

    def test_result_contains_all_known_plugins(self):
        """Returned dict always has all KNOWN_PLUGINS keys."""
        toggles = resolve_plugin_toggles({}, None)
        assert set(toggles.keys()) == KNOWN_PLUGINS

    def test_is_plugin_enabled_convenience(self):
        """is_plugin_enabled returns correct bool for a single plugin."""
        toggles = resolve_plugin_toggles({"captcha": False}, None)
        assert is_plugin_enabled(toggles, "captcha") is False
        assert is_plugin_enabled(toggles, "verify") is True

    def test_group_override_false_overrides_env_true(self):
        """Group override False wins over env default True."""
        toggles = resolve_plugin_toggles(
            {"captcha": True},
            {"captcha": False},
        )
        assert toggles["captcha"] is False

    def test_partial_group_override(self):
        """Only overridden plugins use group value; rest use env or True."""
        toggles = resolve_plugin_toggles(
            {"captcha": False, "dm": True, "verify": False},
            {"captcha": True},
        )
        assert toggles["captcha"] is True   # group override
        assert toggles["dm"] is True         # from env
        assert toggles["verify"] is False    # from env
        assert toggles["profile_monitor"] is True  # default True


class TestPluginContracts:
    """Verify plugin base contracts are importable and well-typed."""

    def test_plugin_protocol_exists(self):
        """Plugin protocol is exported from base module."""
        assert hasattr(base, "PluginProtocol")

    def test_plugin_protocol_has_fields(self):
        """Plugin protocol defines expected fields as annotations + register method."""
        assert "name" in base.PluginProtocol.__annotations__
        assert "description" in base.PluginProtocol.__annotations__
        assert "handler_group" in base.PluginProtocol.__annotations__
        assert hasattr(base.PluginProtocol, "register")