"""
Tests for the constants module.

Tests utility functions like format_threshold_display.
"""

from bot.constants import format_threshold_display


class TestFormatThresholdDisplay:
    def test_formats_hours_when_threshold_is_60_or_more(self):
        """Test that threshold >= 60 minutes is formatted as hours."""
        assert format_threshold_display(60) == "1 jam"
        assert format_threshold_display(120) == "2 jam"
        assert format_threshold_display(180) == "3 jam"
        assert format_threshold_display(300) == "5 jam"

    def test_formats_minutes_when_threshold_is_less_than_60(self):
        """Test that threshold < 60 minutes is formatted as minutes."""
        assert format_threshold_display(30) == "30 menit"
        assert format_threshold_display(45) == "45 menit"
        assert format_threshold_display(1) == "1 menit"
        assert format_threshold_display(59) == "59 menit"
