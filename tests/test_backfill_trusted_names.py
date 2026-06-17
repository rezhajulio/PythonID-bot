"""Tests for scripts/backfill_trusted_names.py."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.backfill_trusted_names import _fetch_name


class TestFetchName:
    async def test_returns_name_and_username_on_success(self):
        bot = MagicMock()
        bot.get_chat = AsyncMock(
            return_value=MagicMock(full_name="Alice Example", username="alice_x")
        )

        full_name, username = await _fetch_name(bot, 12345)

        assert full_name == "Alice Example"
        assert username == "alice_x"

    async def test_returns_empty_string_when_full_name_is_none(self):
        """Account with privacy-restricted name visibility returns full_name=None."""
        bot = MagicMock()
        bot.get_chat = AsyncMock(
            return_value=MagicMock(full_name=None, username="anon")
        )

        full_name, username = await _fetch_name(bot, 12345)

        assert full_name == ""
        assert username == "anon"

    async def test_returns_empty_tuple_on_exception(self):
        """T2 fix: on error, return ('', None) so the column stays clean."""
        bot = MagicMock()
        bot.get_chat = AsyncMock(side_effect=Exception("Forbidden: bot was blocked"))

        full_name, username = await _fetch_name(bot, 12345)

        assert full_name == ""
        assert username is None

    @pytest.mark.parametrize("exc", [Exception("network"), TimeoutError(), ValueError("x")])
    async def test_swallows_all_exception_types(self, exc):
        """Per-record isolation: any exception in get_chat must not propagate."""
        bot = MagicMock()
        bot.get_chat = AsyncMock(side_effect=exc)

        # Must not raise.
        result = await _fetch_name(bot, 12345)

        assert result == ("", None)
