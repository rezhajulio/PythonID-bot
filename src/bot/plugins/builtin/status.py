"""Built-in plugin: status.

Wraps ``bot.handlers.status`` for the ``/status`` DM-admin command.
No ``guard_plugin`` wrap — /status is admin-only by handler checks, not
per-group gated.
"""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING

from bot.handlers import status

if TYPE_CHECKING:
    from telegram.ext import Application, BaseHandler

logger = logging.getLogger(__name__)


def register_status(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register /status command handler.

    Each handler is CLONED before adding to avoid mutating the original
    handler objects returned by ``get_handlers()``.
    """
    handlers = status.get_handlers()
    registered = []
    for h in handlers:
        cloned = copy.copy(h)
        # No guard_plugin wrap — /status is admin-gated by the handler itself
        application.add_handler(cloned)
        registered.append(cloned)
    logger.info("Registered handler: status (group=0)")
    return registered
