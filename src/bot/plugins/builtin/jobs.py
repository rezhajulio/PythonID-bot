"""Built-in plugin: jobs.

Wraps periodic JobQueue jobs (auto_restrict_job, refresh_admin_ids_job).
Register repeating jobs via application.job_queue.

Also exposes individual registrar functions (register_auto_restrict_job,
register_refresh_admin_ids_job) for fine-grained plugin registration.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bot.services.admin_cache import refresh_admin_ids
from bot.services.scheduler import auto_restrict_expired_warnings

if TYPE_CHECKING:
    from telegram.ext import Application, BaseHandler

logger = logging.getLogger(__name__)

# --- Individual registrar functions ---

def register_auto_restrict_job(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register auto-restrict repeating job (every 5 minutes)."""
    handlers: list[BaseHandler] = []
    if application.job_queue:
        application.job_queue.run_repeating(
            auto_restrict_expired_warnings,
            interval=300,
            first=300,
            name="auto_restrict_job",
        )
        logger.info("JobQueue registered: auto_restrict_job (every 5 minutes, first run in 5 minutes)")
    return handlers

def register_refresh_admin_ids_job(application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
    """Register admin cache refresh job (every 10 minutes)."""
    handlers: list[BaseHandler] = []
    if application.job_queue:
        application.job_queue.run_repeating(
            refresh_admin_ids,
            interval=600,
            first=600,
            name="refresh_admin_ids_job",
        )
        logger.info("JobQueue registered: refresh_admin_ids_job (every 10 minutes)")
    return handlers

# --- Coarse plugin class (keeps existing API) ---

# Coarse plugin class for API compatibility. Unused by PluginManager.
class _JobsPlugin:
    """Plugin wrapper for periodic job handlers."""

    name: str = "jobs"
    description: str = "Periodic JobQueue tasks (auto-restrict, admin cache refresh)"
    handler_group: int = 6

    def register(self, application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
        """Register repeating jobs onto application.job_queue."""
        handlers: list[BaseHandler] = []
        handlers.extend(register_auto_restrict_job(application))
        handlers.extend(register_refresh_admin_ids_job(application))
        return handlers

plugin = _JobsPlugin()