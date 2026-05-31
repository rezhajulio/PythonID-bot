"""Built-in plugin: captcha.

Wraps ``bot.handlers.captcha`` handlers for new member verification.
All register at group=0 via ``captcha.get_handlers()``.
All group-scoped callbacks are wrapped with ``guard_plugin("captcha")``
for runtime per-group gating.

Also exposes individual registrar function ``register_captcha`` for
fine-grained plugin registration.
"""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING

from bot.handlers import captcha
from bot.plugins.config import guard_plugin

if TYPE_CHECKING:
    from telegram.ext import Application, BaseHandler

logger = logging.getLogger(__name__)

# --- Individual registrar function ---

def register_captcha(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register captcha handlers onto application.

    Each handler is CLONED before wrapping to avoid mutating the original
    handler objects returned by ``get_handlers()``.
    """
    handlers = captcha.get_handlers()
    registered = []
    for h in handlers:
        # Clone the handler to avoid mutating the original
        cloned = copy.copy(h)
        cloned.callback = guard_plugin("captcha")(cloned.callback)  # type: ignore[method-assign]
        application.add_handler(cloned)
        registered.append(cloned)
    logger.info("Registered handler: captcha_handlers (group=0)")
    return registered

# --- Coarse plugin class (keeps existing API) ---

# Coarse plugin class for API compatibility. Unused by PluginManager.
class _CaptchaPlugin:
    """Plugin wrapper for captcha handlers."""

    name: str = "captcha"
    description: str = "Captcha verification for new members"
    handler_group: int = 0

    def register(self, application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
        """Register captcha handlers onto application."""
        return register_captcha(application)

plugin = _CaptchaPlugin()