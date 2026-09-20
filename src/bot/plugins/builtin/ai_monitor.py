"""Built-in plugin: ai_spam_monitor.

Wraps ``bot.handlers.ai_spam_monitor`` for classifier.dev-powered spam
monitoring. Registers the message handler at group=7 (the last defense:
only messages that survived every enforcement handler reach it) and the
alert action callback at group=0 alongside other callbacks. Applies
runtime gating via ``guard_plugin("ai_spam_monitor")``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram.ext import CallbackQueryHandler, MessageHandler

from bot.handlers.ai_spam_monitor import (
    AI_SPAM_CALLBACK_PATTERN,
    AI_SPAM_FILTER,
    handle_ai_spam_action,
    handle_ai_spam_monitor,
)
from bot.plugins.config import guard_plugin

if TYPE_CHECKING:
    from telegram.ext import Application, BaseHandler

logger = logging.getLogger(__name__)

# --- Individual registrar function ---

def register_ai_spam_monitor(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register the AI spam monitor message handler (group=7).

    Runs at the highest handler group so it only classifies messages
    that passed all other handler groups. Wrapped with
    ``guard_plugin("ai_spam_monitor")`` for runtime per-group gating.
    """
    handler: BaseHandler = MessageHandler(
        AI_SPAM_FILTER,
        guard_plugin("ai_spam_monitor")(handle_ai_spam_monitor),
    )
    application.add_handler(handler, group=7)
    logger.info("Registered handler: ai_spam_monitor (group=7)")
    return [handler]


def register_ai_spam_callback(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register the alert action callback handler (group=0).

    Runs alongside the other admin action callbacks. Wrapped with
    ``guard_plugin("ai_spam_callback")`` for runtime per-group gating.
    """
    handler: BaseHandler = CallbackQueryHandler(
        guard_plugin("ai_spam_callback")(handle_ai_spam_action),
        pattern=AI_SPAM_CALLBACK_PATTERN,
    )
    application.add_handler(handler, group=0)
    logger.info("Registered handler: ai_spam_callback (group=0)")
    return [handler]
