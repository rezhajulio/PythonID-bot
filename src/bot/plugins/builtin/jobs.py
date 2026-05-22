"""Built-in plugin: jobs.

Wraps periodic JobQueue jobs (auto_restrict_job, refresh_admin_ids_job).
Register repeating jobs via application.job_queue.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bot.services.scheduler import auto_restrict_expired_warnings
from bot.main import refresh_admin_ids

if TYPE_CHECKING:
    from telegram.ext import Application, BaseHandler

logger = logging.getLogger(__name__)


class _JobsPlugin:
    """Plugin wrapper for periodic job handlers."""

    name: str = "jobs"
    description: str = "Periodic JobQueue tasks (auto-restrict, admin cache refresh)"
    handler_group: int = 6

    def register(self, application: Application) -> list[BaseHandler]:  # type: ignore[type-arg]
        """Register repeating jobs onto application.job_queue."""
        handlers: list[BaseHandler] = []

        if application.job_queue:
            application.job_queue.run_repeating(
                auto_restrict_expired_warnings,
                interval=300,
                first=300,
                name="auto_restrict_job",
            )
            logger.info("JobQueue registered: auto_restrict_job (every 5 minutes, first run in 5 minutes)")

            application.job_queue.run_repeating(
                refresh_admin_ids,
                interval=600,
                first=600,
                name="refresh_admin_ids_job",
            )
            logger.info("JobQueue registered: refresh_admin_ids_job (every 10 minutes)")

        return handlers


plugin = _JobsPlugin()