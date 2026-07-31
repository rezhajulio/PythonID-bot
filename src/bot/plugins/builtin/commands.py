"""Built-in plugin: commands.

Wraps all command and callback handlers (verify, unverify, check, trust,
untrust, trusted_list, check_forwarded_message, and their callbacks).
All register at group=0.

Note: guard_plugin is intentionally NOT applied to admin
commands/callbacks. Admin overrides must work in every group regardless
of plugin toggle state. This matches pre-refactor behavior where admin
commands were never gated.

Also exposes individual registrar functions (register_verify,
register_unverify, etc.) for fine-grained plugin registration.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters

from bot.handlers.check import (
    handle_check_command,
    handle_check_forwarded_message,
    handle_check_group_callback,
    handle_warn_callback,
)
from bot.handlers.trust import (
    handle_trust_callback,
    handle_trust_command,
    handle_trusted_list_command,
    handle_untrust_callback,
    handle_untrust_command,
)
from bot.handlers.verify import (
    handle_unrestrict_callback,
    handle_unverify_callback,
    handle_unverify_command,
    handle_verify_callback,
    handle_verify_command,
)

if TYPE_CHECKING:
    from telegram.ext import Application, BaseHandler

logger = logging.getLogger(__name__)


# --- Helper for handler registration ---

def _register(application: Application, handler: BaseHandler, label: str) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register a handler and log the registration."""
    application.add_handler(handler)
    logger.info(f"Registered handler: {label} (group=0)")
    return [handler]


# --- Individual registrar functions ---

def register_verify(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register /verify command handler."""
    handler: BaseHandler = CommandHandler("verify", handle_verify_command)
    return _register(application, handler, "verify_command")


def register_unverify(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register /unverify command handler."""
    handler: BaseHandler = CommandHandler("unverify", handle_unverify_command)
    return _register(application, handler, "unverify_command")


def register_check(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register /check command handler."""
    handler: BaseHandler = CommandHandler("check", handle_check_command)
    return _register(application, handler, "check_command")


def register_trust(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register /trust command handler."""
    handler: BaseHandler = CommandHandler("trust", handle_trust_command)
    return _register(application, handler, "trust_command")


def register_untrust(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register /untrust command handler."""
    handler: BaseHandler = CommandHandler("untrust", handle_untrust_command)
    return _register(application, handler, "untrust_command")


def register_trusted_list(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register /trusted command handler."""
    handler: BaseHandler = CommandHandler("trusted", handle_trusted_list_command)
    return _register(application, handler, "trusted_list_command")


def register_check_forwarded_message(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register forwarded message handler for /check context."""
    handler: BaseHandler = MessageHandler(
        filters.FORWARDED & filters.ChatType.PRIVATE,
        handle_check_forwarded_message,
    )
    return _register(application, handler, "check_forwarded_message")


def register_check_group_callback(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register group selector callback for /check."""
    handler: BaseHandler = CallbackQueryHandler(
        handle_check_group_callback,
        pattern=r"^checkgrp:-?\d+:\d+$",
    )
    return _register(application, handler, "check_group_callback")


def register_verify_callback(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register verify callback handler (group-scoped)."""
    handler: BaseHandler = CallbackQueryHandler(
        handle_verify_callback,
        pattern=r"^verify:-?\d+:\d+$",
    )
    return _register(application, handler, "verify_callback")


def register_unverify_callback(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register unverify callback handler (group-scoped)."""
    handler: BaseHandler = CallbackQueryHandler(
        handle_unverify_callback,
        pattern=r"^unverify:-?\d+:\d+$",
    )
    return _register(application, handler, "unverify_callback")


def register_warn_callback(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register warn callback handler (group-scoped)."""
    handler: BaseHandler = CallbackQueryHandler(
        handle_warn_callback,
        pattern=r"^warn:-?\d+:\d+:",
    )
    return _register(application, handler, "warn_callback")


def register_trust_callback(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register trust callback handler (group-scoped)."""
    handler: BaseHandler = CallbackQueryHandler(
        handle_trust_callback,
        pattern=r"^trust:-?\d+:\d+$",
    )
    return _register(application, handler, "trust_callback")


def register_untrust_callback(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register untrust callback handler (group-scoped)."""
    handler: BaseHandler = CallbackQueryHandler(
        handle_untrust_callback,
        pattern=r"^untrust:-?\d+:\d+$",
    )
    return _register(application, handler, "untrust_callback")


def register_unrestrict_callback(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register unrestrict callback handler (group-scoped)."""
    handler: BaseHandler = CallbackQueryHandler(
        handle_unrestrict_callback,
        pattern=r"^unrestrict:-?\d+:\d+$",
    )
    return _register(application, handler, "unrestrict_callback")
