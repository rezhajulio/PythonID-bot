"""Built-in plugin: dm.

Wraps ``bot.handlers.dm.handle_dm`` for DM unrestriction flow.
Registers at group=0 with PRIVATE & TEXT filter.

Also exposes individual registrar function ``register_dm`` for
fine-grained plugin registration.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram.ext import MessageHandler, filters

from bot.handlers.dm import handle_dm

if TYPE_CHECKING:
    from telegram.ext import Application, BaseHandler

logger = logging.getLogger(__name__)


# --- Individual registrar function ---

def register_dm(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register DM handler onto application."""
    handler: BaseHandler = MessageHandler(
        filters.ChatType.PRIVATE & filters.TEXT,
        handle_dm,
    )
    application.add_handler(handler)
    logger.info("Registered handler: dm_handler (group=0)")
    return [handler]


# --- Coarse plugin class (keeps existing API) ---

# Coarse plugin class for API compatibility. Unused by PluginManager.
class _DmPlugin:
    """Plugin wrapper for DM handler."""

    name: str = "dm"
    description: str = "Direct message unrestriction flow"
    handler_group: int = 0

    def register(self, application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
        """Register DM handler onto application."""
        return register_dm(application)


plugin = _DmPlugin()