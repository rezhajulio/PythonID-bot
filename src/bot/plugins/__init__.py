"""Plugin system for PythonID bot.

Provides base contracts, toggle resolution, and plugin definitions
for modular handler registration.
"""

from bot.plugins.base import PluginProtocol
from bot.plugins.config import is_plugin_enabled, resolve_plugin_toggles

__all__ = [
    "PluginProtocol",
    "is_plugin_enabled",
    "resolve_plugin_toggles",
]