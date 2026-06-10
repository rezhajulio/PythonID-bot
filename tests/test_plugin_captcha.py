"""Tests for the captcha plugin handler registration."""
from unittest.mock import MagicMock, patch

from bot.plugins.builtin.captcha import register_captcha


class _FakeHandler:
    """Minimal stub with a real callback attribute for copy.copy testing."""

    def __init__(self):
        self.callback = lambda update, context: None


def test_register_captcha_clones_handlers():
    """Test that register_captcha clones handlers before wrapping."""
    mock_app = MagicMock()

    handler1 = _FakeHandler()
    handler2 = _FakeHandler()
    original_id1 = id(handler1)
    original_id2 = id(handler2)
    fixed_handlers = [handler1, handler2]

    with patch("bot.plugins.builtin.captcha.captcha.get_handlers", return_value=fixed_handlers):
        registered = register_captcha(mock_app)

    # Registered handlers must be different objects (cloned)
    for reg in registered:
        assert id(reg) != original_id1 and id(reg) != original_id2, (
            "Handler should be cloned, not original"
        )
    # Cloned callback must be wrapped (different from original)
    assert registered[0].callback is not handler1.callback
    assert registered[1].callback is not handler2.callback


def test_register_captcha_does_not_mutate_original_handlers():
    """Test that register_captcha clones handlers instead of mutating originals."""
    mock_app = MagicMock()

    handler1 = _FakeHandler()
    handler2 = _FakeHandler()
    original_cb1 = handler1.callback
    original_cb2 = handler2.callback
    fixed_handlers = [handler1, handler2]

    with patch("bot.plugins.builtin.captcha.captcha.get_handlers", return_value=fixed_handlers):
        register_captcha(mock_app)

    # Original handler callbacks must be unchanged
    assert handler1.callback is original_cb1, "Original handler callback should not be mutated"
    assert handler2.callback is original_cb2, "Original handler callback should not be mutated"
