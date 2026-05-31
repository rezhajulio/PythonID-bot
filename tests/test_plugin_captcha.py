"""Tests for the captcha plugin handler registration."""
from unittest.mock import MagicMock, patch

from bot.plugins.builtin.captcha import register_captcha
from bot.handlers.captcha import get_handlers


def test_register_captcha_clones_handlers():
    """Test that register_captcha clones handlers before wrapping."""
    mock_app = MagicMock()

    # Track original handler objects
    original_handlers = get_handlers()
    original_ids = [id(h) for h in original_handlers]

    # Register - should clone, not mutate originals
    registered = register_captcha(mock_app)

    # Registered handlers should be different objects than originals
    for reg, orig_id in zip(registered, original_ids):
        assert id(reg) != orig_id, "Handler should be cloned, not original"

    # Verify wrappers were applied to clones
    for reg in registered:
        # The callback should be wrapped (guard_plugin wrapper)
        assert reg.callback is not None


def test_register_captcha_does_not_mutate_original_handlers():
    """Test that register_captcha clones handlers instead of mutating originals."""
    mock_app = MagicMock()

    # Get fresh handlers to capture original callbacks
    original_handlers = get_handlers()
    original_callbacks = [h.callback for h in original_handlers]

    # Register - should not affect original handler objects
    register_captcha(mock_app)

    # Original handler objects should still have their original callbacks
    for h, orig_cb in zip(original_handlers, original_callbacks):
        assert h.callback is orig_cb, "Original handler callback should not be mutated"
