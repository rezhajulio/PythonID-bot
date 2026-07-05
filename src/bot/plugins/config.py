"""Plugin toggle resolution and runtime guard wrapper.

Provides deterministic resolution of plugin enabled/disabled state
from environment-level defaults and per-group overrides, plus a
reusable ``guard_plugin`` decorator for runtime gating of group-scoped
handler callbacks.
"""

from __future__ import annotations

import functools
import logging
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from bot.plugins.definitions import PLUGIN_NAMES

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

def resolve_plugin_toggles(
    defaults: dict[str, bool],
    overrides: dict[str, bool] | None,
) -> dict[str, bool]:
    """Resolve plugin enabled/disabled state for all known plugins.

    Resolution order (first match wins):
    1. Group ``overrides`` (explicit per-group plugin config)
    2. Environment ``defaults`` (PLUGINS_DEFAULT env var)
    3. ``True`` (all plugins enabled by default)

    Args:
        defaults: Env-wide default toggles from Settings.plugins_default.
        overrides: Per-group overrides from GroupConfig.plugins (or None).

    Returns:
        Dict mapping every ``PLUGIN_NAMES`` name to its resolved bool.
    """
    result: dict[str, bool] = {}

    for name in PLUGIN_NAMES:
        # Priority 1: group override (if present)
        if overrides is not None and name in overrides:
            result[name] = overrides[name]
        # Priority 2: env default (if present)
        elif name in defaults:
            result[name] = defaults[name]
        # Priority 3: True (default)
        else:
            result[name] = True

    return result

def is_plugin_enabled_for_group(
    effective_map: dict[int, dict[str, bool]],
    group_id: int,
    plugin_name: str,
) -> bool:
    """Check if a plugin is enabled for a specific group using the effective map.

    Fail-open defaults:
    - Unknown group_id => True (allow through)
    - Missing plugin key in group toggles => True (fail-open)

    Args:
        effective_map: Per-group plugin toggle map from
            ``compute_effective_plugin_map``, stored in
            ``bot_data["plugin_effective_map"]``.
        group_id: Telegram group ID to check.
        plugin_name: Plugin name from ``MANIFEST_ORDER`` / ``PLUGIN_NAMES``.

    Returns:
        True if plugin is enabled for the given group.
    """
    group_toggles = effective_map.get(group_id)
    if group_toggles is None:
        return True  # Unknown group => fail-open
    return group_toggles.get(plugin_name, True)  # Missing key => fail-open

def validate_plugin_map(parsed: dict[str, bool]) -> dict[str, bool]:
    """Validate that all keys are known plugin names and all values are bools.

    Args:
        parsed: Dict mapping plugin names to enabled/disabled state.

    Returns:
        The validated dict (unchanged).

    Raises:
        ValueError: If unknown plugin key or non-bool value found.
    """
    for key, val in parsed.items():
        if key not in PLUGIN_NAMES:
            raise ValueError(f"Unknown plugin key: '{key}'")
        if not isinstance(val, bool):
            raise ValueError(f"Plugin '{key}' value must be a boolean, got {type(val).__name__}")
    return parsed

def guard_plugin(
    plugin_name: str,
) -> Callable[
    [Callable[..., Coroutine[Any, Any, None]]],
    Callable[..., Coroutine[Any, Any, None]],
]:
    """Return decorator that gates a handler callback on plugin enable state.

    Checks ``context.bot_data["plugin_effective_map"]`` by group id and
    ``plugin_name``.  If the plugin is disabled for the group, the
    decorated callback early-returns (no-op).

    Safe defaults (pass through):
    - Unknown group id (not in effective_map)
    - Missing plugin key in group toggles
    - Empty / missing ``plugin_effective_map`` in bot_data
    - Non-group chat (private, channel)

    Usage::

        @guard_plugin("profile_monitor")
        async def my_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            ...

    Args:
        plugin_name: Plugin name from ``MANIFEST_ORDER`` / ``PLUGIN_NAMES``.

    Returns:
        Decorator that wraps an async handler callback with runtime gating.
    """
    def decorator(
        callback: Callable[..., Coroutine[Any, Any, None]],
    ) -> Callable[..., Coroutine[Any, Any, None]]:
        @functools.wraps(callback)
        async def wrapper(
            update: "Update",
            context: "ContextTypes.DEFAULT_TYPE",
            *args: Any,
            **kwargs: Any,
        ) -> None:
            # Only gate group/supergroup updates
            if update.effective_chat is None or update.effective_chat.type not in ("group", "supergroup"):
                await callback(update, context, *args, **kwargs)
                return

            group_id = update.effective_chat.id
            effective_map: dict[int, dict[str, bool]] = context.bot_data.get("plugin_effective_map", {})

            if not is_plugin_enabled_for_group(effective_map, group_id, plugin_name):
                logger.debug("Plugin '%s' disabled for group %d, skipping", plugin_name, group_id)
                return

            await callback(update, context, *args, **kwargs)

        return wrapper
    return decorator
