"""Built-in plugin: spam.

Wraps all anti-spam handlers (inline_keyboard_spam, bio_bait_spam,
contact_spam, new_user_spam, duplicate_spam) with their respective
filter and group patterns matching main.py.  All group-scoped callbacks
are wrapped with ``guard_plugin`` for runtime per-group gating.

Also exposes individual registrar functions (register_inline_keyboard_spam,
register_bio_bait_spam, etc.) for fine-grained plugin registration.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram.ext import MessageHandler, filters

from bot.handlers.anti_spam import handle_contact_spam, handle_inline_keyboard_spam, handle_new_user_spam
from bot.handlers.bio_bait import BIO_BAIT_FILTER, handle_bio_bait_spam
from bot.handlers.duplicate_spam import handle_duplicate_spam
from bot.plugins.config import guard_plugin

if TYPE_CHECKING:
    from telegram.ext import Application, BaseHandler

logger = logging.getLogger(__name__)

# --- Individual registrar functions ---

def register_inline_keyboard_spam(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register inline keyboard spam handler (group=1).

    Callback wrapped with ``guard_plugin("inline_keyboard_spam")``.
    """
    handler: BaseHandler = MessageHandler(
        filters.ChatType.GROUPS,
        guard_plugin("inline_keyboard_spam")(handle_inline_keyboard_spam),
    )
    application.add_handler(handler, group=1)
    logger.info("Registered handler: inline_keyboard_spam_handler (group=1)")
    return [handler]

def register_bio_bait_spam(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register bio bait spam handler (group=4).

    Callback wrapped with ``guard_plugin("bio_bait_spam")``.
    """
    handler: BaseHandler = MessageHandler(
        BIO_BAIT_FILTER,
        guard_plugin("bio_bait_spam")(handle_bio_bait_spam),
    )
    application.add_handler(handler, group=4)
    logger.info("Registered handler: bio_bait_spam_handler (group=4)")
    return [handler]

def register_contact_spam(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register contact spam handler (group=2).

    Callback wrapped with ``guard_plugin("contact_spam")``.
    """
    handler: BaseHandler = MessageHandler(
        filters.ChatType.GROUPS & filters.CONTACT,
        guard_plugin("contact_spam")(handle_contact_spam),
    )
    application.add_handler(handler, group=2)
    logger.info("Registered handler: contact_spam_handler (group=2)")
    return [handler]

def register_new_user_spam(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register new user spam handler (probation, group=3).

    Callback wrapped with ``guard_plugin("new_user_spam")``.
    """
    handler: BaseHandler = MessageHandler(
        filters.ChatType.GROUPS,
        guard_plugin("new_user_spam")(handle_new_user_spam),
    )
    application.add_handler(handler, group=3)
    logger.info("Registered handler: anti_spam_handler (group=3)")
    return [handler]

def register_duplicate_spam(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register duplicate message spam handler (group=4).

    Callback wrapped with ``guard_plugin("duplicate_spam")``.
    """
    handler: BaseHandler = MessageHandler(
        filters.ChatType.GROUPS & ~filters.COMMAND,
        guard_plugin("duplicate_spam")(handle_duplicate_spam),
    )
    application.add_handler(handler, group=4)
    logger.info("Registered handler: duplicate_spam_handler (group=4)")
    return [handler]

# --- Coarse plugin class (keeps existing API) ---

# Coarse plugin class for API compatibility. Unused by PluginManager.
class _SpamPlugin:
    """Plugin wrapper for all anti-spam handlers."""

    name: str = "spam"
    description: str = "Anti-spam handlers (inline keyboards, bio bait, contact, probation, duplicates)"
    handler_group: int = 1

    def register(self, application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
        """Register all spam handlers onto application with their respective groups."""
        handlers: list[BaseHandler] = []
        handlers.extend(register_inline_keyboard_spam(application))
        handlers.extend(register_bio_bait_spam(application))
        handlers.extend(register_contact_spam(application))
        handlers.extend(register_new_user_spam(application))
        handlers.extend(register_duplicate_spam(application))
        return handlers

plugin = _SpamPlugin()