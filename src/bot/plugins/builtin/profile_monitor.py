"""Built-in plugin: profile_monitor.

Wraps ``bot.handlers.message.handle_message`` for profile compliance
monitoring. Registers at group=6 with GROUPS & ~COMMAND filter.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram.ext import MessageHandler, filters

from bot.handlers.message import handle_message

if TYPE_CHECKING:
    from telegram.ext import Application, BaseHandler

logger = logging.getLogger(__name__)


class _ProfileMonitorPlugin:
    """Plugin wrapper for profile compliance monitor."""

    name: str = "profile_monitor"
    description: str = "Profile compliance monitoring"
    handler_group: int = 6

    def register(self, application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
        """Register profile monitor handler onto application."""
        handler: BaseHandler = MessageHandler(
            filters.ChatType.GROUPS & ~filters.COMMAND,
            handle_message,
        )
        application.add_handler(handler, group=6)
        logger.info("Registered handler: message_handler (group=6)")
        return [handler]


plugin = _ProfileMonitorPlugin()