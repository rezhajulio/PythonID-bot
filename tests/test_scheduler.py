"""
Tests for the scheduler service.

Tests the auto-restriction job and JobQueue integration.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.constants import ChatMemberStatus

from bot.database.models import UserWarning
from bot.group_config import GroupConfig, GroupRegistry
from bot.services.scheduler import auto_restrict_expired_warnings


@pytest.fixture
def group_config():
    return GroupConfig(
        group_id=-100999,
        warning_topic_id=123,
        warning_time_threshold_minutes=180,
        rules_link="https://example.com/rules",
    )


@pytest.fixture
def mock_registry(group_config):
    registry = GroupRegistry()
    registry.register(group_config)
    return registry


class TestAutoRestrictExpiredWarnings:
    @pytest.mark.asyncio
    async def test_restricts_expired_warnings(self, mock_registry):
        """Test that expired warnings are restricted."""
        # Mock database with expired warning
        mock_warning = UserWarning(
            id=1,
            user_id=123,
            group_id=-100999,
            message_count=1,
            first_warned_at=datetime.now(UTC) - timedelta(hours=4),
            last_message_at=datetime.now(UTC),
            is_restricted=False,
            restricted_by_bot=False,
        )

        mock_db = MagicMock()
        mock_db.get_warnings_past_time_threshold_for_group.return_value = [mock_warning]
        mock_db.mark_user_restricted = MagicMock()

        # Mock bot
        mock_bot = AsyncMock()
        mock_bot.restrict_chat_member = AsyncMock()
        mock_bot.send_message = AsyncMock()

        # Mock context (JobQueue context)
        mock_context = MagicMock()
        mock_context.bot = mock_bot

        with patch("bot.services.scheduler.get_database", return_value=mock_db):
            with patch("bot.services.scheduler.get_group_registry", return_value=mock_registry):
                with patch(
                    "bot.services.scheduler.BotInfoCache.get_username",
                    new_callable=AsyncMock,
                    return_value="test_bot",
                ):
                    await auto_restrict_expired_warnings(mock_context)

        # Verify restriction was applied
        mock_bot.restrict_chat_member.assert_called_once()
        call_args = mock_bot.restrict_chat_member.call_args
        assert call_args.kwargs["chat_id"] == -100999
        assert call_args.kwargs["user_id"] == 123

        # Verify database was updated
        mock_db.mark_user_restricted.assert_called_once_with(123, -100999)

        # Verify notification was sent
        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        assert call_args.kwargs["chat_id"] == -100999
        assert call_args.kwargs["message_thread_id"] == 123
        assert "dibatasi" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_handles_no_expired_warnings(self, mock_registry):
        """Test that function handles empty list gracefully."""
        mock_db = MagicMock()
        mock_db.get_warnings_past_time_threshold_for_group.return_value = []

        mock_bot = AsyncMock()
        mock_context = MagicMock()
        mock_context.bot = mock_bot

        with patch("bot.services.scheduler.get_database", return_value=mock_db):
            with patch("bot.services.scheduler.get_group_registry", return_value=mock_registry):
                with patch(
                    "bot.services.scheduler.BotInfoCache.get_username",
                    new_callable=AsyncMock,
                    return_value="test_bot",
                ):
                    await auto_restrict_expired_warnings(mock_context)

        # Should not call restrict or send message
        mock_bot.restrict_chat_member.assert_not_called()
        mock_bot.send_message.assert_not_called()

        # Should have queried once for the single group in registry
        mock_db.get_warnings_past_time_threshold_for_group.assert_called_once_with(
            -100999, timedelta(minutes=180)
        )

    @pytest.mark.asyncio
    async def test_restricts_multiple_expired_warnings(self, mock_registry):
        """Test that multiple expired warnings are processed."""
        mock_warnings = [
            UserWarning(
                id=1,
                user_id=123,
                group_id=-100999,
                message_count=1,
                first_warned_at=datetime.now(UTC) - timedelta(hours=4),
                last_message_at=datetime.now(UTC),
                is_restricted=False,
                restricted_by_bot=False,
            ),
            UserWarning(
                id=2,
                user_id=456,
                group_id=-100999,
                message_count=1,
                first_warned_at=datetime.now(UTC) - timedelta(hours=5),
                last_message_at=datetime.now(UTC),
                is_restricted=False,
                restricted_by_bot=False,
            ),
        ]

        mock_db = MagicMock()
        mock_db.get_warnings_past_time_threshold_for_group.return_value = mock_warnings
        mock_db.mark_user_restricted = MagicMock()

        mock_bot = AsyncMock()
        mock_bot.restrict_chat_member = AsyncMock()
        mock_bot.send_message = AsyncMock()

        mock_context = MagicMock()
        mock_context.bot = mock_bot

        with patch("bot.services.scheduler.get_database", return_value=mock_db):
            with patch("bot.services.scheduler.get_group_registry", return_value=mock_registry):
                with patch(
                    "bot.services.scheduler.BotInfoCache.get_username",
                    new_callable=AsyncMock,
                    return_value="test_bot",
                ):
                    await auto_restrict_expired_warnings(mock_context)

        # Verify both users were restricted
        assert mock_bot.restrict_chat_member.call_count == 2
        assert mock_db.mark_user_restricted.call_count == 2
        assert mock_bot.send_message.call_count == 2

    @pytest.mark.asyncio
    async def test_handles_restriction_errors(self, mock_registry):
        """Test that function handles errors gracefully."""
        mock_warning = UserWarning(
            id=1,
            user_id=123,
            group_id=-100999,
            message_count=1,
            first_warned_at=datetime.now(UTC) - timedelta(hours=4),
            last_message_at=datetime.now(UTC),
            is_restricted=False,
            restricted_by_bot=False,
        )

        mock_db = MagicMock()
        mock_db.get_warnings_past_time_threshold_for_group.return_value = [mock_warning]

        mock_bot = AsyncMock()
        mock_bot.restrict_chat_member = AsyncMock(side_effect=Exception("API error"))

        mock_context = MagicMock()
        mock_context.bot = mock_bot

        with patch("bot.services.scheduler.get_database", return_value=mock_db):
            with patch("bot.services.scheduler.get_group_registry", return_value=mock_registry):
                with patch(
                    "bot.services.scheduler.BotInfoCache.get_username",
                    new_callable=AsyncMock,
                    return_value="test_bot",
                ):
                    # Should not raise, but log the error
                    await auto_restrict_expired_warnings(mock_context)

        # Verify restriction was attempted
        mock_bot.restrict_chat_member.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_correct_time_threshold(self):
        """Test that the correct time threshold from group config is used."""
        # Create a group config with a different threshold
        custom_group_config = GroupConfig(
            group_id=-100999,
            warning_topic_id=123,
            warning_time_threshold_minutes=300,
            rules_link="https://example.com/rules",
        )
        custom_registry = GroupRegistry()
        custom_registry.register(custom_group_config)

        mock_db = MagicMock()
        mock_db.get_warnings_past_time_threshold_for_group.return_value = []

        mock_bot = AsyncMock()
        mock_context = MagicMock()
        mock_context.bot = mock_bot

        with patch("bot.services.scheduler.get_database", return_value=mock_db):
            with patch("bot.services.scheduler.get_group_registry", return_value=custom_registry):
                with patch(
                    "bot.services.scheduler.BotInfoCache.get_username",
                    new_callable=AsyncMock,
                    return_value="test_bot",
                ):
                    await auto_restrict_expired_warnings(mock_context)

        # Verify correct group_id and threshold were passed to database query
        mock_db.get_warnings_past_time_threshold_for_group.assert_called_once_with(
            -100999, timedelta(minutes=300)
        )

    @pytest.mark.asyncio
    async def test_skips_kicked_user_and_deletes_warning(self, mock_registry):
        """Test that kicked users have their warning deleted so they don't reappear."""
        mock_warning = UserWarning(
            id=1,
            user_id=123,
            group_id=-100999,
            message_count=1,
            first_warned_at=datetime.now(UTC) - timedelta(hours=4),
            last_message_at=datetime.now(UTC),
            is_restricted=False,
            restricted_by_bot=False,
        )

        mock_db = MagicMock()
        mock_db.get_warnings_past_time_threshold_for_group.return_value = [mock_warning]
        mock_db.delete_user_warnings = MagicMock()

        mock_bot = AsyncMock()
        mock_bot.restrict_chat_member = AsyncMock()
        mock_bot.send_message = AsyncMock()

        mock_context = MagicMock()
        mock_context.bot = mock_bot

        with patch("bot.services.scheduler.get_database", return_value=mock_db):
            with patch("bot.services.scheduler.get_group_registry", return_value=mock_registry):
                with patch(
                    "bot.services.scheduler.BotInfoCache.get_username",
                    new_callable=AsyncMock,
                    return_value="test_bot",
                ):
                    with patch(
                        "bot.services.scheduler.get_user_status",
                        new_callable=AsyncMock,
                        return_value=ChatMemberStatus.BANNED,
                    ):
                        await auto_restrict_expired_warnings(mock_context)

        # Verify warning was deleted (not just marked unrestricted)
        mock_db.delete_user_warnings.assert_called_once_with(123, -100999)

        # Verify restriction was NOT applied
        mock_bot.restrict_chat_member.assert_not_called()
        mock_bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_kicked_user_not_in_subsequent_queries(self, mock_registry):
        """Test that deleted warnings don't appear in subsequent threshold queries."""
        mock_warning = UserWarning(
            id=1,
            user_id=123,
            group_id=-100999,
            message_count=1,
            first_warned_at=datetime.now(UTC) - timedelta(hours=4),
            last_message_at=datetime.now(UTC),
            is_restricted=False,
            restricted_by_bot=False,
        )

        # Track calls to simulate deletion effect
        call_count = 0

        def get_warnings_side_effect(group_id, threshold):
            nonlocal call_count
            call_count += 1
            # First call returns the warning, subsequent calls return empty
            # (simulating that delete_user_warnings removed it)
            if call_count == 1:
                return [mock_warning]
            return []

        mock_db = MagicMock()
        mock_db.get_warnings_past_time_threshold_for_group.side_effect = get_warnings_side_effect
        mock_db.delete_user_warnings = MagicMock()

        mock_bot = AsyncMock()
        mock_bot.restrict_chat_member = AsyncMock()
        mock_bot.send_message = AsyncMock()

        mock_context = MagicMock()
        mock_context.bot = mock_bot

        with patch("bot.services.scheduler.get_database", return_value=mock_db):
            with patch("bot.services.scheduler.get_group_registry", return_value=mock_registry):
                with patch(
                    "bot.services.scheduler.BotInfoCache.get_username",
                    new_callable=AsyncMock,
                    return_value="test_bot",
                ):
                    with patch(
                        "bot.services.scheduler.get_user_status",
                        new_callable=AsyncMock,
                        return_value=ChatMemberStatus.BANNED,
                    ):
                        # First run - should process and delete warning
                        await auto_restrict_expired_warnings(mock_context)
                        # Second run - should find no warnings
                        await auto_restrict_expired_warnings(mock_context)

        # Verify delete was called exactly once (first run only)
        mock_db.delete_user_warnings.assert_called_once_with(123, -100999)
        # Verify the query was called twice (once per run, one group each)
        assert mock_db.get_warnings_past_time_threshold_for_group.call_count == 2

    @pytest.mark.asyncio
    async def test_handles_get_chat_member_failure(self, mock_registry):
        """Test fallback user mention when get_chat_member fails."""
        mock_warning = UserWarning(
            id=1,
            user_id=123,
            group_id=-100999,
            message_count=1,
            first_warned_at=datetime.now(UTC) - timedelta(hours=4),
            last_message_at=datetime.now(UTC),
            is_restricted=False,
            restricted_by_bot=False,
        )

        mock_db = MagicMock()
        mock_db.get_warnings_past_time_threshold_for_group.return_value = [mock_warning]
        mock_db.mark_user_restricted = MagicMock()

        mock_bot = AsyncMock()
        mock_bot.restrict_chat_member = AsyncMock()
        mock_bot.send_message = AsyncMock()
        # Make get_chat_member raise an exception
        mock_bot.get_chat_member = AsyncMock(side_effect=Exception("User not found"))

        mock_context = MagicMock()
        mock_context.bot = mock_bot

        with patch("bot.services.scheduler.get_database", return_value=mock_db):
            with patch("bot.services.scheduler.get_group_registry", return_value=mock_registry):
                with patch(
                    "bot.services.scheduler.get_user_status",
                    new_callable=AsyncMock,
                    return_value=ChatMemberStatus.MEMBER,
                ):
                    with patch(
                        "bot.services.scheduler.BotInfoCache.get_username",
                        new_callable=AsyncMock,
                        return_value="test_bot",
                    ):
                        await auto_restrict_expired_warnings(mock_context)

        # Verify restriction was applied
        mock_bot.restrict_chat_member.assert_called_once()

        # Verify notification was sent with fallback user mention
        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        assert "User 123" in call_args.kwargs["text"]
