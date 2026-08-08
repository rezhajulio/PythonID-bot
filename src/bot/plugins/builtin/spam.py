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
from bot.handlers.guest_bot import GuestBotFilter, handle_guest_bot_message
from bot.plugins.config import guard_plugin

if TYPE_CHECKING:
    from telegram.ext import Application, BaseHandler

logger = logging.getLogger(__name__)

# --- Helper for spam handler registration ---

def _register_spam(application: Application, handler: BaseHandler, group: int, label: str) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register a spam handler at a specific group and log the registration."""
    application.add_handler(handler, group=group)
    logger.info(f"Registered handler: {label} (group={group})")
    return [handler]


# --- Individual registrar functions ---

def register_inline_keyboard_spam(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register inline keyboard spam handler (group=1).

    Callback wrapped with ``guard_plugin("inline_keyboard_spam")``.
    """
    handler: BaseHandler = MessageHandler(
        filters.ChatType.GROUPS,
        guard_plugin("inline_keyboard_spam")(handle_inline_keyboard_spam),
    )
    return _register_spam(application, handler, 1, "inline_keyboard_spam_handler")

def register_guest_bot_block(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register guest bot block handler (group=0).

    Callback wrapped with ``guard_plugin(\"guest_bot_block\")``. Runs at
    group=0 (same group as commands and captcha) to intercept Telegram
    Guest Mode messages before other spam checks at higher groups.
    """
    handler: BaseHandler = MessageHandler(
        GuestBotFilter(),
        guard_plugin("guest_bot_block")(handle_guest_bot_message),
    )
    return _register_spam(application, handler, 0, "guest_bot_block_handler")

def register_bio_bait_spam(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register bio bait spam handler (group=4).

    Callback wrapped with ``guard_plugin("bio_bait_spam")``. Shares group=4
    and filter shape with ``duplicate_spam``; ``block=False`` so both get a
    chance to run instead of the first match swallowing the update.
    """
    handler: BaseHandler = MessageHandler(
        BIO_BAIT_FILTER,
        guard_plugin("bio_bait_spam")(handle_bio_bait_spam),
        block=False,
    )
    return _register_spam(application, handler, 4, "bio_bait_spam_handler")

def register_contact_spam(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register contact spam handler (group=2).

    Callback wrapped with ``guard_plugin("contact_spam")``.
    """
    handler: BaseHandler = MessageHandler(
        filters.ChatType.GROUPS & filters.CONTACT,
        guard_plugin("contact_spam")(handle_contact_spam),
    )
    return _register_spam(application, handler, 2, "contact_spam_handler")

def register_new_user_spam(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register new user spam handler (probation, group=3).

    Callback wrapped with ``guard_plugin("new_user_spam")``.
    """
    handler: BaseHandler = MessageHandler(
        filters.ChatType.GROUPS,
        guard_plugin("new_user_spam")(handle_new_user_spam),
    )
    return _register_spam(application, handler, 3, "anti_spam_handler")

def register_duplicate_spam(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register duplicate message spam handler (group=4).

    Callback wrapped with ``guard_plugin("duplicate_spam")``. Registered
    before ``bio_bait_spam`` in the same group with the same filter shape;
    ``block=False`` so PTB still checks the next handler in group=4 instead
    of stopping after this one matches.
    """
    handler: BaseHandler = MessageHandler(
        filters.ChatType.GROUPS & ~filters.COMMAND,
        guard_plugin("duplicate_spam")(handle_duplicate_spam),
        block=False,
    )
    return _register_spam(application, handler, 4, "duplicate_spam_handler")
