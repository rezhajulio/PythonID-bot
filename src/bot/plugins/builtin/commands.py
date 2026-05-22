"""Built-in plugin: commands.

Wraps all command and callback handlers (verify, unverify, check, trust,
untrust, trusted_list, check_forwarded_message, and their callbacks).
All register at group=0.

Also exposes individual registrar functions (register_verify,
register_unverify, etc.) for fine-grained plugin registration.
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


# --- Individual registrar functions ---

def register_verify(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register /verify command handler."""
    handler: BaseHandler = CommandHandler("verify", handle_verify_command)
    application.add_handler(handler)
    logger.info("Registered handler: verify_command (group=0)")
    return [handler]


def register_unverify(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register /unverify command handler."""
    handler: BaseHandler = CommandHandler("unverify", handle_unverify_command)
    application.add_handler(handler)
    logger.info("Registered handler: unverify_command (group=0)")
    return [handler]


def register_check(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register /check command handler."""
    handler: BaseHandler = CommandHandler("check", handle_check_command)
    application.add_handler(handler)
    logger.info("Registered handler: check_command (group=0)")
    return [handler]


def register_trust(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register /trust command handler."""
    handler: BaseHandler = CommandHandler("trust", handle_trust_command)
    application.add_handler(handler)
    logger.info("Registered handler: trust_command (group=0)")
    return [handler]


def register_untrust(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register /untrust command handler."""
    handler: BaseHandler = CommandHandler("untrust", handle_untrust_command)
    application.add_handler(handler)
    logger.info("Registered handler: untrust_command (group=0)")
    return [handler]


def register_trusted_list(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register /trusted command handler."""
    handler: BaseHandler = CommandHandler("trusted", handle_trusted_list_command)
    application.add_handler(handler)
    logger.info("Registered handler: trusted_list_command (group=0)")
    return [handler]


def register_check_forwarded_message(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register forwarded message handler for /check context."""
    handler: BaseHandler = MessageHandler(
        filters.FORWARDED & filters.ChatType.PRIVATE,
        handle_check_forwarded_message,
    )
    application.add_handler(handler)
    logger.info("Registered handler: check_forwarded_message (group=0)")
    return [handler]


def register_verify_callback(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register verify callback handler."""
    handler: BaseHandler = CallbackQueryHandler(handle_verify_callback, pattern=r"^verify:\d+$")
    application.add_handler(handler)
    logger.info("Registered handler: verify_callback (group=0)")
    return [handler]


def register_unverify_callback(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register unverify callback handler."""
    handler: BaseHandler = CallbackQueryHandler(handle_unverify_callback, pattern=r"^unverify:\d+$")
    application.add_handler(handler)
    logger.info("Registered handler: unverify_callback (group=0)")
    return [handler]


def register_warn_callback(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register warn callback handler."""
    handler: BaseHandler = CallbackQueryHandler(handle_warn_callback, pattern=r"^warn:\d+:")
    application.add_handler(handler)
    logger.info("Registered handler: warn_callback (group=0)")
    return [handler]


def register_trust_callback(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register trust callback handler."""
    handler: BaseHandler = CallbackQueryHandler(handle_trust_callback, pattern=r"^trust:\d+$")
    application.add_handler(handler)
    logger.info("Registered handler: trust_callback (group=0)")
    return [handler]


def register_untrust_callback(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register untrust callback handler."""
    handler: BaseHandler = CallbackQueryHandler(handle_untrust_callback, pattern=r"^untrust:\d+$")
    application.add_handler(handler)
    logger.info("Registered handler: untrust_callback (group=0)")
    return [handler]


# --- Coarse plugin class (keeps existing API) ---

class _CommandsPlugin:
    """Plugin wrapper for command and callback handlers."""

    name: str = "commands"
    description: str = "Admin commands and callback handlers (verify, unverify, check, trust)"
    handler_group: int = 0

    def register(self, application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
        """Register all command and callback handlers onto application."""
        handlers: list[BaseHandler] = []
        handlers.extend(register_verify(application))
        handlers.extend(register_unverify(application))
        handlers.extend(register_check(application))
        handlers.extend(register_trust(application))
        handlers.extend(register_untrust(application))
        handlers.extend(register_trusted_list(application))
        handlers.extend(register_check_forwarded_message(application))
        handlers.extend(register_verify_callback(application))
        handlers.extend(register_unverify_callback(application))
        handlers.extend(register_warn_callback(application))
        handlers.extend(register_trust_callback(application))
        handlers.extend(register_untrust_callback(application))
        return handlers


plugin = _CommandsPlugin()