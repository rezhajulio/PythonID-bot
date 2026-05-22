"""Plugin toggle resolution.

Provides deterministic resolution of plugin enabled/disabled state
from environment-level defaults and per-group overrides.
"""

from __future__ import annotations

from bot.group_config import KNOWN_PLUGINS

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
        Dict mapping every ``KNOWN_PLUGINS`` name to its resolved bool.
    """
    result: dict[str, bool] = {}

    for name in KNOWN_PLUGINS:
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

def is_plugin_enabled(toggles: dict[str, bool], name: str) -> bool:
    """Check if a single plugin is enabled from a resolved toggle dict.

    Args:
        toggles: Resolved toggle dict from ``resolve_plugin_toggles``.
        name: Plugin name to check.

    Returns:
        True if plugin is enabled.

    Raises:
        KeyError: If ``name`` is not in ``toggles``.
    """
    return toggles[name]


def is_plugin_enabled_for_group(
    effective_map: dict[int, dict[str, bool]],
    group_id: int,
    plugin_name: str,
) -> bool:
    """Check if a plugin is enabled for a specific group using the effective map.

    Safe defaults:
    - Unknown group_id => True (allow through)
    - Missing plugin key in group toggles => True (strict defaults)

    Args:
        effective_map: Per-group plugin toggle map from
            ``compute_effective_plugin_map``, stored in
            ``bot_data["plugin_effective_map"]``.
        group_id: Telegram group ID to check.
        plugin_name: Plugin name from ``MANIFEST_ORDER`` / ``KNOWN_PLUGINS``.

    Returns:
        True if plugin is enabled for the given group.
    """
    group_toggles = effective_map.get(group_id)
    if group_toggles is None:
        return True  # Unknown group => safe default
    return group_toggles.get(plugin_name, True)  # Missing key => safe default