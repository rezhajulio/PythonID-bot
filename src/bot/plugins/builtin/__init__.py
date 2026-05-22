"""Built-in plugin wrappers for the PythonID bot.

Each submodule exports a single ``plugin`` object satisfying
``PluginProtocol`` that knows how to register its handlers onto
a PTB ``Application`` instance.
"""

from bot.plugins.builtin import (
    captcha,
    commands,
    dm,
    jobs,
    profile_monitor,
    spam,
    topic_guard,
)

__all__ = [
    "captcha",
    "commands",
    "dm",
    "jobs",
    "profile_monitor",
    "spam",
    "topic_guard",
]