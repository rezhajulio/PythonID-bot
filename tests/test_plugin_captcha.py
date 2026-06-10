"""Tests for the captcha plugin handler registration."""
from unittest.mock import MagicMock, patch

from bot.plugins.builtin.captcha import register_captcha


def test_register_captcha_clones_handlers():
    """Test that register_captcha clones handlers before wrapping."""
    mock_app = MagicMock()

    # Create fixed handler objects that get_handlers will return
    handler1 = MagicMock()
    handler1.callback = MagicMock()
    handler2 = MagicMock()
    handler2.callback = MagicMock()
    fixed_handlers = [handler1, handler2]

    with patch("bot.plugins.builtin.captcha.captcha.get_handlers", return_value=fixed_handlers):
        registered = register_captcha(mock_app)

    # Registered handlers must be different objects (cloned)
    for reg in registered:
        assert reg is not handler1 and reg is not handler2, (
            "Handler should be cloned, not original"
        )


def test_register_captcha_does_not_mutate_original_handlers():
    """Test that register_captcha clones handlers instead of mutating originals."""
    mock_app = MagicMock()

    # Create fixed handler objects
    handler1 = MagicMock()
    original_cb1 = handler1.callback
    handler2 = MagicMock()
    original_cb2 = handler2.callback
    fixed_handlers = [handler1, handler2]

    with patch("bot.plugins.builtin.captcha.captcha.get_handlers", return_value=fixed_handlers):
        register_captcha(mock_app)

    # Original handler callbacks must be unchanged
    assert handler1.callback is original_cb1, "Original handler callback should not be mutated"
    assert handler2.callback is original_cb2, "Original handler callback should not be mutated"
