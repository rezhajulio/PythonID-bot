"""Base plugin contracts for the PythonID bot plugin system."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from telegram.ext import BaseHandler


@runtime_checkable
class PluginProtocol(Protocol):
    """Protocol that all built-in plugins must satisfy.

    Attributes:
        name: Canonical plugin identifier (must match KNOWN_PLUGINS).
        description: Human-readable description of plugin purpose.
        handler_group: PTB handler group integer for registration ordering.
    """

    name: str
    description: str
    handler_group: int

    def register(self, application: object) -> list[BaseHandler]:
        """Register handlers onto the PTB Application.

        Args:
            application: PTB Application instance.

        Returns:
            List of registered BaseHandler instances.
        """
        ...