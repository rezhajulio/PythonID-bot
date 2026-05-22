"""Plugin system for PythonID bot.

Provides base contracts, toggle resolution, plugin definitions,
and runtime guard wrappers for modular handler registration.
"""

from bot.plugins.base import PluginProtocol
from bot.plugins.config import guard_plugin, is_plugin_enabled, resolve_plugin_toggles
from bot.plugins.definitions import PluginManifest, get_plugin_definitions

__all__ = [
    "PluginProtocol",
    "PluginManifest",
    "get_plugin_definitions",
    "guard_plugin",
    "is_plugin_enabled",
    "resolve_plugin_toggles",
]