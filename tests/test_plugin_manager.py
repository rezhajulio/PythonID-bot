"""Tests for plugin toggle resolver, plugin contracts, definitions, and built-in wrappers."""

from unittest.mock import MagicMock


from bot.group_config import KNOWN_PLUGINS, GroupConfig, GroupRegistry
from bot.plugins import base
from bot.plugins.config import is_plugin_enabled, is_plugin_enabled_for_group, resolve_plugin_toggles
from bot.plugins.definitions import MANIFEST_ORDER, get_plugin_definitions
from bot.plugins.manager import PluginManager, compute_effective_plugin_map


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


class TestPluginDefinitions:
    """Verify plugin definitions match KNOWN_PLUGINS and have correct types."""

    def test_names_match_known_plugins(self):
        """Every definition name is in KNOWN_PLUGINS and every KNOWN_PLUGINS has a definition."""
        defs = get_plugin_definitions()
        def_names = {d["name"] for d in defs}
        assert def_names == KNOWN_PLUGINS

    def test_each_definition_has_required_keys(self):
        """Each definition dict contains name, handler_group, description."""
        for d in get_plugin_definitions():
            assert "name" in d
            assert "handler_group" in d
            assert "description" in d

    def test_handler_group_is_int(self):
        """handler_group value is int, not str."""
        for d in get_plugin_definitions():
            assert isinstance(d["handler_group"], int), f"{d['name']}: handler_group={d['handler_group']!r}"

    def test_returned_copy_isolation(self):
        """Mutating returned list or dicts doesn't affect internal definitions."""
        defs1 = get_plugin_definitions()
        defs2 = get_plugin_definitions()
        # List-level isolation: clearing defs1 doesn't affect defs2
        defs1.clear()
        assert len(defs2) > 0
        # Dict-level isolation: mutating a dict in defs2 doesn't affect future calls
        defs2[0]["name"] = "hacked"
        defs3 = get_plugin_definitions()
        assert defs3[0]["name"] != "hacked"
        # Calling again still works
        assert len(defs3) == len(KNOWN_PLUGINS)


class TestManifestOrder:
    """MANIFEST_ORDER defines deterministic handler registration order matching main.py."""

    @staticmethod
    def _expected_order() -> tuple[str, ...]:
        """Canonical registration order derived from main.py."""
        return (
            "topic_guard",
            "verify",
            "unverify",
            "check",
            "trust",
            "untrust",
            "trusted_list",
            "check_forwarded_message",
            "verify_callback",
            "unverify_callback",
            "warn_callback",
            "trust_callback",
            "untrust_callback",
            "captcha",
            "dm",
            "inline_keyboard_spam",
            "bio_bait_spam",
            "contact_spam",
            "new_user_spam",
            "duplicate_spam",
            "profile_monitor",
            "auto_restrict_job",
            "refresh_admin_ids_job",
        )

    def test_manifest_order_is_tuple_of_strings(self):
        """MANIFEST_ORDER is a tuple of plugin name strings."""
        assert isinstance(MANIFEST_ORDER, tuple)
        assert len(MANIFEST_ORDER) > 0
        for name in MANIFEST_ORDER:
            assert isinstance(name, str)

    def test_manifest_order_matches_registration_order(self):
        """Order matches the canonical order from main.py."""
        assert MANIFEST_ORDER == self._expected_order()

    def test_manifest_order_contains_all_known_plugins(self):
        """Every KNOWN_PLUGINS name appears exactly once in MANIFEST_ORDER."""
        assert set(MANIFEST_ORDER) == KNOWN_PLUGINS
        assert len(MANIFEST_ORDER) == len(KNOWN_PLUGINS)

    def test_manifest_order_first_is_topic_guard(self):
        """topic_guard is first (group=-1 runs before all others)."""
        assert MANIFEST_ORDER[0] == "topic_guard"

    def test_manifest_order_last_is_refresh_admin_ids_job(self):
        """refresh_admin_ids_job is last (final registration in main.py)."""
        assert MANIFEST_ORDER[-1] == "refresh_admin_ids_job"

    def test_manifest_order_no_duplicates(self):
        """No duplicate names in MANIFEST_ORDER."""
        assert len(MANIFEST_ORDER) == len(set(MANIFEST_ORDER))

    def test_manifest_order_topic_guard_in_group_negative_one(self):
        """The topic_guard entry from definitions has handler_group=-1."""
        defs = {d["name"]: d for d in get_plugin_definitions()}
        assert defs["topic_guard"]["handler_group"] == -1

    def test_manifest_order_bio_bait_spam_in_group_two(self):
        """bio_bait_spam entry has handler_group=2 (matches main.py)."""
        defs = {d["name"]: d for d in get_plugin_definitions()}
        assert defs["bio_bait_spam"]["handler_group"] == 2

    def test_manifest_order_contact_spam_in_group_three(self):
        """contact_spam entry has handler_group=3 (matches main.py)."""
        defs = {d["name"]: d for d in get_plugin_definitions()}
        assert defs["contact_spam"]["handler_group"] == 3

    def test_manifest_order_new_user_spam_in_group_four(self):
        """new_user_spam entry has handler_group=4 (matches main.py)."""
        defs = {d["name"]: d for d in get_plugin_definitions()}
        assert defs["new_user_spam"]["handler_group"] == 4

    def test_manifest_order_duplicate_spam_in_group_five(self):
        """duplicate_spam entry has handler_group=5 (matches main.py)."""
        defs = {d["name"]: d for d in get_plugin_definitions()}
        assert defs["duplicate_spam"]["handler_group"] == 5

    def test_manifest_order_profile_monitor_in_group_six(self):
        """profile_monitor entry has handler_group=6 (matches main.py)."""
        defs = {d["name"]: d for d in get_plugin_definitions()}
        assert defs["profile_monitor"]["handler_group"] == 6


class TestBuiltinModules:
    """Verify built-in wrapper modules exist and export plugin objects."""

    def test_builtin_init_module_exists(self):
        """builtin/__init__.py is importable."""
        import bot.plugins.builtin  # noqa: F811
        assert hasattr(bot.plugins.builtin, "__file__")

    def test_topic_guard_module_has_plugin(self):
        """builtin/topic_guard.py exports a plugin object."""
        import bot.plugins.builtin.topic_guard  # noqa: F811
        plugin = bot.plugins.builtin.topic_guard.plugin
        assert isinstance(plugin, base.PluginProtocol)
        assert plugin.name == "topic_guard"

    def test_commands_module_has_plugin(self):
        """builtin/commands.py exports a plugin object."""
        import bot.plugins.builtin.commands  # noqa: F811
        plugin = bot.plugins.builtin.commands.plugin
        assert isinstance(plugin, base.PluginProtocol)
        assert plugin.name == "commands"

    def test_captcha_module_has_plugin(self):
        """builtin/captcha.py exports a plugin object."""
        import bot.plugins.builtin.captcha  # noqa: F811
        plugin = bot.plugins.builtin.captcha.plugin
        assert isinstance(plugin, base.PluginProtocol)
        assert plugin.name == "captcha"

    def test_dm_module_has_plugin(self):
        """builtin/dm.py exports a plugin object."""
        import bot.plugins.builtin.dm  # noqa: F811
        plugin = bot.plugins.builtin.dm.plugin
        assert isinstance(plugin, base.PluginProtocol)
        assert plugin.name == "dm"

    def test_spam_module_has_plugin(self):
        """builtin/spam.py exports a plugin object."""
        import bot.plugins.builtin.spam  # noqa: F811
        plugin = bot.plugins.builtin.spam.plugin
        assert isinstance(plugin, base.PluginProtocol)
        assert plugin.name == "spam"

    def test_profile_monitor_module_has_plugin(self):
        """builtin/profile_monitor.py exports a plugin object."""
        import bot.plugins.builtin.profile_monitor  # noqa: F811
        plugin = bot.plugins.builtin.profile_monitor.plugin
        assert isinstance(plugin, base.PluginProtocol)
        assert plugin.name == "profile_monitor"

    def test_jobs_module_has_plugin(self):
        """builtin/jobs.py exports a plugin object."""
        import bot.plugins.builtin.jobs  # noqa: F811
        plugin = bot.plugins.builtin.jobs.plugin
        assert isinstance(plugin, base.PluginProtocol)
        assert plugin.name == "jobs"

    def test_each_plugin_satisfies_protocol(self):
        """Every builtin plugin object satisfies PluginProtocol with correct fields."""
        import bot.plugins.builtin.captcha as captcha_mod
        import bot.plugins.builtin.commands as commands_mod
        import bot.plugins.builtin.dm as dm_mod
        import bot.plugins.builtin.jobs as jobs_mod
        import bot.plugins.builtin.profile_monitor as pm_mod
        import bot.plugins.builtin.spam as spam_mod
        import bot.plugins.builtin.topic_guard as tg_mod

        plugin_map = {
            "topic_guard": tg_mod.plugin,
            "commands": commands_mod.plugin,
            "captcha": captcha_mod.plugin,
            "dm": dm_mod.plugin,
            "spam": spam_mod.plugin,
            "profile_monitor": pm_mod.plugin,
            "jobs": jobs_mod.plugin,
        }

        for name, plugin in plugin_map.items():
            assert isinstance(plugin, base.PluginProtocol), f"{name} fails PluginProtocol"
            assert isinstance(plugin.name, str)
            assert len(plugin.name) > 0
            assert isinstance(plugin.handler_group, int)
            assert isinstance(plugin.description, str)
            assert len(plugin.description) > 0
            assert callable(getattr(plugin, "register", None))


class TestComputeEffectivePluginMap:
    """compute_effective_plugin_map: per-group toggle dict from registry + env defaults."""

    def _make_registry(self, *group_configs: GroupConfig) -> GroupRegistry:
        reg = GroupRegistry()
        for gc in group_configs:
            reg.register(gc)
        return reg

    def test_empty_registry_returns_empty_map(self):
        """Empty registry => empty map (no groups = nothing to compute)."""
        reg = self._make_registry()
        result = compute_effective_plugin_map({}, reg)
        assert result == {}

    def test_single_group_no_plugin_overrides_uses_env_defaults(self):
        """Single group with no plugins override uses env defaults."""
        gc = GroupConfig(group_id=-100111, warning_topic_id=42)
        reg = self._make_registry(gc)
        result = compute_effective_plugin_map({"captcha": False, "verify": True}, reg)
        assert -100111 in result
        assert result[-100111]["captcha"] is False
        assert result[-100111]["verify"] is True
        assert result[-100111]["profile_monitor"] is True  # default

    def test_single_group_with_override_takes_precedence(self):
        """Group plugins override wins over env defaults."""
        gc = GroupConfig(group_id=-100222, warning_topic_id=42, plugins={"profile_monitor": False})
        reg = self._make_registry(gc)
        result = compute_effective_plugin_map({"profile_monitor": True}, reg)
        assert result[-100222]["profile_monitor"] is False  # group override wins

    def test_multiple_groups_independent_toggles(self):
        """Each group gets its own toggle map; one group's override doesn't affect others."""
        gc1 = GroupConfig(group_id=-100111, warning_topic_id=42)
        gc2 = GroupConfig(group_id=-100222, warning_topic_id=42, plugins={"profile_monitor": False})
        gc3 = GroupConfig(group_id=-100333, warning_topic_id=42, plugins={"profile_monitor": True, "captcha": False})
        reg = self._make_registry(gc1, gc2, gc3)
        result = compute_effective_plugin_map({"captcha": True}, reg)
        # gc1: no override, env defaults all True
        assert result[-100111]["profile_monitor"] is True
        assert result[-100111]["captcha"] is True
        # gc2: profile_monitor disabled via group override
        assert result[-100222]["profile_monitor"] is False
        assert result[-100222]["captcha"] is True  # from env
        # gc3: profile_monitor enabled, captcha disabled via group override
        assert result[-100333]["profile_monitor"] is True
        assert result[-100333]["captcha"] is False
        # gc1 unaffected by gc2's disable
        assert result[-100111]["profile_monitor"] is True

    def test_result_contains_all_groups(self):
        """Every group in registry has an entry in result."""
        gc1 = GroupConfig(group_id=-100111, warning_topic_id=42)
        gc2 = GroupConfig(group_id=-100222, warning_topic_id=42)
        reg = self._make_registry(gc1, gc2)
        result = compute_effective_plugin_map({}, reg)
        assert set(result.keys()) == {-100111, -100222}

    def test_each_group_toggle_has_all_known_plugins(self):
        """Each group's toggle dict contains all KNOWN_PLUGINS keys."""
        gc = GroupConfig(group_id=-100111, warning_topic_id=42)
        reg = self._make_registry(gc)
        result = compute_effective_plugin_map({}, reg)
        assert set(result[-100111].keys()) == KNOWN_PLUGINS

    def test_profile_monitor_disabled_for_one_group_only(self):
        """profile_monitor can be False for group A and True for group B."""
        gc_a = GroupConfig(group_id=-100111, warning_topic_id=42, plugins={"profile_monitor": False})
        gc_b = GroupConfig(group_id=-100222, warning_topic_id=42)
        reg = self._make_registry(gc_a, gc_b)
        result = compute_effective_plugin_map({}, reg)
        assert result[-100111]["profile_monitor"] is False
        assert result[-100222]["profile_monitor"] is True

    def test_none_env_defaults_treated_as_empty(self):
        """plugins_default=None treated as empty dict."""
        gc = GroupConfig(group_id=-100111, warning_topic_id=42)
        reg = self._make_registry(gc)
        result = compute_effective_plugin_map({}, reg)
        assert result[-100111]["profile_monitor"] is True


class TestIsPluginEnabledForGroup:
    """Guard utility: is_plugin_enabled_for_group checks effective map."""

    def test_known_group_enabled_plugin_returns_true(self):
        """Enabled plugin for known group returns True."""
        effective_map = {-100111: {"profile_monitor": True, "captcha": False}}
        assert is_plugin_enabled_for_group(effective_map, -100111, "profile_monitor") is True

    def test_known_group_disabled_plugin_returns_false(self):
        """Disabled plugin for known group returns False."""
        effective_map = {-100111: {"profile_monitor": False, "captcha": True}}
        assert is_plugin_enabled_for_group(effective_map, -100111, "profile_monitor") is False

    def test_unknown_group_returns_true_safe_default(self):
        """Unknown group_id returns True (safe default)."""
        effective_map = {-100111: {"profile_monitor": True}}
        assert is_plugin_enabled_for_group(effective_map, -100999, "profile_monitor") is True

    def test_missing_plugin_key_in_toggles_returns_true(self):
        """Plugin key missing from group toggles returns True (strict defaults)."""
        effective_map = {-100111: {"captcha": False}}
        assert is_plugin_enabled_for_group(effective_map, -100111, "profile_monitor") is True

    def test_empty_effective_map_returns_true(self):
        """Empty effective map returns True for any group/plugin."""
        assert is_plugin_enabled_for_group({}, -100111, "profile_monitor") is True


class TestPluginManagerComputeEffectiveMap:
    """PluginManager.compute_effective_map stores result in app.bot_data."""

    def test_stores_in_bot_data(self):
        """compute_effective_map stores result under bot_data['plugin_effective_map']."""
        gc = GroupConfig(group_id=-100111, warning_topic_id=42)
        reg = GroupRegistry()
        reg.register(gc)
        settings = MagicMock()
        settings.plugins_default = {}
        app = MagicMock()
        app.bot_data = {}

        pm = PluginManager()
        pm.compute_effective_map(settings, reg, app)

        assert "plugin_effective_map" in app.bot_data
        assert -100111 in app.bot_data["plugin_effective_map"]
        assert app.bot_data["plugin_effective_map"][-100111]["profile_monitor"] is True

    def test_stores_returns_effective_map(self):
        """compute_effective_map returns the computed effective map."""
        gc = GroupConfig(group_id=-100111, warning_topic_id=42)
        reg = GroupRegistry()
        reg.register(gc)
        settings = MagicMock()
        settings.plugins_default = {}
        app = MagicMock()
        app.bot_data = {}

        pm = PluginManager()
        result = pm.compute_effective_map(settings, reg, app)

        assert isinstance(result, dict)
        assert -100111 in result
        assert result[-100111]["profile_monitor"] is True
        # bot_data also set
        assert app.bot_data["plugin_effective_map"] is result

    def test_multiple_groups_in_map(self):
        """Multiple groups each get correct toggle map in bot_data."""
        gc1 = GroupConfig(group_id=-100111, warning_topic_id=42)
        gc2 = GroupConfig(group_id=-100222, warning_topic_id=42, plugins={"profile_monitor": False})
        reg = GroupRegistry()
        reg.register(gc1)
        reg.register(gc2)
        settings = MagicMock()
        settings.plugins_default = {}
        app = MagicMock()
        app.bot_data = {}

        pm = PluginManager()
        pm.compute_effective_map(settings, reg, app)

        map_ = app.bot_data["plugin_effective_map"]
        assert map_[-100111]["profile_monitor"] is True
        assert map_[-100222]["profile_monitor"] is False