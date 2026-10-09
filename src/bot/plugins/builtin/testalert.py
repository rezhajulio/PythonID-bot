"""Built-in plugin: testalert.

Wraps ``bot.handlers.testalert`` for the ``/testalert`` DM-admin command.
No ``guard_plugin`` wrap — /testalert is admin-only by handler checks, not
per-group gated.
"""

from __future__ import annotations

import logging

from bot.dispatch import AppState, HandlerSpec
from bot.handlers import testalert

logger = logging.getLogger(__name__)


def register_testalert(state: AppState) -> list[HandlerSpec]:
    """Register /testalert command handler spec."""
    specs = testalert.get_handlers(state)
    # No guard_plugin wrap — /testalert is admin-gated by the handler itself
    logger.info("Registered handler: testalert (group=0)")
    return specs
