"""Built-in plugin: spam.

Wraps all anti-spam handlers (inline_keyboard_spam, bio_bait_spam,
contact_spam, new_user_spam, duplicate_spam) with their respective
filter and group patterns matching main.py.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram.ext import MessageHandler, filters

from bot.handlers.anti_spam import handle_contact_spam, handle_inline_keyboard_spam, handle_new_user_spam
from bot.handlers.bio_bait import BIO_BAIT_FILTER, handle_bio_bait_spam
from bot.handlers.duplicate_spam import handle_duplicate_spam

if TYPE_CHECKING:
    from telegram.ext import Application, BaseHandler

logger = logging.getLogger(__name__)


class _SpamPlugin:
    """Plugin wrapper for all anti-spam handlers."""

    name: str = "spam"
    description: str = "Anti-spam handlers (inline keyboards, bio bait, contact, probation, duplicates)"
    handler_group: int = 1

    def register(self, application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
        """Register all spam handlers onto application with their respective groups."""
        handlers: list[BaseHandler] = []

        # Inline keyboard spam - group 1
        h: BaseHandler = MessageHandler(
            filters.ChatType.GROUPS,
            handle_inline_keyboard_spam,
        )
        application.add_handler(h, group=1)
        handlers.append(h)
        logger.info("Registered handler: inline_keyboard_spam_handler (group=1)")

        # Bio bait spam - group 2
        h = MessageHandler(
            BIO_BAIT_FILTER,
            handle_bio_bait_spam,
        )
        application.add_handler(h, group=2)
        handlers.append(h)
        logger.info("Registered handler: bio_bait_spam_handler (group=2)")

        # Contact spam - group 3
        h = MessageHandler(
            filters.ChatType.GROUPS & filters.CONTACT,
            handle_contact_spam,
        )
        application.add_handler(h, group=3)
        handlers.append(h)
        logger.info("Registered handler: contact_spam_handler (group=3)")

        # New user spam (probation) - group 4
        h = MessageHandler(
            filters.ChatType.GROUPS,
            handle_new_user_spam,
        )
        application.add_handler(h, group=4)
        handlers.append(h)
        logger.info("Registered handler: anti_spam_handler (group=4)")

        # Duplicate spam - group 5
        h = MessageHandler(
            filters.ChatType.GROUPS & ~filters.COMMAND,
            handle_duplicate_spam,
        )
        application.add_handler(h, group=5)
        handlers.append(h)
        logger.info("Registered handler: duplicate_spam_handler (group=5)")

        return handlers


plugin = _SpamPlugin()