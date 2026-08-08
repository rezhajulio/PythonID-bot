"""Tests for plugin toggle resolver, plugin contracts, definitions, and built-in wrappers."""

from unittest.mock import AsyncMock, MagicMock

from bot.group_config import GroupConfig, GroupRegistry
import pytest

from bot.plugins.config import guard_plugin, is_plugin_enabled_for_group, resolve_plugin_toggles
from bot.plugins.definitions import MANIFEST_ORDER, PLUGIN_NAMES as KNOWN_PLUGINS, get_plugin_definitions
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

class TestPluginDefinitions:
    """Verify plugin definitions match KNOWN_PLUGINS and have correct types."""

    def test_plugin_names_exists(self):
        """PLUGIN_NAMES is exported from definitions module."""
        from bot.plugins.definitions import PLUGIN_NAMES
        assert isinstance(PLUGIN_NAMES, frozenset)
        assert "topic_guard" in PLUGIN_NAMES

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

    def test_handler_group_is_int_or_float(self):
        """handler_group value is int or float, not str."""
        for d in get_plugin_definitions():
            assert isinstance(d["handler_group"], (int, float)), f"{d['name']}: handler_group={d['handler_group']!r}"

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
    def test_verify_callback_description(self):
        """verify_callback description says 'Admin verify confirm button callback' not 'Captcha verify'."""
        defs = get_plugin_definitions()
        defs_by_name = {d["name"]: d for d in defs}
        assert defs_by_name["verify_callback"]["description"] == "Admin verify (photo exemption) button callback"

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
            "check_group_callback",
            "verify_callback",
            "unverify_callback",
            "warn_callback",
            "trust_callback",
            "untrust_callback",
            "unrestrict_callback",
            "warn_command",
            "captcha",
            "dm",
            "status",
            "guest_bot_block",
            "inline_keyboard_spam",
            "contact_spam",
            "new_user_spam",
            "duplicate_spam",
            "bio_bait_spam",
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

    def test_manifest_order_bio_bait_spam_in_group_four(self):
        """bio_bait_spam entry has handler_group=4 (runs before profile_monitor)."""
        defs = {d["name"]: d for d in get_plugin_definitions()}
        assert defs["bio_bait_spam"]["handler_group"] == 4

    def test_manifest_order_contact_spam_in_group_two(self):
        """contact_spam entry has handler_group=2 (matches pre-refactor main.py)."""
        defs = {d["name"]: d for d in get_plugin_definitions()}
        assert defs["contact_spam"]["handler_group"] == 2

    def test_manifest_order_new_user_spam_in_group_three(self):
        """new_user_spam entry has handler_group=3 (matches pre-refactor main.py)."""
        defs = {d["name"]: d for d in get_plugin_definitions()}
        assert defs["new_user_spam"]["handler_group"] == 3

    def test_manifest_order_duplicate_spam_in_group_four(self):
        """duplicate_spam entry has handler_group=4 (matches pre-refactor main.py)."""
        defs = {d["name"]: d for d in get_plugin_definitions()}
        assert defs["duplicate_spam"]["handler_group"] == 4

    def test_manifest_order_profile_monitor_in_group_five(self):
        """profile_monitor entry has handler_group=5 (matches pre-refactor main.py)."""
        defs = {d["name"]: d for d in get_plugin_definitions()}
        assert defs["profile_monitor"]["handler_group"] == 5

class TestManifestOrderConsistency:
    """MANIFEST_ORDER must be sorted by handler_group."""

    def test_manifest_order_sorted_by_handler_group(self):
        """Entries in MANIFEST_ORDER appear in non-decreasing handler_group order."""
        defs = {d["name"]: d for d in get_plugin_definitions()}
        groups = [defs[name]["handler_group"] for name in MANIFEST_ORDER]
        assert groups == sorted(groups), (
            f"MANIFEST_ORDER not sorted by handler_group: "
            f"{list(zip(MANIFEST_ORDER, groups))}"
        )

class TestBuiltinModules:
    """Verify built-in wrapper modules exist."""

    def test_builtin_init_module_exists(self):
        """builtin/__init__.py is importable."""
        import bot.plugins.builtin  # noqa: F811
        assert hasattr(bot.plugins.builtin, "__file__")

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
        """Plugin key missing from group toggles returns True (fail-open defaults)."""
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

class TestGuardPlugin:
    """guard_plugin decorator: gated runtime enable/disable per group."""

    @staticmethod
    def _make_mock_update(chat_id: int, chat_type: str = "supergroup") -> MagicMock:
        """Create a mock update with effective_chat."""
        update = MagicMock()
        chat = MagicMock()
        chat.id = chat_id
        chat.type = chat_type
        update.effective_chat = chat
        return update

    @staticmethod
    def _make_mock_context(effective_map: dict | None = None) -> MagicMock:
        """Create a mock context with bot_data."""
        context = MagicMock()
        context.bot_data = {}
        if effective_map is not None:
            context.bot_data["plugin_effective_map"] = effective_map
        return context

    async def test_enabled_plugin_calls_callback(self):
        """Enabled plugin for group -> callback called normally."""
        callback = AsyncMock()
        wrapped = guard_plugin("profile_monitor")(callback)

        update = self._make_mock_update(-100111)
        context = self._make_mock_context({-100111: {"profile_monitor": True}})

        await wrapped(update, context)

        callback.assert_awaited_once_with(update, context)

    async def test_disabled_plugin_skips_callback(self):
        """Disabled plugin for group -> callback NOT called."""
        callback = AsyncMock()
        wrapped = guard_plugin("profile_monitor")(callback)

        update = self._make_mock_update(-100111)
        context = self._make_mock_context({-100111: {"profile_monitor": False}})

        await wrapped(update, context)

        callback.assert_not_awaited()

    async def test_unknown_group_passes_through(self):
        """Unknown group_id -> safe default True -> callback called."""
        callback = AsyncMock()
        wrapped = guard_plugin("profile_monitor")(callback)

        update = self._make_mock_update(-100999)
        context = self._make_mock_context({-100111: {"profile_monitor": False}})

        await wrapped(update, context)

        callback.assert_awaited_once_with(update, context)

    async def test_empty_effective_map_passes_through(self):
        """Empty effective_map -> safe defaults -> callback called."""
        callback = AsyncMock()
        wrapped = guard_plugin("profile_monitor")(callback)

        update = self._make_mock_update(-100111)
        context = self._make_mock_context({})

        await wrapped(update, context)

        callback.assert_awaited_once_with(update, context)

    async def test_missing_effective_map_passes_through(self):
        """bot_data missing plugin_effective_map -> callback called."""
        callback = AsyncMock()
        wrapped = guard_plugin("profile_monitor")(callback)

        update = self._make_mock_update(-100111)
        context = MagicMock()
        context.bot_data = {}

        await wrapped(update, context)

        callback.assert_awaited_once_with(update, context)

    async def test_private_chat_passes_through(self):
        """Private chat -> bypass gating -> callback called."""
        callback = AsyncMock()
        wrapped = guard_plugin("profile_monitor")(callback)

        update = self._make_mock_update(12345, chat_type="private")
        context = self._make_mock_context({-100111: {"profile_monitor": False}})

        await wrapped(update, context)

        callback.assert_awaited_once_with(update, context)

    async def test_no_effective_chat_passes_through(self):
        """No effective_chat in update -> bypass gating -> callback called."""
        callback = AsyncMock()
        wrapped = guard_plugin("profile_monitor")(callback)

        update = MagicMock()
        update.effective_chat = None
        context = self._make_mock_context({-100111: {"profile_monitor": False}})

        await wrapped(update, context)

        callback.assert_awaited_once_with(update, context)

    async def test_group_a_disabled_group_b_enabled(self):
        """Group A disabled -> no-op. Group B enabled -> callback called."""
        callback_a = AsyncMock()
        callback_b = AsyncMock()
        wrapped_a = guard_plugin("profile_monitor")(callback_a)
        wrapped_b = guard_plugin("profile_monitor")(callback_b)

        effective_map = {-100111: {"profile_monitor": False}, -100222: {"profile_monitor": True}}

        # Group A: disabled
        update_a = self._make_mock_update(-100111)
        context_a = self._make_mock_context(effective_map)
        await wrapped_a(update_a, context_a)
        callback_a.assert_not_awaited()

        # Group B: enabled
        update_b = self._make_mock_update(-100222)
        context_b = self._make_mock_context(effective_map)
        await wrapped_b(update_b, context_b)
        callback_b.assert_awaited_once_with(update_b, context_b)

    async def test_topic_guard_enabled_calls_callback(self):
        """topic_guard plugin enabled -> topic_guard callback called."""
        callback = AsyncMock()
        wrapped = guard_plugin("topic_guard")(callback)

        update = self._make_mock_update(-100111)
        context = self._make_mock_context({-100111: {"topic_guard": True}})

        await wrapped(update, context)

        callback.assert_awaited_once_with(update, context)

    async def test_topic_guard_disabled_skips_callback(self):
        """topic_guard plugin disabled -> topic_guard callback NOT called."""
        callback = AsyncMock()
        wrapped = guard_plugin("topic_guard")(callback)

        update = self._make_mock_update(-100111)
        context = self._make_mock_context({-100111: {"topic_guard": False}})

        await wrapped(update, context)

        callback.assert_not_awaited()

    async def test_inline_keyboard_spam_disabled_skips_callback(self):
        """inline_keyboard_spam disabled -> callback NOT called."""
        callback = AsyncMock()
        wrapped = guard_plugin("inline_keyboard_spam")(callback)

        update = self._make_mock_update(-100111)
        context = self._make_mock_context({-100111: {"inline_keyboard_spam": False}})

        await wrapped(update, context)

        callback.assert_not_awaited()

    async def test_guard_plugin_import_exported(self):
        """guard_plugin is importable from bot.plugins.config."""
        assert callable(guard_plugin)

    async def test_no_effective_map_key_all_true(self):
        """Toggle absent in effective_map -> safe default True."""
        callback = AsyncMock()
        wrapped = guard_plugin("some_unknown_plugin")(callback)

        update = self._make_mock_update(-100111)
        context = self._make_mock_context({-100111: {"profile_monitor": True}})

        await wrapped(update, context)

        callback.assert_awaited_once_with(update, context)

    async def test_decorated_function_name_preserved(self):
        """guard_plugin preserves __name__ and __wrapped__ of original callback."""
        async def my_handler(update, context):
            pass

        wrapped = guard_plugin("profile_monitor")(my_handler)

        assert wrapped.__name__ == "my_handler"
        assert wrapped.__wrapped__ is my_handler

    async def test_channel_chat_passes_through(self):
        """Channel chat -> bypass gating -> callback called."""
        callback = AsyncMock()
        wrapped = guard_plugin("profile_monitor")(callback)

        update = self._make_mock_update(-100111, chat_type="channel")
        context = self._make_mock_context({-100111: {"profile_monitor": False}})

        await wrapped(update, context)

        callback.assert_awaited_once_with(update, context)

    async def test_args_and_kwargs_forwarded_to_callback(self):
        """Extra args/kwargs are forwarded to the underlying callback."""
        callback = AsyncMock()
        wrapped = guard_plugin("profile_monitor")(callback)

        update = self._make_mock_update(-100111)
        context = self._make_mock_context({-100111: {"profile_monitor": True}})

        await wrapped(update, context, "extra_arg", key="value")

        callback.assert_awaited_once_with(update, context, "extra_arg", key="value")

class TestPluginInitExports:
    """Verify bot.plugins.__init__ exports the full public API."""

    def test_is_plugin_enabled_for_group_exported(self):
        """is_plugin_enabled_for_group is exported from bot.plugins."""
        from bot.plugins import is_plugin_enabled_for_group
        assert callable(is_plugin_enabled_for_group)

    def test_compute_effective_plugin_map_exported(self):
        """compute_effective_plugin_map is exported from bot.plugins."""
        from bot.plugins import compute_effective_plugin_map
        assert callable(compute_effective_plugin_map)

    def test_all_includes_new_exports(self):
        """__all__ includes is_plugin_enabled_for_group and compute_effective_plugin_map."""
        import bot.plugins
        assert "is_plugin_enabled_for_group" in bot.plugins.__all__
        assert "compute_effective_plugin_map" in bot.plugins.__all__

class TestComputeEffectivePluginMapEdgeCases:
    """Edge cases for compute_effective_plugin_map."""

    def test_non_group_registry_returns_empty_map(self):
        """Non-GroupRegistry input returns empty dict."""
        result = compute_effective_plugin_map({}, "not_a_registry")
        assert result == {}

    def test_none_registry_returns_empty_map(self):
        """None input returns empty dict."""
        result = compute_effective_plugin_map({}, None)
        assert result == {}

    def test_list_registry_returns_empty_map(self):
        """List input returns empty dict."""
        result = compute_effective_plugin_map({}, [1, 2, 3])
        assert result == {}

class TestHandlerGroupsMatchPreRefactor:
    """Each pre-refactor handler group must match original main.py values.

    Pre-refactor groups (from main branch):
    - topic_guard: -1
    - commands, captcha, dm: 0
    - inline_keyboard_spam: 1
    - contact_spam: 2
    - new_user_spam: 3
    - duplicate_spam: 4
    - profile_monitor: 5
    """

    def test_topic_guard_group_negative_one(self):
        """topic_guard must be in group -1."""
        defs = get_plugin_definitions()
        defs_by_name = {d["name"]: d for d in defs}
        assert defs_by_name["topic_guard"]["handler_group"] == -1

    def test_commands_group_zero(self):
        """All command/callback plugins must be in group 0."""
        command_plugins = [
            "verify", "unverify", "check", "trust", "untrust",
            "trusted_list", "check_forwarded_message",
            "verify_callback", "unverify_callback", "warn_callback",
            "trust_callback", "untrust_callback",
        ]
        defs = get_plugin_definitions()
        defs_by_name = {d["name"]: d for d in defs}
        for name in command_plugins:
            assert defs_by_name[name]["handler_group"] == 0, f"{name} not in group 0"

    def test_captcha_group_zero(self):
        """captcha must be in group 0."""
        defs = get_plugin_definitions()
        defs_by_name = {d["name"]: d for d in defs}
        assert defs_by_name["captcha"]["handler_group"] == 0

    def test_dm_group_zero(self):
        """dm must be in group 0."""
        defs = get_plugin_definitions()
        defs_by_name = {d["name"]: d for d in defs}
        assert defs_by_name["dm"]["handler_group"] == 0

    def test_inline_keyboard_spam_group_one(self):
        """inline_keyboard_spam must be in group 1."""
        defs = get_plugin_definitions()
        defs_by_name = {d["name"]: d for d in defs}
        assert defs_by_name["inline_keyboard_spam"]["handler_group"] == 1

    def test_contact_spam_group_two(self):
        """contact_spam must be in group 2 (was shifted to 3)."""
        defs = get_plugin_definitions()
        defs_by_name = {d["name"]: d for d in defs}
        assert defs_by_name["contact_spam"]["handler_group"] == 2

    def test_new_user_spam_group_three(self):
        """new_user_spam must be in group 3 (was shifted to 4)."""
        defs = get_plugin_definitions()
        defs_by_name = {d["name"]: d for d in defs}
        assert defs_by_name["new_user_spam"]["handler_group"] == 3

    def test_duplicate_spam_group_four(self):
        """duplicate_spam must be in group 4 (was shifted to 5)."""
        defs = get_plugin_definitions()
        defs_by_name = {d["name"]: d for d in defs}
        assert defs_by_name["duplicate_spam"]["handler_group"] == 4

    def test_profile_monitor_group_five(self):
        """profile_monitor must be in group 5 (was shifted to 6)."""
        defs = get_plugin_definitions()
        defs_by_name = {d["name"]: d for d in defs}
        assert defs_by_name["profile_monitor"]["handler_group"] == 5

    def test_bio_bait_spam_not_in_group_two(self):
        """bio_bait_spam must NOT use group 2 (that was contact_spam's original group)."""
        defs = get_plugin_definitions()
        defs_by_name = {d["name"]: d for d in defs}
        assert defs_by_name["bio_bait_spam"]["handler_group"] != 2

    def test_bio_bait_spam_group_less_than_profile_monitor(self):
        """bio_bait_spam must run before profile_monitor (group < 5)."""
        defs = get_plugin_definitions()
        defs_by_name = {d["name"]: d for d in defs}
        assert defs_by_name["bio_bait_spam"]["handler_group"] < defs_by_name["profile_monitor"]["handler_group"], \
            f"bio_bait_spam (group={defs_by_name['bio_bait_spam']['handler_group']}) must be < profile_monitor (group=5)"

class TestRegisterAllErrorHandling:
    """register_all must handle registrar failures gracefully."""

    def test_register_all_propagates_registrar_exception(self):
        """If a registrar raises, the exception propagates to caller."""
        from bot.plugins.manager import PluginManager

        app = MagicMock()
        app.bot_data = {}

        pm = PluginManager()

        def failing_registrar(application):
            raise RuntimeError("captcha registrar failed")
        pm._registry["captcha"] = failing_registrar

        with pytest.raises(RuntimeError, match="captcha registrar failed"):
            pm.register_all(app)
