"""Plugin system for PythonID bot.

Provides base contracts, toggle resolution, plugin definitions,
and runtime guard wrappers for modular handler registration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bot.plugins.base import PluginProtocol
from bot.plugins.config import guard_plugin, is_plugin_enabled, is_plugin_enabled_for_group, resolve_plugin_toggles
from bot.plugins.definitions import PluginManifest, get_plugin_definitions

if TYPE_CHECKING:
    from bot.plugins.manager import compute_effective_plugin_map

__all__ = [
    "PluginProtocol",
    "PluginManifest",
    "compute_effective_plugin_map",
    "get_plugin_definitions",
    "guard_plugin",
    "is_plugin_enabled",
    "is_plugin_enabled_for_group",
    "resolve_plugin_toggles",
]


def __getattr__(name: str) -> object:
    """Lazy-load ``compute_effective_plugin_map`` to avoid circular imports.

    The function is defined in ``bot.plugins.manager``, which imports
    ``bot.plugins.builtin`` → ``bot.handlers.captcha`` → ``bot.group_config``
    → ``bot.plugins.definitions``.  Importing at module level from
    ``__init__.py`` would create a circular dependency because
    ``group_config`` itself imports from ``bot.plugins.definitions``
    while ``bot.plugins`` is still being initialised.
    """
    if name == "compute_effective_plugin_map":
        from bot.plugins.manager import compute_effective_plugin_map as _f
        return _f
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)