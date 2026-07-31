"""Plugin manager for deterministic handler/job registration.

Provides ``PluginManager`` which maps each fine-grained plugin name
(from ``MANIFEST_ORDER``) to an individual registrar callable, then
calls them in canonical order via ``register_all()``.

Handler groups: topic_guard (-1), commands/captcha/dm (0),
inline_keyboard_spam (1), contact_spam (2), new_user_spam (3),
duplicate_spam (4), bio_bait_spam (4), profile_monitor (5), jobs (6).

Usage inside ``main.py``::

    pm = PluginManager()
    plugin_handlers = pm.register_all(application)
    # plugin_handlers dict stored in application.bot_data["plugin_handlers"]

    # After init_group_registry:
    pm.compute_effective_map(settings, get_group_registry(), application)
    # Per-group toggles stored in application.bot_data["plugin_effective_map"]
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
from bot.plugins.builtin import status as status_mod
from bot.plugins.builtin import topic_guard as tg_mod
from bot.plugins.config import resolve_plugin_toggles
from bot.plugins.definitions import MANIFEST_ORDER, get_plugin_definitions

if TYPE_CHECKING:
    from telegram.ext import Application, BaseHandler

logger = logging.getLogger(__name__)

# Type alias for a registrar callable.
# Accepts an Application, returns a list of registered BaseHandler instances.
# Use string forward ref because BaseHandler is only imported under TYPE_CHECKING.
Registrar = Callable[..., list["BaseHandler"]]

# Module-level registry constant mapping plugin names to registrar functions.
_REGISTRY: dict[str, Registrar] = {
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
    "check_group_callback": commands.register_check_group_callback,
    "verify_callback": commands.register_verify_callback,
    "unverify_callback": commands.register_unverify_callback,
    "warn_callback": commands.register_warn_callback,
    "trust_callback": commands.register_trust_callback,
    "untrust_callback": commands.register_untrust_callback,
    "unrestrict_callback": commands.register_unrestrict_callback,
    # captcha
    "captcha": captcha_mod.register_captcha,
    # dm
    "dm": dm_mod.register_dm,
    # status
    "status": status_mod.register_status,
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


def compute_effective_plugin_map(
    plugins_default: dict[str, bool],
    registry: object,
) -> dict[int, dict[str, bool]]:
    """Compute per-group effective plugin toggle maps for all registry groups.

    For each group in the registry, resolves plugin enabled/disabled state
    using ``resolve_plugin_toggles`` with env defaults and per-group overrides.

    Args:
        plugins_default: Env-wide default toggles from Settings.plugins_default.
        registry: GroupRegistry instance with all monitored groups.

    Returns:
        Dict mapping group_id -> resolved toggle dict (all KNOWN_PLUGINS keys).
        Empty dict if registry has no groups.
    """
    from bot.group_config import GroupRegistry

    if not isinstance(registry, GroupRegistry):
        logger.warning("compute_effective_plugin_map: registry is not a GroupRegistry")
        return {}

    result: dict[int, dict[str, bool]] = {}
    for gc in registry.all_groups():
        result[gc.group_id] = resolve_plugin_toggles(plugins_default, gc.plugins)

    return result


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
        """Initialize with a shallow copy of the shared registry."""
        self._registry: dict[str, Registrar] = dict(_REGISTRY)

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
            noun = "job(s)" if name.endswith("_job") else "handler(s)"
            group = defs_by_name[name]["handler_group"]
            logger.info(
                f"Registered plugin: {name} (group={group}, {len(handlers)} {noun})"
            )

        # Store metadata for later gating
        metadata: dict[str, dict] = {}
        for name in MANIFEST_ORDER:
            metadata[name] = {
                "handler_group": defs_by_name[name]["handler_group"],  # type: ignore[arg-type]
                "handlers": result[name],
            }
        application.bot_data["plugin_handlers"] = metadata  # type: ignore[index]

        return result

    def compute_effective_map(
        self,
        settings: object,
        registry: object,
        application: Application,  # type: ignore[type-arg]
    ) -> dict[int, dict[str, bool]]:
        """Compute and store per-group effective plugin toggle map.

        Resolves plugin enabled/disabled state for every group in the
        registry and stores the result in
        ``application.bot_data["plugin_effective_map"]``.

        Args:
            settings: Application Settings instance (must have
                ``plugins_default`` attribute).
            registry: GroupRegistry instance.
            application: PTB Application instance.

        Returns:
            Dict mapping group_id -> resolved toggle dict. Also stored
            in ``bot_data["plugin_effective_map"]``.
        """
        plugins_default = getattr(settings, "plugins_default", {})
        effective_map = compute_effective_plugin_map(plugins_default, registry)
        application.bot_data["plugin_effective_map"] = effective_map  # type: ignore[index]
        logger.info(f"Computed effective plugin map for {len(effective_map)} group(s)")
        return effective_map