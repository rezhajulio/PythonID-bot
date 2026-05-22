"""Plugin manager for deterministic handler/job registration.

Provides ``PluginManager`` which maps each fine-grained plugin name
(from ``MANIFEST_ORDER``) to an individual registrar callable, then
calls them in canonical order via ``register_all()``.

Usage inside ``main.py``::

    pm = PluginManager()
    plugin_handlers = pm.register_all(application)
    # plugin_handlers dict stored in application.bot_data["plugin_handlers"]
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from bot.plugins.builtin import captcha as captcha_mod
from bot.plugins.builtin import commands
from bot.plugins.builtin import dm as dm_mod
from bot.plugins.builtin import jobs as jobs_mod
from bot.plugins.builtin import profile_monitor as pm_mod
from bot.plugins.builtin import spam as spam_mod
from bot.plugins.builtin import topic_guard as tg_mod
from bot.plugins.definitions import MANIFEST_ORDER, get_plugin_definitions

if TYPE_CHECKING:
    from telegram.ext import Application, BaseHandler

logger = logging.getLogger(__name__)

# Type alias for a registrar callable.
# Accepts an Application, returns a list of registered BaseHandler instances.
# Use string forward ref because BaseHandler is only imported under TYPE_CHECKING.
Registrar = Callable[..., list["BaseHandler"]]


class PluginManager:
    """Manages deterministic handler/job registration from MANIFEST_ORDER.

    Builds an internal registry mapping each manifest-level plugin name
    to its individual registrar function. ``register_all()`` iterates
    ``MANIFEST_ORDER`` and invokes each registrar in order.

    After registration, metadata (handler group, handler instances) is
    stored in ``application.bot_data["plugin_handlers"]`` for later
    gating (e.g., Task 5 selective disable).
    """

    def __init__(self) -> None:
        # Build registry: manifest name -> registrar callable
        self._registry: dict[str, Registrar] = self._build_registry()

    @staticmethod
    def _build_registry() -> dict[str, Registrar]:
        """Return dict mapping each manifest name to its registrar.

        Each registrar is a module-level function that accepts an
        ``Application`` and returns ``list[BaseHandler]``.
        """
        return {
            # topic_guard
            "topic_guard": tg_mod.register_topic_guard,
            # commands (group=0)
            "verify": commands.register_verify,
            "unverify": commands.register_unverify,
            "check": commands.register_check,
            "trust": commands.register_trust,
            "untrust": commands.register_untrust,
            "trusted_list": commands.register_trusted_list,
            "check_forwarded_message": commands.register_check_forwarded_message,
            "verify_callback": commands.register_verify_callback,
            "unverify_callback": commands.register_unverify_callback,
            "warn_callback": commands.register_warn_callback,
            "trust_callback": commands.register_trust_callback,
            "untrust_callback": commands.register_untrust_callback,
            # captcha
            "captcha": captcha_mod.register_captcha,
            # dm
            "dm": dm_mod.register_dm,
            # spam
            "inline_keyboard_spam": spam_mod.register_inline_keyboard_spam,
            "bio_bait_spam": spam_mod.register_bio_bait_spam,
            "contact_spam": spam_mod.register_contact_spam,
            "new_user_spam": spam_mod.register_new_user_spam,
            "duplicate_spam": spam_mod.register_duplicate_spam,
            # profile_monitor
            "profile_monitor": pm_mod.register_profile_monitor,
            # jobs
            "auto_restrict_job": jobs_mod.register_auto_restrict_job,
            "refresh_admin_ids_job": jobs_mod.register_refresh_admin_ids_job,
        }

    def register_all(
        self,
        application: Application,  # type: ignore[type-arg]
    ) -> dict[str, list[BaseHandler]]:
        """Register all built-in plugins in MANIFEST_ORDER.

        Args:
            application: PTB Application instance.

        Returns:
            Dict mapping each plugin name to the list of handler instances
            returned by its registrar. Also stored in
            ``application.bot_data["plugin_handlers"]``.
        """
        result: dict[str, list[BaseHandler]] = {}
        defs_by_name = {d["name"]: d for d in get_plugin_definitions()}

        for name in MANIFEST_ORDER:
            registrar = self._registry[name]
            handlers = registrar(application)
            result[name] = handlers
            logger.info("Registered plugin: %s (group=%d, %d handler(s))", name, defs_by_name[name]["handler_group"], len(handlers))  # type: ignore[arg-type]

        # Store metadata for later gating
        metadata: dict[str, dict] = {}
        for name in MANIFEST_ORDER:
            metadata[name] = {
                "handler_group": defs_by_name[name]["handler_group"],  # type: ignore[arg-type]
                "handlers": result[name],
            }
        application.bot_data["plugin_handlers"] = metadata  # type: ignore[index]

        return result