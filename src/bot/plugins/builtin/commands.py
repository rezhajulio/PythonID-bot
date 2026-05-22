"""Built-in plugin: commands.

Wraps all command and callback handlers (verify, unverify, check, trust,
untrust, trusted_list, check_forwarded_message, and their callbacks).
All register at group=0.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters

from bot.handlers.check import handle_check_command, handle_check_forwarded_message, handle_warn_callback
from bot.handlers.trust import (
    handle_trust_callback,
    handle_trust_command,
    handle_trusted_list_command,
    handle_untrust_callback,
    handle_untrust_command,
)
from bot.handlers.verify import (
    handle_unverify_callback,
    handle_unverify_command,
    handle_verify_callback,
    handle_verify_command,
)

if TYPE_CHECKING:
    from telegram.ext import Application, BaseHandler

logger = logging.getLogger(__name__)


class _CommandsPlugin:
    """Plugin wrapper for command and callback handlers."""

    name: str = "commands"
    description: str = "Admin commands and callback handlers (verify, unverify, check, trust)"
    handler_group: int = 0

    def register(self, application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
        """Register all command and callback handlers onto application."""
        handlers: list[BaseHandler] = []

        h = CommandHandler("verify", handle_verify_command)
        application.add_handler(h)
        handlers.append(h)
        logger.info("Registered handler: verify_command (group=0)")

        h = CommandHandler("unverify", handle_unverify_command)
        application.add_handler(h)
        handlers.append(h)
        logger.info("Registered handler: unverify_command (group=0)")

        h = CommandHandler("check", handle_check_command)
        application.add_handler(h)
        handlers.append(h)
        logger.info("Registered handler: check_command (group=0)")

        h = CommandHandler("trust", handle_trust_command)
        application.add_handler(h)
        handlers.append(h)
        logger.info("Registered handler: trust_command (group=0)")

        h = CommandHandler("untrust", handle_untrust_command)
        application.add_handler(h)
        handlers.append(h)
        logger.info("Registered handler: untrust_command (group=0)")

        h = CommandHandler("trusted", handle_trusted_list_command)
        application.add_handler(h)
        handlers.append(h)
        logger.info("Registered handler: trusted_list_command (group=0)")

        h = MessageHandler(
            filters.FORWARDED & filters.ChatType.PRIVATE,
            handle_check_forwarded_message,
        )
        application.add_handler(h)
        handlers.append(h)
        logger.info("Registered handler: check_forwarded_message (group=0)")

        h = CallbackQueryHandler(handle_verify_callback, pattern=r"^verify:\d+$")
        application.add_handler(h)
        handlers.append(h)
        logger.info("Registered handler: verify_callback (group=0)")

        h = CallbackQueryHandler(handle_unverify_callback, pattern=r"^unverify:\d+$")
        application.add_handler(h)
        handlers.append(h)
        logger.info("Registered handler: unverify_callback (group=0)")

        h = CallbackQueryHandler(handle_warn_callback, pattern=r"^warn:\d+:")
        application.add_handler(h)
        handlers.append(h)
        logger.info("Registered handler: warn_callback (group=0)")

        h = CallbackQueryHandler(handle_trust_callback, pattern=r"^trust:\d+$")
        application.add_handler(h)
        handlers.append(h)
        logger.info("Registered handler: trust_callback (group=0)")

        h = CallbackQueryHandler(handle_untrust_callback, pattern=r"^untrust:\d+$")
        application.add_handler(h)
        handlers.append(h)
        logger.info("Registered handler: untrust_callback (group=0)")

        return handlers


plugin = _CommandsPlugin()