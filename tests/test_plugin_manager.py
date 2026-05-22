"""Tests for plugin toggle resolver, plugin contracts, definitions, and built-in wrappers."""

from bot.group_config import KNOWN_PLUGINS
from bot.plugins import base
from bot.plugins.config import is_plugin_enabled, resolve_plugin_toggles
from bot.plugins.definitions import MANIFEST_ORDER, get_plugin_definitions


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