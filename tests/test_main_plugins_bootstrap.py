"""Tests for main.py using PluginManager for handler+job registration.

Verifies that:
1. PluginManager maps every MANIFEST_ORDER name to a registrar callable.
2. register_all() registers handlers in MANIFEST_ORDER.
3. Plugin metadata is stored in bot_data.
4. main() uses PluginManager.register_all instead of manual registration wall.
"""

import sys
from unittest.mock import MagicMock, patch

import bot.plugins.manager as pm_module
from bot.plugins.definitions import MANIFEST_ORDER


class TestPluginManagerRegistry:
    """PluginManager must map every MANIFEST_ORDER name to a registrar."""

    def test_manager_importable(self):
        """PluginManager class is importable from bot.plugins.manager."""
        from bot.plugins.manager import PluginManager
        assert PluginManager is not None

    def test_manager_has_register_all_method(self):
        """PluginManager.register_all exists and is callable."""
        from bot.plugins.manager import PluginManager
        pm = PluginManager()
        assert hasattr(pm, "register_all")
        assert callable(pm.register_all)

    def test_manager_builds_registry_with_all_manifest_names(self):
        """PluginManager._registry has all MANIFEST_ORDER names."""
        from bot.plugins.manager import PluginManager
        pm = PluginManager()
        for name in MANIFEST_ORDER:
            assert name in pm._registry, f"Missing registrar for {name}"

    def test_each_registrar_is_callable(self):
        """Each entry in registry is a callable."""
        from bot.plugins.manager import PluginManager
        pm = PluginManager()
        for name in MANIFEST_ORDER:
            assert callable(pm._registry[name]), f"{name} registrar not callable"

    def test_registry_size_matches_manifest(self):
        """Registry size equals MANIFEST_ORDER length."""
        from bot.plugins.manager import PluginManager
        pm = PluginManager()
        assert len(pm._registry) == len(MANIFEST_ORDER)


class TestRegisterAll:
    """PluginManager.register_all registers handlers in MANIFEST_ORDER."""

    def test_register_all_calls_each_registrar(self):
        """register_all calls every registrar exactly once."""
        from bot.plugins.manager import PluginManager

        app = MagicMock()
        app.bot_data = {}
        job_queue = MagicMock()
        job_queue.run_repeating = MagicMock()
        app.job_queue = job_queue
        app.add_handler = MagicMock()

        pm = PluginManager()
        for name in MANIFEST_ORDER:
            original = pm._registry[name]
            wrapped = MagicMock(wraps=original)
            pm._registry[name] = wrapped

        result = pm.register_all(app)

        for name in MANIFEST_ORDER:
            pm._registry[name].assert_called_once_with(app)

        assert set(result.keys()) == set(MANIFEST_ORDER)

    def test_register_all_returns_handler_lists(self):
        """register_all returns dict mapping name to list of handlers."""
        from bot.plugins.manager import PluginManager

        app = MagicMock()
        app.bot_data = {}
        job_queue = MagicMock()
        job_queue.run_repeating = MagicMock()
        app.job_data = {}
        app.job_queue = job_queue
        app.add_handler = MagicMock()

        pm = PluginManager()
        result = pm.register_all(app)

        for name in MANIFEST_ORDER:
            assert isinstance(result[name], list)

    def test_register_all_stores_metadata_in_bot_data(self):
        """register_all stores registration results in bot_data['plugin_handlers']."""
        from bot.plugins.manager import PluginManager

        app = MagicMock()
        app.bot_data = {}
        job_queue = MagicMock()
        job_queue.run_repeating = MagicMock()
        app.job_data = {}
        app.job_queue = job_queue
        app.add_handler = MagicMock()

        pm = PluginManager()
        pm.register_all(app)

        assert "plugin_handlers" in app.bot_data
        metadata = app.bot_data["plugin_handlers"]
        assert set(metadata.keys()) == set(MANIFEST_ORDER)

    def test_register_all_stores_metadata_with_handler_group(self):
        """bot_data['plugin_handlers'][name] includes handler_group."""
        from bot.plugins.definitions import get_plugin_definitions
        from bot.plugins.manager import PluginManager

        defs_by_name = {d["name"]: d for d in get_plugin_definitions()}

        app = MagicMock()
        app.bot_data = {}
        job_queue = MagicMock()
        job_queue.run_repeating = MagicMock()
        app.job_data = {}
        app.job_queue = job_queue
        app.add_handler = MagicMock()

        pm = PluginManager()
        pm.register_all(app)

        for name in MANIFEST_ORDER:
            assert app.bot_data["plugin_handlers"][name]["handler_group"] == defs_by_name[name]["handler_group"]

    def test_register_all_stores_handlers_in_metadata(self):
        """bot_data['plugin_handlers'][name] includes handlers list."""
        from bot.plugins.manager import PluginManager

        app = MagicMock()
        app.bot_data = {}
        job_queue = MagicMock()
        job_queue.run_repeating = MagicMock()
        app.job_data = {}
        app.job_queue = job_queue
        app.add_handler = MagicMock()

        pm = PluginManager()
        result = pm.register_all(app)

        for name in MANIFEST_ORDER:
            assert app.bot_data["plugin_handlers"][name]["handlers"] == result[name]


class TestMainUsesPluginManager:
    """main() must use PluginManager.register_all instead of manual registration."""

    def test_main_calls_register_all(self):
        """main() calls PluginManager.register_all."""
        # Remove from cache to force fresh import inside patch context
        sys.modules.pop("bot.main", None)

        with patch.object(pm_module, "PluginManager") as mock_plugin_cls:
            mock_pm = MagicMock()
            mock_pm.register_all.return_value = {}
            mock_plugin_cls.return_value = mock_pm

            with patch("bot.main.configure_logging"):
                with patch("bot.main.init_group_registry") as mock_init_reg:
                    mock_reg = MagicMock()
                    mock_reg.all_groups.return_value = []
                    mock_init_reg.return_value = mock_reg
                    with patch("bot.main.init_database"):
                        with patch("bot.main.Application") as mock_app_cls:
                            mock_app = MagicMock()
                            mock_app.bot_data = {}
                            mock_app_cls.builder.return_value.token.return_value.post_init.return_value.build.return_value = mock_app
    
                            class FakeSettings:
                                logfire_environment = "test"
                                database_path = ":memory:"
                                telegram_bot_token = "test"
                                groups_config_path = "nonexistent.json"
                                group_id = -100999
                                warning_topic_id = 42
                                restrict_failed_users = True
                                warning_threshold = 3
                                warning_time_threshold_minutes = 10080
                                captcha_enabled = False
                                captcha_timeout_seconds = 120
                                new_user_probation_hours = 48
                                new_user_violation_threshold = 3
                                rules_link = "https://t.me/rules"
                                contact_spam_restrict = False
                                duplicate_spam_enabled = False
                                duplicate_spam_window_seconds = 30
                                duplicate_spam_threshold = 3
                                duplicate_spam_min_length = 10
                                duplicate_spam_similarity = 0.8
                                bio_bait_enabled = True
                                bio_bait_monitor_only = False
                                bio_bait_alert_chat_id = None
                                plugins_default = {}
                                log_level = "INFO"
                                logfire_enabled = False
                                logfire_token = None
                                logfire_service_name = "pythonid-bot"
    
                            with patch("bot.main.get_settings", return_value=FakeSettings()):
                                from bot.main import main
                                main()
    
                                mock_pm.register_all.assert_called_once()
                    mock_init_reg.assert_called_once()


class TestRefactoredBuiltinModules:
    """Builtin modules expose individual registrar functions for each manifest name."""

    def test_commands_has_verify_registrar(self):
        """bot.plugins.builtin.commands has register_verify function."""
        from bot.plugins.builtin import commands
        assert hasattr(commands, "register_verify")
        assert callable(commands.register_verify)

    def test_commands_has_unverify_registrar(self):
        """bot.plugins.builtin.commands has register_unverify function."""
        from bot.plugins.builtin import commands
        assert hasattr(commands, "register_unverify")
        assert callable(commands.register_unverify)

    def test_commands_has_check_registrar(self):
        """bot.plugins.builtin.commands has register_check function."""
        from bot.plugins.builtin import commands
        assert hasattr(commands, "register_check")
        assert callable(commands.register_check)

    def test_commands_has_trust_registrar(self):
        """bot.plugins.builtin.commands has register_trust function."""
        from bot.plugins.builtin import commands
        assert hasattr(commands, "register_trust")
        assert callable(commands.register_trust)

    def test_commands_has_untrust_registrar(self):
        """bot.plugins.builtin.commands has register_untrust function."""
        from bot.plugins.builtin import commands
        assert hasattr(commands, "register_untrust")
        assert callable(commands.register_untrust)

    def test_commands_has_trusted_list_registrar(self):
        """bot.plugins.builtin.commands has register_trusted_list function."""
        from bot.plugins.builtin import commands
        assert hasattr(commands, "register_trusted_list")
        assert callable(commands.register_trusted_list)

    def test_commands_has_check_forwarded_message_registrar(self):
        """bot.plugins.builtin.commands has register_check_forwarded_message function."""
        from bot.plugins.builtin import commands
        assert hasattr(commands, "register_check_forwarded_message")
        assert callable(commands.register_check_forwarded_message)

    def test_commands_has_verify_callback_registrar(self):
        """bot.plugins.builtin.commands has register_verify_callback function."""
        from bot.plugins.builtin import commands
        assert hasattr(commands, "register_verify_callback")
        assert callable(commands.register_verify_callback)

    def test_commands_has_unverify_callback_registrar(self):
        """bot.plugins.builtin.commands has register_unverify_callback function."""
        from bot.plugins.builtin import commands
        assert hasattr(commands, "register_unverify_callback")
        assert callable(commands.register_unverify_callback)

    def test_commands_has_warn_callback_registrar(self):
        """bot.plugins.builtin.commands has register_warn_callback function."""
        from bot.plugins.builtin import commands
        assert hasattr(commands, "register_warn_callback")
        assert callable(commands.register_warn_callback)

    def test_commands_has_trust_callback_registrar(self):
        """bot.plugins.builtin.commands has register_trust_callback function."""
        from bot.plugins.builtin import commands
        assert hasattr(commands, "register_trust_callback")
        assert callable(commands.register_trust_callback)

    def test_commands_has_untrust_callback_registrar(self):
        """bot.plugins.builtin.commands has register_untrust_callback function."""
        from bot.plugins.builtin import commands
        assert hasattr(commands, "register_untrust_callback")
        assert callable(commands.register_untrust_callback)

    def test_spam_has_inline_keyboard_spam_registrar(self):
        """bot.plugins.builtin.spam has register_inline_keyboard_spam function."""
        from bot.plugins.builtin import spam
        assert hasattr(spam, "register_inline_keyboard_spam")
        assert callable(spam.register_inline_keyboard_spam)

    def test_spam_has_bio_bait_spam_registrar(self):
        """bot.plugins.builtin.spam has register_bio_bait_spam function."""
        from bot.plugins.builtin import spam
        assert hasattr(spam, "register_bio_bait_spam")
        assert callable(spam.register_bio_bait_spam)

    def test_spam_has_contact_spam_registrar(self):
        """bot.plugins.builtin.spam has register_contact_spam function."""
        from bot.plugins.builtin import spam
        assert hasattr(spam, "register_contact_spam")
        assert callable(spam.register_contact_spam)

    def test_spam_has_new_user_spam_registrar(self):
        """bot.plugins.builtin.spam has register_new_user_spam function."""
        from bot.plugins.builtin import spam
        assert hasattr(spam, "register_new_user_spam")
        assert callable(spam.register_new_user_spam)

    def test_spam_has_duplicate_spam_registrar(self):
        """bot.plugins.builtin.spam has register_duplicate_spam function."""
        from bot.plugins.builtin import spam
        assert hasattr(spam, "register_duplicate_spam")
        assert callable(spam.register_duplicate_spam)

    def test_captcha_has_registrar(self):
        """bot.plugins.builtin.captcha has register_captcha function."""
        from bot.plugins.builtin import captcha as captcha_mod
        assert hasattr(captcha_mod, "register_captcha")
        assert callable(captcha_mod.register_captcha)

    def test_dm_has_registrar(self):
        """bot.plugins.builtin.dm has register_dm function."""
        from bot.plugins.builtin import dm as dm_mod
        assert hasattr(dm_mod, "register_dm")
        assert callable(dm_mod.register_dm)

    def test_profile_monitor_has_registrar(self):
        """bot.plugins.builtin.profile_monitor has register_profile_monitor function."""
        from bot.plugins.builtin import profile_monitor as pm_mod
        assert hasattr(pm_mod, "register_profile_monitor")
        assert callable(pm_mod.register_profile_monitor)

    def test_jobs_has_auto_restrict_registrar(self):
        """bot.plugins.builtin.jobs has register_auto_restrict_job function."""
        from bot.plugins.builtin import jobs as jobs_mod
        assert hasattr(jobs_mod, "register_auto_restrict_job")
        assert callable(jobs_mod.register_auto_restrict_job)

    def test_jobs_has_refresh_admin_ids_registrar(self):
        """bot.plugins.builtin.jobs has register_refresh_admin_ids_job function."""
        from bot.plugins.builtin import jobs as jobs_mod
        assert hasattr(jobs_mod, "register_refresh_admin_ids_job")
        assert callable(jobs_mod.register_refresh_admin_ids_job)

    def test_topic_guard_has_registrar(self):
        """bot.plugins.builtin.topic_guard has register_topic_guard function."""
        from bot.plugins.builtin import topic_guard as tg_mod
        assert hasattr(tg_mod, "register_topic_guard")
        assert callable(tg_mod.register_topic_guard)


class TestIndividualRegistrars:
    """Individual registrar functions correctly register their handlers."""

    def test_verify_registrar_adds_handler(self):
        """register_verify adds a CommandHandler to the app."""
        from bot.plugins.builtin.commands import register_verify

        app = MagicMock()
        app.bot_data = {}
        app.add_handler = MagicMock()
        handlers = register_verify(app)
        assert len(handlers) >= 1
        app.add_handler.assert_called()

    def test_topic_guard_registrar_adds_handler(self):
        """register_topic_guard adds handler to group=-1."""
        from bot.plugins.builtin.topic_guard import register_topic_guard

        app = MagicMock()
        app.bot_data = {}
        app.add_handler = MagicMock()
        handlers = register_topic_guard(app)
        assert len(handlers) >= 1
        app.add_handler.assert_called()

    def test_captcha_registrar_adds_handlers(self):
        """register_captcha adds handlers via captcha.get_handlers()."""
        from bot.plugins.builtin.captcha import register_captcha

        app = MagicMock()
        app.bot_data = {}
        app.add_handler = MagicMock()
        handlers = register_captcha(app)
        assert len(handlers) >= 1
        app.add_handler.assert_called()

    def test_auto_restrict_job_registrar_schedules_job(self):
        """register_auto_restrict_job calls job_queue.run_repeating."""
        from bot.plugins.builtin.jobs import register_auto_restrict_job

        app = MagicMock()
        app.bot_data = {}
        job_queue = MagicMock()
        job_queue.run_repeating = MagicMock()
        app.job_queue = job_queue
        register_auto_restrict_job(app)
        app.job_queue.run_repeating.assert_called_once()

    def test_inline_keyboard_spam_registrar_adds_handler(self):
        """register_inline_keyboard_spam adds handler to group=1."""
        from bot.plugins.builtin.spam import register_inline_keyboard_spam

        app = MagicMock()
        app.bot_data = {}
        app.add_handler = MagicMock()
        handlers = register_inline_keyboard_spam(app)
        assert len(handlers) >= 1
        assert app.add_handler.call_count == 1
        call_args, call_kwargs = app.add_handler.call_args
        assert len(call_args) == 1
        assert call_kwargs["group"] == 1
        from telegram.ext import MessageHandler
        assert isinstance(call_args[0], MessageHandler)