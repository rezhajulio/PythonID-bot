"""Built-in plugin: profile_monitor.

Wraps ``bot.handlers.message.handle_message`` for profile compliance
monitoring. Registers at group=6 with GROUPS & ~COMMAND filter.
Applies runtime gating via ``guard_plugin("profile_monitor")``.

Also exposes individual registrar function ``register_profile_monitor``
for fine-grained plugin registration.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram.ext import MessageHandler, filters

from bot.handlers.message import handle_message
from bot.plugins.config import guard_plugin

if TYPE_CHECKING:
    from telegram.ext import Application, BaseHandler

logger = logging.getLogger(__name__)

# --- Individual registrar function ---

def register_profile_monitor(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register profile monitor handler onto application (group=6).

    The callback is wrapped with ``guard_plugin("profile_monitor")`` for
    runtime per-group enable/disable gating.
    """
    handler: BaseHandler = MessageHandler(
        filters.ChatType.GROUPS & ~filters.COMMAND,
        guard_plugin("profile_monitor")(handle_message),
    )
    application.add_handler(handler, group=6)
    logger.info("Registered handler: message_handler (group=6)")
    return [handler]

# --- Coarse plugin class (keeps existing API) ---

class _ProfileMonitorPlugin:
    """Plugin wrapper for profile compliance monitor."""

    name: str = "profile_monitor"
    description: str = "Profile compliance monitoring"
    handler_group: int = 6

    def register(self, application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
        """Register profile monitor handler onto application."""
        return register_profile_monitor(application)

plugin = _ProfileMonitorPlugin()