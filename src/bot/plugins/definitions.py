"""Plugin definitions and manifest for the PythonID bot.

Provides the canonical mapping from plugin names to human-readable
metadata.  ``PLUGIN_NAMES`` is the single source of truth for all known
built-in plugin identifiers -- other modules import from here.
"""

from __future__ import annotations

import copy

PluginManifest = list[dict[str, str | int]]
"""Type alias for a list of plugin descriptor dicts."""

# Human-readable metadata for each known built-in plugin.
# Order matches main.py registration order (topic_guard first).
# handler_group values match the PTB group argument used in main.py.
_PLUGIN_DEFINITIONS: PluginManifest = [
    {"name": "topic_guard", "handler_group": -1, "description": "Intercept warning-topic messages before other handlers"},
    {"name": "verify", "handler_group": 0, "description": "Admin /verify command"},
    {"name": "unverify", "handler_group": 0, "description": "Admin /unverify command"},
    {"name": "check", "handler_group": 0, "description": "Admin /check command"},
    {"name": "trust", "handler_group": 0, "description": "Admin /trust command"},
    {"name": "untrust", "handler_group": 0, "description": "Admin /untrust command"},
    {"name": "trusted_list", "handler_group": 0, "description": "Admin /trusted list command"},
    {"name": "check_forwarded_message", "handler_group": 0, "description": "Handle forwarded messages for /check context"},
    {"name": "verify_callback", "handler_group": 0, "description": "Admin verify confirm button callback"},
    {"name": "unverify_callback", "handler_group": 0, "description": "Admin unverify button callback"},
    {"name": "warn_callback", "handler_group": 0, "description": "Admin warn button callback"},
    {"name": "trust_callback", "handler_group": 0, "description": "Admin trust button callback"},
    {"name": "untrust_callback", "handler_group": 0, "description": "Admin untrust button callback"},
    {"name": "captcha", "handler_group": 0, "description": "Captcha verification for new members"},
    {"name": "dm", "handler_group": 0, "description": "Direct message unrestriction flow"},
    {"name": "status", "handler_group": 0, "description": "Admin /status command"},
    {"name": "inline_keyboard_spam", "handler_group": 1, "description": "Block inline keyboard URL spam"},
    {"name": "contact_spam", "handler_group": 2, "description": "Block contact card sharing"},
    {"name": "new_user_spam", "handler_group": 3, "description": "Probation enforcement for new users"},
    {"name": "duplicate_spam", "handler_group": 4, "description": "Repeated message detection"},
    {"name": "bio_bait_spam", "handler_group": 4, "description": "Detect and alert on bio bait patterns"},
    {"name": "profile_monitor", "handler_group": 5, "description": "Profile compliance monitoring"},
    {"name": "auto_restrict_job", "handler_group": 6, "description": "Periodic auto-restriction job (every 5 min)"},
    {"name": "refresh_admin_ids_job", "handler_group": 6, "description": "Periodic admin cache refresh job (every 10 min)"},
]

# Single source of truth: canonical set of all known plugin names.
PLUGIN_NAMES: frozenset[str] = frozenset(d["name"] for d in _PLUGIN_DEFINITIONS)  # type: ignore[arg-type]
"""Canonical set of all known built-in plugin names.

Derived automatically from ``_PLUGIN_DEFINITIONS``.  This is the
single source of truth -- other modules should import from here.
"""

# Deterministic registration order matching main.py.
# topic_guard first (group=-1), refresh_admin_ids_job last.
MANIFEST_ORDER: tuple[str, ...] = tuple(d["name"] for d in _PLUGIN_DEFINITIONS)  # type: ignore[arg-type]
"""Canonical handler registration order for all known built-in plugins.

Order matches ``main.py`` registration sequence:
topic_guard (group=-1) first, then group-0 commands/callbacks/captcha/dm,
then spam handlers (groups 1-4), then profile_monitor (group 5),
then job plugins last.
"""


def get_plugin_definitions() -> PluginManifest:
    """Return a deep copy of all built-in plugin definitions.

    Returns:
        List of plugin descriptor dicts with keys: name, handler_group, description.
    """
    return copy.deepcopy(_PLUGIN_DEFINITIONS)