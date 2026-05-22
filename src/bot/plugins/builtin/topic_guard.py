"""Built-in plugin: topic_guard.

Wraps ``bot.handlers.topic_guard.guard_warning_topic`` with same
filter/group pattern (MessageHandler, MESSAGE|EDITED_MESSAGE, group=-1).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram.ext import MessageHandler, filters

from bot.handlers.topic_guard import guard_warning_topic

if TYPE_CHECKING:
    from telegram.ext import Application, BaseHandler

logger = logging.getLogger(__name__)


class _TopicGuardPlugin:
    """Plugin wrapper for topic_guard handler."""

    name: str = "topic_guard"
    description: str = "Intercept warning-topic messages before other handlers"
    handler_group: int = -1

    def register(self, application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
        """Register topic_guard handler onto application."""
        handler: BaseHandler = MessageHandler(
            filters.UpdateType.MESSAGE | filters.UpdateType.EDITED_MESSAGE,
            guard_warning_topic,
        )
        application.add_handler(handler, group=-1)
        logger.info("Registered handler: topic_guard (group=-1, message + edited_message)")
        return [handler]


plugin = _TopicGuardPlugin()