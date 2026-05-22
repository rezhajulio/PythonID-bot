"""Built-in plugin: topic_guard.

Wraps ``bot.handlers.topic_guard.guard_warning_topic`` with same
filter/group pattern (MessageHandler, MESSAGE|EDITED_MESSAGE, group=-1).
Applies runtime gating via ``guard_plugin("topic_guard")``.

Also exposes individual registrar function ``register_topic_guard`` for
fine-grained plugin registration.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram.ext import MessageHandler, filters

from bot.handlers.topic_guard import guard_warning_topic
from bot.plugins.config import guard_plugin

if TYPE_CHECKING:
    from telegram.ext import Application, BaseHandler

logger = logging.getLogger(__name__)

# --- Individual registrar function ---

def register_topic_guard(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register topic_guard handler onto application (group=-1).

    The callback is wrapped with ``guard_plugin("topic_guard")`` for
    runtime per-group enable/disable gating.
    """
    handler: BaseHandler = MessageHandler(
        filters.UpdateType.MESSAGE | filters.UpdateType.EDITED_MESSAGE,
        guard_plugin("topic_guard")(guard_warning_topic),
    )
    application.add_handler(handler, group=-1)
    logger.info("Registered handler: topic_guard (group=-1, message + edited_message)")
    return [handler]

# --- Coarse plugin class (keeps existing API) ---

class _TopicGuardPlugin:
    """Plugin wrapper for topic_guard handler."""

    name: str = "topic_guard"
    description: str = "Intercept warning-topic messages before other handlers"
    handler_group: int = -1

    def register(self, application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
        """Register topic_guard handler onto application."""
        return register_topic_guard(application)

plugin = _TopicGuardPlugin()