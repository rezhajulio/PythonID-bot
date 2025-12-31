"""Tests for the anti-spam handler."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Message, MessageEntity, User

from bot.handlers.anti_spam import (
    extract_urls,
    handle_new_user_spam,
    has_external_reply,
    has_link,
    has_non_whitelisted_link,
    is_forwarded,
    is_url_whitelisted,
)


class TestIsForwarded:
    """Tests for the is_forwarded helper function."""

    def test_forward_origin_is_forwarded(self):
        """Test that message with forward_origin is detected as forwarded."""
        msg = MagicMock(spec=Message)
        msg.forward_origin = MagicMock()  # Any non-None value indicates forwarded

        assert is_forwarded(msg) is True

    def test_regular_message_not_forwarded(self):
        """Test that regular message is not detected as forwarded."""
        msg = MagicMock(spec=Message)
        msg.forward_origin = None

        assert is_forwarded(msg) is False


class TestHasLink:
    """Tests for the has_link helper function."""

    def test_url_entity_detected(self):
        """Test that URL entity is detected."""
        entity = MagicMock(spec=MessageEntity)
        entity.type = MessageEntity.URL

        msg = MagicMock(spec=Message)
        msg.entities = [entity]
        msg.caption_entities = None

        assert has_link(msg) is True

    def test_text_link_entity_detected(self):
        """Test that TEXT_LINK entity is detected."""
        entity = MagicMock(spec=MessageEntity)
        entity.type = MessageEntity.TEXT_LINK

        msg = MagicMock(spec=Message)
        msg.entities = [entity]
        msg.caption_entities = None

        assert has_link(msg) is True

    def test_caption_link_detected(self):
        """Test that link in caption is detected."""
        entity = MagicMock(spec=MessageEntity)
        entity.type = MessageEntity.URL

        msg = MagicMock(spec=Message)
        msg.entities = None
        msg.caption_entities = [entity]

        assert has_link(msg) is True

    def test_no_link_returns_false(self):
        """Test that message without links returns False."""
        msg = MagicMock(spec=Message)
        msg.entities = None
        msg.caption_entities = None

        assert has_link(msg) is False

    def test_other_entity_not_link(self):
        """Test that non-link entities are not detected as links."""
        entity = MagicMock(spec=MessageEntity)
        entity.type = MessageEntity.BOLD

        msg = MagicMock(spec=Message)
        msg.entities = [entity]
        msg.caption_entities = None

        assert has_link(msg) is False


class TestHasExternalReply:
    """Tests for the has_external_reply helper function."""

    def test_external_reply_detected(self):
        """Test that message with external_reply is detected."""
        msg = MagicMock(spec=Message)
        msg.external_reply = MagicMock()  # Any non-None value

        assert has_external_reply(msg) is True

    def test_no_external_reply_returns_false(self):
        """Test that message without external_reply returns False."""
        msg = MagicMock(spec=Message)
        msg.external_reply = None

        assert has_external_reply(msg) is False


class TestUrlWhitelist:
    """Tests for URL whitelist functionality."""

    def test_github_url_is_whitelisted(self):
        """Test that GitHub URLs are whitelisted."""
        assert is_url_whitelisted("https://github.com/user/repo") is True

    def test_subdomain_is_whitelisted(self):
        """Test that subdomains of whitelisted domains are allowed."""
        assert is_url_whitelisted("https://www.github.com/user/repo") is True
        assert is_url_whitelisted("https://gist.github.com/user/123") is True

    def test_pypi_url_is_whitelisted(self):
        """Test that PyPI URLs are whitelisted."""
        assert is_url_whitelisted("https://pypi.org/project/requests/") is True

    def test_stackoverflow_url_is_whitelisted(self):
        """Test that StackOverflow URLs are whitelisted."""
        assert is_url_whitelisted("https://stackoverflow.com/questions/123") is True

    def test_random_url_not_whitelisted(self):
        """Test that random URLs are not whitelisted."""
        assert is_url_whitelisted("https://some-spam-site.com/scam") is False

    def test_case_insensitive_matching(self):
        """Test that URL matching is case-insensitive."""
        assert is_url_whitelisted("https://GITHUB.COM/user/repo") is True

    def test_malicious_lookalike_not_whitelisted(self):
        """Test that malicious lookalike domains are NOT whitelisted."""
        assert is_url_whitelisted("https://fake-github.com/user/repo") is False
        assert is_url_whitelisted("https://github.com.malware.site/scam") is False
        assert is_url_whitelisted("https://notgithub.com/user/repo") is False

    def test_url_without_scheme(self):
        """Test that URLs without scheme are handled."""
        assert is_url_whitelisted("github.com/user/repo") is True

    def test_url_with_port(self):
        """Test that URLs with port are handled."""
        assert is_url_whitelisted("https://github.com:443/user/repo") is True

    def test_deeply_nested_subdomain_whitelisted(self):
        """Test that deeply nested subdomains are whitelisted."""
        assert is_url_whitelisted("https://api.v2.docs.github.com/endpoint") is True
        assert is_url_whitelisted("https://a.b.c.d.stackoverflow.com/q/123") is True

    def test_partial_domain_not_whitelisted(self):
        """Test that partial domain matches are NOT whitelisted."""
        # "hub.com" is not in whitelist, even though "github.com" is
        assert is_url_whitelisted("https://hub.com/something") is False

    def test_empty_hostname_handled(self):
        """Test that empty/invalid hostnames are handled gracefully."""
        assert is_url_whitelisted("") is False
        assert is_url_whitelisted("https://") is False

    def test_malformed_url_exception_handled(self):
        """Test that exceptions during URL parsing are handled."""
        # This URL has an invalid character that may cause parsing issues
        assert is_url_whitelisted("\x00invalid") is False


class TestExtractUrls:
    """Tests for URL extraction."""

    def test_extracts_url_entity(self):
        """Test extracting URL from URL entity."""
        msg = MagicMock(spec=Message)
        msg.text = "Check https://github.com/repo"
        msg.caption = None
        entity = MagicMock(spec=MessageEntity)
        entity.type = MessageEntity.URL
        entity.offset = 6
        entity.length = 23
        msg.entities = [entity]
        msg.caption_entities = None

        urls = extract_urls(msg)
        assert "https://github.com/repo" in urls

    def test_extracts_text_link(self):
        """Test extracting URL from TEXT_LINK entity."""
        msg = MagicMock(spec=Message)
        msg.text = "Click here"
        msg.caption = None
        entity = MagicMock(spec=MessageEntity)
        entity.type = MessageEntity.TEXT_LINK
        entity.url = "https://example.com"
        msg.entities = [entity]
        msg.caption_entities = None

        urls = extract_urls(msg)
        assert "https://example.com" in urls

    def test_returns_empty_for_no_urls(self):
        """Test that empty list is returned when no URLs."""
        msg = MagicMock(spec=Message)
        msg.text = "Hello world"
        msg.caption = None
        msg.entities = None
        msg.caption_entities = None

        urls = extract_urls(msg)
        assert urls == []


class TestHasNonWhitelistedLink:
    """Tests for has_non_whitelisted_link function."""

    def test_whitelisted_url_returns_false(self):
        """Test that whitelisted URLs don't trigger violation."""
        msg = MagicMock(spec=Message)
        msg.text = "Check https://github.com/repo"
        msg.caption = None
        entity = MagicMock(spec=MessageEntity)
        entity.type = MessageEntity.URL
        entity.offset = 6
        entity.length = 23
        msg.entities = [entity]
        msg.caption_entities = None

        assert has_non_whitelisted_link(msg) is False

    def test_non_whitelisted_url_returns_true(self):
        """Test that non-whitelisted URLs trigger violation."""
        msg = MagicMock(spec=Message)
        msg.text = "Check https://spam-site.com/scam"
        msg.caption = None
        entity = MagicMock(spec=MessageEntity)
        entity.type = MessageEntity.URL
        entity.offset = 6
        entity.length = 27
        msg.entities = [entity]
        msg.caption_entities = None

        assert has_non_whitelisted_link(msg) is True

    def test_no_urls_returns_false(self):
        """Test that messages without URLs return False."""
        msg = MagicMock(spec=Message)
        msg.text = "Hello world"
        msg.caption = None
        msg.entities = None
        msg.caption_entities = None

        assert has_non_whitelisted_link(msg) is False


class TestHandleNewUserSpam:
    """Tests for the handle_new_user_spam handler."""

    @pytest.fixture
    def mock_update(self):
        """Create a mock update with a message."""
        update = MagicMock()
        update.message = MagicMock(spec=Message)
        update.message.from_user = MagicMock(spec=User)
        update.message.from_user.id = 12345
        update.message.from_user.is_bot = False
        update.message.from_user.full_name = "Test User"
        update.message.from_user.username = "testuser"
        update.effective_chat = MagicMock(spec=Chat)
        update.effective_chat.id = -100123456  # group_id from settings

        # Default: not forwarded, no links, no external reply
        update.message.forward_origin = None
        update.message.external_reply = None
        update.message.entities = None
        update.message.caption_entities = None
        update.message.text = None
        update.message.caption = None
        update.message.delete = AsyncMock()

        return update

    @pytest.fixture
    def mock_context(self):
        """Create a mock context."""
        context = MagicMock()
        context.bot = AsyncMock()
        context.bot.send_message = AsyncMock()
        context.bot.restrict_chat_member = AsyncMock()
        return context

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.group_id = -100123456
        settings.warning_topic_id = 123
        settings.rules_link = "https://example.com/rules"
        settings.new_user_probation_hours = 168
        settings.new_user_violation_threshold = 3
        return settings

    @pytest.mark.asyncio
    async def test_ignores_message_from_wrong_group(
        self, mock_update, mock_context, mock_settings
    ):
        """Test that messages from other groups are ignored."""
        mock_update.effective_chat.id = -999999  # Different group

        with patch("bot.handlers.anti_spam.get_settings", return_value=mock_settings):
            await handle_new_user_spam(mock_update, mock_context)

        mock_update.message.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_bot_messages(
        self, mock_update, mock_context, mock_settings
    ):
        """Test that bot messages are ignored."""
        mock_update.message.from_user.is_bot = True

        with patch("bot.handlers.anti_spam.get_settings", return_value=mock_settings):
            await handle_new_user_spam(mock_update, mock_context)

        mock_update.message.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_user_not_on_probation(
        self, mock_update, mock_context, mock_settings
    ):
        """Test that users without probation record are ignored."""
        mock_db = MagicMock()
        mock_db.get_new_user_probation.return_value = None

        with (
            patch("bot.handlers.anti_spam.get_settings", return_value=mock_settings),
            patch("bot.handlers.anti_spam.get_database", return_value=mock_db),
        ):
            await handle_new_user_spam(mock_update, mock_context)

        mock_update.message.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_naive_datetime_from_database(
        self, mock_update, mock_context, mock_settings
    ):
        """Test that naive datetimes from database are handled correctly."""
        mock_update.message.forward_origin = MagicMock()  # Trigger violation

        # Simulate naive datetime from SQLite (no tzinfo) - use current time to keep user on probation
        mock_record = MagicMock()
        now = datetime.now()  # naive datetime
        mock_record.joined_at = now  # Just joined, still on probation

        updated_record = MagicMock()
        updated_record.violation_count = 1

        mock_db = MagicMock()
        mock_db.get_new_user_probation.return_value = mock_record
        mock_db.increment_new_user_violation.return_value = updated_record

        with (
            patch("bot.handlers.anti_spam.get_settings", return_value=mock_settings),
            patch("bot.handlers.anti_spam.get_database", return_value=mock_db),
        ):
            # Should not raise TypeError
            await handle_new_user_spam(mock_update, mock_context)

        mock_update.message.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_clears_expired_probation(
        self, mock_update, mock_context, mock_settings
    ):
        """Test that expired probation is cleared and message is not deleted."""
        mock_record = MagicMock()
        mock_record.joined_at = datetime.now(UTC) - timedelta(hours=200)  # Expired

        mock_db = MagicMock()
        mock_db.get_new_user_probation.return_value = mock_record

        with (
            patch("bot.handlers.anti_spam.get_settings", return_value=mock_settings),
            patch("bot.handlers.anti_spam.get_database", return_value=mock_db),
        ):
            await handle_new_user_spam(mock_update, mock_context)

        mock_db.clear_new_user_probation.assert_called_once()
        mock_update.message.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_regular_message(
        self, mock_update, mock_context, mock_settings
    ):
        """Test that regular messages (no forward, no link) are ignored."""
        mock_record = MagicMock()
        mock_record.joined_at = datetime.now(UTC)  # Active probation

        mock_db = MagicMock()
        mock_db.get_new_user_probation.return_value = mock_record

        with (
            patch("bot.handlers.anti_spam.get_settings", return_value=mock_settings),
            patch("bot.handlers.anti_spam.get_database", return_value=mock_db),
        ):
            await handle_new_user_spam(mock_update, mock_context)

        mock_update.message.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_deletes_forwarded_message(
        self, mock_update, mock_context, mock_settings
    ):
        """Test that forwarded messages are deleted."""
        mock_update.message.forward_origin = MagicMock()  # Any non-None value

        mock_record = MagicMock()
        mock_record.joined_at = datetime.now(UTC)
        mock_record.violation_count = 0

        updated_record = MagicMock()
        updated_record.violation_count = 1

        mock_db = MagicMock()
        mock_db.get_new_user_probation.return_value = mock_record
        mock_db.increment_new_user_violation.return_value = updated_record

        with (
            patch("bot.handlers.anti_spam.get_settings", return_value=mock_settings),
            patch("bot.handlers.anti_spam.get_database", return_value=mock_db),
        ):
            await handle_new_user_spam(mock_update, mock_context)

        mock_update.message.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_deletes_message_with_non_whitelisted_link(
        self, mock_update, mock_context, mock_settings
    ):
        """Test that messages with non-whitelisted links are deleted."""
        entity = MagicMock(spec=MessageEntity)
        entity.type = MessageEntity.URL
        entity.offset = 6
        entity.length = 27
        mock_update.message.entities = [entity]
        mock_update.message.text = "Check https://spam-site.com/scam"

        mock_record = MagicMock()
        mock_record.joined_at = datetime.now(UTC)

        updated_record = MagicMock()
        updated_record.violation_count = 1

        mock_db = MagicMock()
        mock_db.get_new_user_probation.return_value = mock_record
        mock_db.increment_new_user_violation.return_value = updated_record

        with (
            patch("bot.handlers.anti_spam.get_settings", return_value=mock_settings),
            patch("bot.handlers.anti_spam.get_database", return_value=mock_db),
        ):
            await handle_new_user_spam(mock_update, mock_context)

        mock_update.message.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_allows_whitelisted_link(
        self, mock_update, mock_context, mock_settings
    ):
        """Test that messages with whitelisted links are allowed."""
        entity = MagicMock(spec=MessageEntity)
        entity.type = MessageEntity.URL
        entity.offset = 6
        entity.length = 23
        mock_update.message.entities = [entity]
        mock_update.message.text = "Check https://github.com/repo"

        mock_record = MagicMock()
        mock_record.joined_at = datetime.now(UTC)

        mock_db = MagicMock()
        mock_db.get_new_user_probation.return_value = mock_record

        with (
            patch("bot.handlers.anti_spam.get_settings", return_value=mock_settings),
            patch("bot.handlers.anti_spam.get_database", return_value=mock_db),
        ):
            await handle_new_user_spam(mock_update, mock_context)

        mock_update.message.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_warning_on_first_violation(
        self, mock_update, mock_context, mock_settings
    ):
        """Test that warning is sent on first violation."""
        mock_update.message.forward_origin = MagicMock()  # Any non-None value

        mock_record = MagicMock()
        mock_record.joined_at = datetime.now(UTC)

        updated_record = MagicMock()
        updated_record.violation_count = 1  # First violation

        mock_db = MagicMock()
        mock_db.get_new_user_probation.return_value = mock_record
        mock_db.increment_new_user_violation.return_value = updated_record

        with (
            patch("bot.handlers.anti_spam.get_settings", return_value=mock_settings),
            patch("bot.handlers.anti_spam.get_database", return_value=mock_db),
        ):
            await handle_new_user_spam(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_warning_on_second_violation(
        self, mock_update, mock_context, mock_settings
    ):
        """Test that no warning is sent on subsequent violations."""
        mock_update.message.forward_origin = MagicMock()  # Any non-None value

        mock_record = MagicMock()
        mock_record.joined_at = datetime.now(UTC)

        updated_record = MagicMock()
        updated_record.violation_count = 2  # Second violation

        mock_db = MagicMock()
        mock_db.get_new_user_probation.return_value = mock_record
        mock_db.increment_new_user_violation.return_value = updated_record

        with (
            patch("bot.handlers.anti_spam.get_settings", return_value=mock_settings),
            patch("bot.handlers.anti_spam.get_database", return_value=mock_db),
        ):
            await handle_new_user_spam(mock_update, mock_context)

        mock_context.bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_restricts_user_at_threshold(
        self, mock_update, mock_context, mock_settings
    ):
        """Test that user is restricted when reaching threshold."""
        mock_update.message.forward_origin = MagicMock()  # Any non-None value

        mock_record = MagicMock()
        mock_record.joined_at = datetime.now(UTC)

        updated_record = MagicMock()
        updated_record.violation_count = 3  # Threshold reached

        mock_db = MagicMock()
        mock_db.get_new_user_probation.return_value = mock_record
        mock_db.increment_new_user_violation.return_value = updated_record

        with (
            patch("bot.handlers.anti_spam.get_settings", return_value=mock_settings),
            patch("bot.handlers.anti_spam.get_database", return_value=mock_db),
        ):
            await handle_new_user_spam(mock_update, mock_context)

        mock_context.bot.restrict_chat_member.assert_called_once()

    @pytest.mark.asyncio
    async def test_sends_restriction_notification_at_threshold(
        self, mock_update, mock_context, mock_settings
    ):
        """Test that restriction notification is sent when user is restricted."""
        mock_update.message.forward_origin = MagicMock()

        mock_record = MagicMock()
        mock_record.joined_at = datetime.now(UTC)

        updated_record = MagicMock()
        updated_record.violation_count = 3  # Threshold reached

        mock_db = MagicMock()
        mock_db.get_new_user_probation.return_value = mock_record
        mock_db.increment_new_user_violation.return_value = updated_record

        with (
            patch("bot.handlers.anti_spam.get_settings", return_value=mock_settings),
            patch("bot.handlers.anti_spam.get_database", return_value=mock_db),
        ):
            await handle_new_user_spam(mock_update, mock_context)

        # Should call send_message for restriction notification (not first warning)
        mock_context.bot.send_message.assert_called_once()
        mock_context.bot.restrict_chat_member.assert_called_once()

    @pytest.mark.asyncio
    async def test_deletes_message_with_external_reply(
        self, mock_update, mock_context, mock_settings
    ):
        """Test that messages with external replies are deleted."""
        mock_update.message.external_reply = MagicMock()  # Any non-None value

        mock_record = MagicMock()
        mock_record.joined_at = datetime.now(UTC)

        updated_record = MagicMock()
        updated_record.violation_count = 1

        mock_db = MagicMock()
        mock_db.get_new_user_probation.return_value = mock_record
        mock_db.increment_new_user_violation.return_value = updated_record

        with (
            patch("bot.handlers.anti_spam.get_settings", return_value=mock_settings),
            patch("bot.handlers.anti_spam.get_database", return_value=mock_db),
        ):
            await handle_new_user_spam(mock_update, mock_context)

        mock_update.message.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_ignores_update_without_message(self, mock_context, mock_settings):
        """Test that update without message is ignored."""
        mock_update = MagicMock()
        mock_update.message = None

        with patch("bot.handlers.anti_spam.get_settings", return_value=mock_settings):
            await handle_new_user_spam(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_ignores_message_without_from_user(self, mock_context, mock_settings):
        """Test that message without from_user is ignored."""
        mock_update = MagicMock()
        mock_update.message = MagicMock(spec=Message)
        mock_update.message.from_user = None

        with patch("bot.handlers.anti_spam.get_settings", return_value=mock_settings):
            await handle_new_user_spam(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_continues_when_delete_fails(
        self, mock_update, mock_context, mock_settings
    ):
        """Test that handler continues when message delete fails."""
        mock_update.message.forward_origin = MagicMock()
        mock_update.message.delete = AsyncMock(side_effect=Exception("Delete failed"))

        mock_record = MagicMock()
        mock_record.joined_at = datetime.now(UTC)

        updated_record = MagicMock()
        updated_record.violation_count = 1

        mock_db = MagicMock()
        mock_db.get_new_user_probation.return_value = mock_record
        mock_db.increment_new_user_violation.return_value = updated_record

        with (
            patch("bot.handlers.anti_spam.get_settings", return_value=mock_settings),
            patch("bot.handlers.anti_spam.get_database", return_value=mock_db),
        ):
            await handle_new_user_spam(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_continues_when_send_warning_fails(
        self, mock_update, mock_context, mock_settings
    ):
        """Test that handler continues when sending warning fails."""
        mock_update.message.forward_origin = MagicMock()
        mock_context.bot.send_message = AsyncMock(
            side_effect=Exception("Send failed")
        )

        mock_record = MagicMock()
        mock_record.joined_at = datetime.now(UTC)

        updated_record = MagicMock()
        updated_record.violation_count = 1

        mock_db = MagicMock()
        mock_db.get_new_user_probation.return_value = mock_record
        mock_db.increment_new_user_violation.return_value = updated_record

        with (
            patch("bot.handlers.anti_spam.get_settings", return_value=mock_settings),
            patch("bot.handlers.anti_spam.get_database", return_value=mock_db),
        ):
            await handle_new_user_spam(mock_update, mock_context)

        mock_update.message.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_continues_when_restrict_fails(
        self, mock_update, mock_context, mock_settings
    ):
        """Test that handler completes when restrict fails."""
        mock_update.message.forward_origin = MagicMock()
        mock_context.bot.restrict_chat_member = AsyncMock(
            side_effect=Exception("Restrict failed")
        )

        mock_record = MagicMock()
        mock_record.joined_at = datetime.now(UTC)

        updated_record = MagicMock()
        updated_record.violation_count = 3  # Threshold reached

        mock_db = MagicMock()
        mock_db.get_new_user_probation.return_value = mock_record
        mock_db.increment_new_user_violation.return_value = updated_record

        with (
            patch("bot.handlers.anti_spam.get_settings", return_value=mock_settings),
            patch("bot.handlers.anti_spam.get_database", return_value=mock_db),
        ):
            await handle_new_user_spam(mock_update, mock_context)

        mock_update.message.delete.assert_called_once()
