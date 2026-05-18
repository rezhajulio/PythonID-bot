"""Tests for the duplicate message spam detection handler."""

from collections import deque
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Message, User
from telegram.ext import ApplicationHandlerStop

from bot.group_config import GroupConfig
from bot.handlers.duplicate_spam import (
    RecentMessage,
    _get_recent_messages,
    _prune_old_messages,
    count_similar_in_window,
    handle_duplicate_spam,
    is_similar,
    normalize_text,
    RECENT_MESSAGES_KEY,
)

DEFAULT_SIMILARITY = 0.95


class TestNormalizeText:
    """Tests for the normalize_text function."""

    def test_lowercase(self):
        assert normalize_text("Hello World") == "hello world"

    def test_collapse_whitespace(self):
        assert normalize_text("hello   world") == "hello world"

    def test_strip_punctuation(self):
        assert normalize_text("hello, world!") == "hello world"

    def test_strip_emoji(self):
        result = normalize_text("hello 🙏")
        assert result.strip() == "hello"

    def test_unicode_normalization(self):
        result = normalize_text("ﬁnd")
        assert result == "find"

    def test_multiline(self):
        result = normalize_text("line one\nline two\nline three")
        assert result == "line one line two line three"

    def test_empty_string(self):
        assert normalize_text("") == ""


class TestIsSimilar:
    """Tests for the is_similar function."""

    def test_exact_match(self):
        assert is_similar("hello world", "hello world") is True

    def test_very_similar(self):
        a = "barangkali di sini ada yang sedang mencari kerja"
        b = "barangkali di sini ada yang sedang mencari kerja"
        assert is_similar(a, b) is True

    def test_different_texts(self):
        assert is_similar("hello world", "goodbye universe") is False

    def test_slightly_different(self):
        a = "barangkali di sini ada yang sedang mencari kerja bisa menghubungi saya kak"
        b = "barangkali di sini ada yang sedang mencari kerja bisa menghubungi saya ya"
        assert is_similar(a, b) is True

    def test_completely_different(self):
        a = "python is great for data science"
        b = "javascript is used for web development"
        assert is_similar(a, b) is False


class TestPruneOldMessages:
    """Tests for the _prune_old_messages function."""

    def test_removes_old_messages(self):
        now = datetime.now(UTC)
        dq = deque([
            RecentMessage(timestamp=now - timedelta(seconds=200), normalized_text="old", message_id=1),
            RecentMessage(timestamp=now - timedelta(seconds=50), normalized_text="recent", message_id=2),
        ])
        _prune_old_messages(dq, 120, now)
        assert len(dq) == 1
        assert dq[0].normalized_text == "recent"

    def test_keeps_all_within_window(self):
        now = datetime.now(UTC)
        dq = deque([
            RecentMessage(timestamp=now - timedelta(seconds=60), normalized_text="a", message_id=1),
            RecentMessage(timestamp=now - timedelta(seconds=30), normalized_text="b", message_id=2),
        ])
        _prune_old_messages(dq, 120, now)
        assert len(dq) == 2

    def test_empty_deque(self):
        dq: deque[RecentMessage] = deque()
        _prune_old_messages(dq, 120, datetime.now(UTC))
        assert len(dq) == 0


class TestCountSimilarInWindow:
    """Tests for the count_similar_in_window function."""

    def test_counts_similar(self):
        dq = deque([
            RecentMessage(timestamp=datetime.now(UTC), normalized_text="spam message here", message_id=1),
            RecentMessage(timestamp=datetime.now(UTC), normalized_text="spam message here", message_id=2),
            RecentMessage(timestamp=datetime.now(UTC), normalized_text="different message", message_id=3),
        ])
        assert count_similar_in_window(dq, "spam message here") == 2

    def test_no_similar(self):
        dq = deque([
            RecentMessage(timestamp=datetime.now(UTC), normalized_text="hello world foo bar", message_id=1),
        ])
        assert count_similar_in_window(dq, "completely different text here") == 0


class TestGetRecentMessages:
    """Tests for the _get_recent_messages function."""

    def test_creates_new_deque(self):
        context = MagicMock()
        context.bot_data = {}
        dq = _get_recent_messages(context, -100, 42)
        assert isinstance(dq, deque)
        assert len(dq) == 0

    def test_returns_existing_deque(self):
        context = MagicMock()
        existing_dq = deque()
        existing_dq.append(
            RecentMessage(timestamp=datetime.now(UTC), normalized_text="test", message_id=1)
        )
        context.bot_data = {RECENT_MESSAGES_KEY: {(-100, 42): existing_dq}}
        dq = _get_recent_messages(context, -100, 42)
        assert len(dq) == 1


class TestHandleDuplicateSpam:
    """Tests for the handle_duplicate_spam handler."""

    @pytest.fixture
    def group_config(self):
        return GroupConfig(
            group_id=-100,
            warning_topic_id=999,
            duplicate_spam_enabled=True,
            duplicate_spam_window_seconds=120,
            duplicate_spam_threshold=2,
            duplicate_spam_min_length=20,
        )

    @pytest.fixture
    def mock_update(self):
        update = MagicMock()
        update.message = MagicMock(spec=Message)
        update.message.from_user = MagicMock(spec=User)
        update.message.from_user.id = 42
        update.message.from_user.is_bot = False
        update.message.from_user.full_name = "Test User"
        update.message.from_user.username = "testuser"
        update.message.text = "Barangkali di sini ada yang sedang mencari kerja bisa menghubungi saya"
        update.message.caption = None
        update.message.message_id = 100
        update.message.delete = AsyncMock()
        update.effective_chat = MagicMock(spec=Chat)
        update.effective_chat.id = -100
        return update

    @pytest.fixture
    def mock_context(self):
        context = MagicMock()
        context.bot_data = {"group_admin_ids": {-100: [1, 2]}}
        context.bot = MagicMock()
        context.bot.restrict_chat_member = AsyncMock()
        context.bot.send_message = AsyncMock()
        return context

    async def test_skips_no_message(self, mock_context, group_config):
        update = MagicMock()
        update.message = None
        with patch("bot.handlers.duplicate_spam.get_group_config_for_update", return_value=group_config):
            await handle_duplicate_spam(update, mock_context)

    async def test_skips_no_user(self, mock_context, group_config):
        update = MagicMock()
        update.message = MagicMock(spec=Message)
        update.message.from_user = None
        with patch("bot.handlers.duplicate_spam.get_group_config_for_update", return_value=group_config):
            await handle_duplicate_spam(update, mock_context)

    async def test_skips_unmonitored_group(self, mock_update, mock_context):
        with patch("bot.handlers.duplicate_spam.get_group_config_for_update", return_value=None):
            await handle_duplicate_spam(mock_update, mock_context)
        mock_update.message.delete.assert_not_called()

    async def test_skips_when_disabled(self, mock_update, mock_context, group_config):
        group_config.duplicate_spam_enabled = False
        with patch("bot.handlers.duplicate_spam.get_group_config_for_update", return_value=group_config):
            await handle_duplicate_spam(mock_update, mock_context)
        mock_update.message.delete.assert_not_called()

    async def test_skips_bots(self, mock_update, mock_context, group_config):
        mock_update.message.from_user.is_bot = True
        with patch("bot.handlers.duplicate_spam.get_group_config_for_update", return_value=group_config):
            await handle_duplicate_spam(mock_update, mock_context)
        mock_update.message.delete.assert_not_called()

    async def test_skips_admins(self, mock_update, mock_context, group_config):
        mock_update.message.from_user.id = 1  # admin
        with patch("bot.handlers.duplicate_spam.get_group_config_for_update", return_value=group_config):
            await handle_duplicate_spam(mock_update, mock_context)
        mock_update.message.delete.assert_not_called()

    async def test_skips_trusted_users(self, mock_update, mock_context, group_config):
        now = datetime.now(UTC)
        norm = normalize_text(mock_update.message.text)
        existing_dq = deque([
            RecentMessage(timestamp=now, normalized_text=norm, message_id=99),
        ])
        mock_context.bot_data[RECENT_MESSAGES_KEY] = {(-100, 42): existing_dq}
        mock_context.bot_data["trusted_user_ids"] = {mock_update.message.from_user.id}

        with (
            patch(
                "bot.handlers.duplicate_spam.get_group_config_for_update",
                return_value=group_config,
            ),
            patch("bot.services.telegram_utils.get_database") as mock_get_db,
        ):
            await handle_duplicate_spam(mock_update, mock_context)

        mock_update.message.delete.assert_not_called()
        mock_context.bot.restrict_chat_member.assert_not_called()
        # Trusted cache hit must not trigger any DB call.
        mock_get_db.assert_not_called()

    async def test_admin_bypass_does_not_query_database(
        self, mock_update, mock_context, group_config
    ):
        """Admin cache hit must not perform any DB lookup."""
        mock_update.message.from_user.id = 1  # already in group_admin_ids
        mock_context.bot_data["trusted_user_ids"] = set()

        with (
            patch(
                "bot.handlers.duplicate_spam.get_group_config_for_update",
                return_value=group_config,
            ),
            patch("bot.services.telegram_utils.get_database") as mock_get_db,
        ):
            await handle_duplicate_spam(mock_update, mock_context)

        mock_update.message.delete.assert_not_called()
        mock_get_db.assert_not_called()

    async def test_skips_no_text(self, mock_update, mock_context, group_config):
        mock_update.message.text = None
        mock_update.message.caption = None
        with patch("bot.handlers.duplicate_spam.get_group_config_for_update", return_value=group_config):
            await handle_duplicate_spam(mock_update, mock_context)
        mock_update.message.delete.assert_not_called()

    async def test_skips_short_text(self, mock_update, mock_context, group_config):
        mock_update.message.text = "ok"
        with patch("bot.handlers.duplicate_spam.get_group_config_for_update", return_value=group_config):
            await handle_duplicate_spam(mock_update, mock_context)
        mock_update.message.delete.assert_not_called()

    async def test_first_message_no_action(self, mock_update, mock_context, group_config):
        with patch("bot.handlers.duplicate_spam.get_group_config_for_update", return_value=group_config):
            await handle_duplicate_spam(mock_update, mock_context)
        mock_update.message.delete.assert_not_called()

    async def test_second_message_triggers_restriction(self, mock_update, mock_context, group_config):
        now = datetime.now(UTC)
        norm = normalize_text(mock_update.message.text)
        existing_dq = deque([
            RecentMessage(timestamp=now, normalized_text=norm, message_id=99),
        ])
        mock_context.bot_data[RECENT_MESSAGES_KEY] = {(-100, 42): existing_dq}

        with patch("bot.handlers.duplicate_spam.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await handle_duplicate_spam(mock_update, mock_context)

        mock_update.message.delete.assert_called_once()
        mock_context.bot.restrict_chat_member.assert_called_once()
        mock_context.bot.send_message.assert_called_once()

    async def test_uses_caption_when_no_text(self, mock_update, mock_context, group_config):
        mock_update.message.text = None
        mock_update.message.caption = "Barangkali di sini ada yang sedang mencari kerja bisa menghubungi saya"
        now = datetime.now(UTC)
        norm = normalize_text(mock_update.message.caption)
        existing_dq = deque([
            RecentMessage(timestamp=now, normalized_text=norm, message_id=99),
        ])
        mock_context.bot_data[RECENT_MESSAGES_KEY] = {(-100, 42): existing_dq}

        with patch("bot.handlers.duplicate_spam.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await handle_duplicate_spam(mock_update, mock_context)

        mock_update.message.delete.assert_called_once()

    async def test_expired_messages_not_counted(self, mock_update, mock_context, group_config):
        old = datetime.now(UTC) - timedelta(seconds=200)
        norm = normalize_text(mock_update.message.text)
        existing_dq = deque([
            RecentMessage(timestamp=old, normalized_text=norm, message_id=99),
        ])
        mock_context.bot_data[RECENT_MESSAGES_KEY] = {(-100, 42): existing_dq}

        with patch("bot.handlers.duplicate_spam.get_group_config_for_update", return_value=group_config):
            await handle_duplicate_spam(mock_update, mock_context)

        mock_update.message.delete.assert_not_called()

    async def test_different_messages_not_counted(self, mock_update, mock_context, group_config):
        now = datetime.now(UTC)
        existing_dq = deque([
            RecentMessage(timestamp=now, normalized_text="some completely different text here one", message_id=98),
            RecentMessage(timestamp=now, normalized_text="another totally different text here two", message_id=99),
        ])
        mock_context.bot_data[RECENT_MESSAGES_KEY] = {(-100, 42): existing_dq}

        with patch("bot.handlers.duplicate_spam.get_group_config_for_update", return_value=group_config):
            await handle_duplicate_spam(mock_update, mock_context)

        mock_update.message.delete.assert_not_called()

    async def test_delete_failure_continues(self, mock_update, mock_context, group_config):
        mock_update.message.delete = AsyncMock(side_effect=Exception("Delete failed"))
        now = datetime.now(UTC)
        norm = normalize_text(mock_update.message.text)
        existing_dq = deque([
            RecentMessage(timestamp=now, normalized_text=norm, message_id=99),
        ])
        mock_context.bot_data[RECENT_MESSAGES_KEY] = {(-100, 42): existing_dq}

        with patch("bot.handlers.duplicate_spam.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await handle_duplicate_spam(mock_update, mock_context)

        mock_context.bot.restrict_chat_member.assert_called_once()

    async def test_restrict_failure_still_notifies(self, mock_update, mock_context, group_config):
        mock_context.bot.restrict_chat_member = AsyncMock(side_effect=Exception("Restrict failed"))
        now = datetime.now(UTC)
        norm = normalize_text(mock_update.message.text)
        existing_dq = deque([
            RecentMessage(timestamp=now, normalized_text=norm, message_id=99),
        ])
        mock_context.bot_data[RECENT_MESSAGES_KEY] = {(-100, 42): existing_dq}

        with patch("bot.handlers.duplicate_spam.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await handle_duplicate_spam(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args
        assert "dihapus" in call_kwargs.kwargs.get("text", call_kwargs[1].get("text", ""))

    async def test_notification_failure_still_raises_stop(self, mock_update, mock_context, group_config):
        mock_context.bot.send_message = AsyncMock(side_effect=Exception("Send failed"))
        now = datetime.now(UTC)
        norm = normalize_text(mock_update.message.text)
        existing_dq = deque([
            RecentMessage(timestamp=now, normalized_text=norm, message_id=99),
        ])
        mock_context.bot_data[RECENT_MESSAGES_KEY] = {(-100, 42): existing_dq}

        with patch("bot.handlers.duplicate_spam.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await handle_duplicate_spam(mock_update, mock_context)

    async def test_third_message_also_triggers(self, mock_update, mock_context, group_config):
        now = datetime.now(UTC)
        norm = normalize_text(mock_update.message.text)
        existing_dq = deque([
            RecentMessage(timestamp=now, normalized_text=norm, message_id=98),
            RecentMessage(timestamp=now, normalized_text=norm, message_id=99),
        ])
        mock_context.bot_data[RECENT_MESSAGES_KEY] = {(-100, 42): existing_dq}

        with patch("bot.handlers.duplicate_spam.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await handle_duplicate_spam(mock_update, mock_context)

        mock_update.message.delete.assert_called_once()
        mock_context.bot.restrict_chat_member.assert_called_once()
