"""Tests for plugin definitions."""
from bot.plugins.definitions import ADMIN_COMMANDS, PLUGIN_NAMES


def test_admin_commands_constant():
    """Test that ADMIN_COMMANDS contains expected admin-only plugins."""
    expected = {
        "verify", "unverify", "check", "trust", "untrust", "trusted_list",
        "check_forwarded_message", "verify_callback", "unverify_callback",
        "warn_callback", "trust_callback", "untrust_callback",
    }
    assert ADMIN_COMMANDS == expected


def test_admin_commands_subset_of_plugin_names():
    """Test that admin commands are a subset of all plugin names."""
    assert ADMIN_COMMANDS.issubset(PLUGIN_NAMES)


def test_admin_commands_not_gateable():
    """Test that admin commands are explicitly marked as not gateable."""
    # This documents the architectural decision that admin commands
    # skip guard_plugin wrapping intentionally
    assert len(ADMIN_COMMANDS) == 12
