from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, User
from telegram.error import BadRequest, Forbidden, RetryAfter

from bot.services.telegram_utils import (
    fetch_group_admin_ids,
    get_user_mention,
    get_user_mention_by_id,
    get_user_status,
    is_user_admin_or_trusted,
    restrict_chat_member_with_retry,
    send_message_with_retry,
    unrestrict_user,
)


@pytest.fixture
def mock_bot():
    return AsyncMock()


class TestGetUserMention:
    def test_get_user_mention_with_username(self):
        """Test getting mention for user with username."""
        user = MagicMock(spec=User)
        user.username = "johndoe"
        user.id = 123456
        user.full_name = "John Doe"

        result = get_user_mention(user)

        assert result == "@johndoe"

    @patch("bot.services.telegram_utils.mention_markdown")
    def test_get_user_mention_without_username(self, mock_mention_markdown):
        """Test getting mention for user without username."""
        user = MagicMock(spec=User)
        user.username = None
        user.id = 123456
        user.full_name = "John Doe"
        mock_mention_markdown.return_value = "[John Doe](tg://user?id=123456)"

        result = get_user_mention(user)

        mock_mention_markdown.assert_called_once_with(123456, "John Doe", version=1)
        assert result == "[John Doe](tg://user?id=123456)"

    @patch("bot.services.telegram_utils.mention_markdown")
    def test_get_user_mention_empty_username(self, mock_mention_markdown):
        """Test getting mention for user with empty string username."""
        user = MagicMock(spec=User)
        user.username = ""
        user.id = 987654
        user.full_name = "Jane Smith"
        mock_mention_markdown.return_value = "[Jane Smith](tg://user?id=987654)"

        result = get_user_mention(user)

        mock_mention_markdown.assert_called_once_with(987654, "Jane Smith", version=1)
        assert result == "[Jane Smith](tg://user?id=987654)"

    def test_get_user_mention_special_characters_in_username(self):
        """Test getting mention with special characters in username."""
        user = MagicMock(spec=User)
        user.username = "user_name_123"
        user.id = 111222
        user.full_name = "User Name"

        result = get_user_mention(user)

        assert result == r"@user\_name\_123"

    @patch("bot.services.telegram_utils.mention_markdown")
    def test_get_user_mention_special_characters_in_full_name(self, mock_mention_markdown):
        """Test getting mention with special characters in full name."""
        user = MagicMock(spec=User)
        user.username = None
        user.id = 555666
        user.full_name = "José María"
        mock_mention_markdown.return_value = "[José María](tg://user?id=555666)"

        result = get_user_mention(user)

        mock_mention_markdown.assert_called_once_with(555666, "José María", version=1)
        assert result == "[José María](tg://user?id=555666)"

    @patch("bot.services.telegram_utils.mention_markdown")
    def test_get_user_mention_long_full_name(self, mock_mention_markdown):
        """Test getting mention with very long full name."""
        user = MagicMock(spec=User)
        user.username = None
        user.id = 777888
        user.full_name = "A" * 100
        mock_mention_markdown.return_value = f"[{'A' * 100}](tg://user?id=777888)"

        result = get_user_mention(user)

        mock_mention_markdown.assert_called_once_with(777888, "A" * 100, version=1)
        assert result == f"[{'A' * 100}](tg://user?id=777888)"

    def test_get_user_mention_with_prefixed_username(self):
        """Test that username with @ prefix is normalized."""
        user = MagicMock(spec=User)
        user.username = "@already_prefixed"
        user.id = 123456
        user.full_name = "Test User"

        result = get_user_mention(user)

        assert result == r"@already\_prefixed"

    def test_get_user_mention_chat_with_username(self):
        """Test getting mention for Chat object with username."""
        chat = MagicMock(spec=Chat)
        chat.username = "john_doe"
        chat.id = 123456
        chat.full_name = "John Doe"

        result = get_user_mention(chat)

        assert result == r"@john\_doe"

    def test_get_user_mention_chat_with_prefixed_username(self):
        """Test that Chat with @ prefixed username is normalized."""
        chat = MagicMock(spec=Chat)
        chat.username = "@prefixed_chat"
        chat.id = 123456
        chat.full_name = "Prefixed Chat"

        result = get_user_mention(chat)

        assert result == r"@prefixed\_chat"

    @patch("bot.services.telegram_utils.mention_markdown")
    def test_get_user_mention_chat_without_username(self, mock_mention_markdown):
        """Test getting mention for Chat object without username."""
        chat = MagicMock(spec=Chat)
        chat.username = None
        chat.id = 123456
        chat.full_name = "Jane Smith"
        mock_mention_markdown.return_value = "[Jane Smith](tg://user?id=123456)"

        result = get_user_mention(chat)

        mock_mention_markdown.assert_called_once_with(123456, "Jane Smith", version=1)
        assert result == "[Jane Smith](tg://user?id=123456)"

    @patch("bot.services.telegram_utils.mention_markdown")
    def test_get_user_mention_chat_empty_username(self, mock_mention_markdown):
        """Test getting mention for Chat object with empty string username."""
        chat = MagicMock(spec=Chat)
        chat.username = ""
        chat.id = 987654
        chat.full_name = "Jane Smith"
        mock_mention_markdown.return_value = "[Jane Smith](tg://user?id=987654)"

        result = get_user_mention(chat)

        mock_mention_markdown.assert_called_once_with(987654, "Jane Smith", version=1)
        assert result == "[Jane Smith](tg://user?id=987654)"


class TestGetUserMentionById:
    @patch("bot.services.telegram_utils.mention_markdown")
    def test_get_user_mention_by_id_basic(self, mock_mention_markdown):
        """Test basic user mention by ID."""
        mock_mention_markdown.return_value = "[John Doe](tg://user?id=123456)"

        result = get_user_mention_by_id(123456, "John Doe")

        mock_mention_markdown.assert_called_once_with(123456, "John Doe", version=1)
        assert result == "[John Doe](tg://user?id=123456)"

    @patch("bot.services.telegram_utils.mention_markdown")
    def test_get_user_mention_by_id_large_id(self, mock_mention_markdown):
        """Test mention by ID with large user ID."""
        mock_mention_markdown.return_value = "[Jane Smith](tg://user?id=9999999999)"

        result = get_user_mention_by_id(9999999999, "Jane Smith")

        mock_mention_markdown.assert_called_once_with(9999999999, "Jane Smith", version=1)
        assert result == "[Jane Smith](tg://user?id=9999999999)"

    @patch("bot.services.telegram_utils.mention_markdown")
    def test_get_user_mention_by_id_special_characters(self, mock_mention_markdown):
        """Test mention by ID with special characters in name."""
        mock_mention_markdown.return_value = "[José María](tg://user?id=111222)"

        result = get_user_mention_by_id(111222, "José María")

        mock_mention_markdown.assert_called_once_with(111222, "José María", version=1)
        assert result == "[José María](tg://user?id=111222)"

    @patch("bot.services.telegram_utils.mention_markdown")
    def test_get_user_mention_by_id_emojis_in_name(self, mock_mention_markdown):
        """Test mention by ID with emojis in name."""
        mock_mention_markdown.return_value = "[User 🎉](tg://user?id=333444)"

        result = get_user_mention_by_id(333444, "User 🎉")

        mock_mention_markdown.assert_called_once_with(333444, "User 🎉", version=1)
        assert result == "[User 🎉](tg://user?id=333444)"

    @patch("bot.services.telegram_utils.mention_markdown")
    def test_get_user_mention_by_id_long_name(self, mock_mention_markdown):
        """Test mention by ID with very long name."""
        long_name = "A" * 200
        mock_mention_markdown.return_value = f"[{long_name}](tg://user?id=555666)"

        result = get_user_mention_by_id(555666, long_name)

        mock_mention_markdown.assert_called_once_with(555666, long_name, version=1)
        assert result == f"[{long_name}](tg://user?id=555666)"

    @patch("bot.services.telegram_utils.mention_markdown")
    def test_get_user_mention_by_id_single_character_name(self, mock_mention_markdown):
        """Test mention by ID with single character name."""
        mock_mention_markdown.return_value = "[A](tg://user?id=777888)"

        result = get_user_mention_by_id(777888, "A")

        mock_mention_markdown.assert_called_once_with(777888, "A", version=1)
        assert result == "[A](tg://user?id=777888)"

    def test_get_user_mention_by_id_with_username(self):
        """Test mention by ID with username provided returns @username."""
        result = get_user_mention_by_id(123456, "John Doe", username="johndoe")

        assert result == "@johndoe"

    def test_get_user_mention_by_id_with_username_special_chars(self):
        """Test mention by ID with username containing underscores."""
        result = get_user_mention_by_id(123456, "John Doe", username="john_doe_123")

        assert result == r"@john\_doe\_123"

    def test_get_user_mention_by_id_with_prefixed_username(self):
        """Test that username with @ prefix is normalized."""
        result = get_user_mention_by_id(123456, "Test User", username="@prefixed")

        assert result == "@prefixed"

    @patch("bot.services.telegram_utils.mention_markdown")
    def test_get_user_mention_by_id_with_none_username(self, mock_mention_markdown):
        """Test mention by ID with explicit None username."""
        mock_mention_markdown.return_value = "[John Doe](tg://user?id=123456)"

        result = get_user_mention_by_id(123456, "John Doe", username=None)

        mock_mention_markdown.assert_called_once_with(123456, "John Doe", version=1)
        assert result == "[John Doe](tg://user?id=123456)"

    @patch("bot.services.telegram_utils.mention_markdown")
    def test_get_user_mention_by_id_with_empty_username(self, mock_mention_markdown):
        """Test mention by ID with empty string username falls back to markdown."""
        mock_mention_markdown.return_value = "[John Doe](tg://user?id=123456)"

        result = get_user_mention_by_id(123456, "John Doe", username="")

        mock_mention_markdown.assert_called_once_with(123456, "John Doe", version=1)
        assert result == "[John Doe](tg://user?id=123456)"


class TestUnrestrictUser:
    async def test_unrestrict_user_basic(self, mock_bot):
        """Test basic user unrestriction."""
        mock_chat = MagicMock()
        mock_permissions = MagicMock()
        mock_chat.permissions = mock_permissions
        mock_bot.get_chat.return_value = mock_chat

        await unrestrict_user(mock_bot, group_id=123, user_id=456)

        mock_bot.get_chat.assert_called_once_with(123)
        mock_bot.restrict_chat_member.assert_called_once_with(
            chat_id=123,
            user_id=456,
            permissions=mock_permissions,
        )

    async def test_unrestrict_user_with_negative_group_id(self, mock_bot):
        """Test unrestricting user in supergroup (negative ID)."""
        mock_chat = MagicMock()
        mock_permissions = MagicMock()
        mock_chat.permissions = mock_permissions
        mock_bot.get_chat.return_value = mock_chat

        await unrestrict_user(mock_bot, group_id=-1001234567890, user_id=456)

        mock_bot.get_chat.assert_called_once_with(-1001234567890)
        mock_bot.restrict_chat_member.assert_called_once_with(
            chat_id=-1001234567890,
            user_id=456,
            permissions=mock_permissions,
        )

    async def test_unrestrict_user_raises_bad_request(self, mock_bot):
        """Test that BadRequest is raised when user not found."""
        mock_bot.get_chat.side_effect = BadRequest("User not found")

        with pytest.raises(BadRequest, match="User not found"):
            await unrestrict_user(mock_bot, group_id=123, user_id=456)

    async def test_unrestrict_user_raises_forbidden(self, mock_bot):
        """Test that Forbidden is raised when bot lacks permissions."""
        mock_chat = MagicMock()
        mock_permissions = MagicMock()
        mock_chat.permissions = mock_permissions
        mock_bot.get_chat.return_value = mock_chat
        mock_bot.restrict_chat_member.side_effect = Forbidden("No permissions")

        with pytest.raises(Forbidden, match="No permissions"):
            await unrestrict_user(mock_bot, group_id=123, user_id=456)


class TestGetUserStatus:
    async def test_get_user_status_member(self, mock_bot):
        """Test getting status of a member user."""
        user_member = MagicMock()
        user_member.status = "member"
        mock_bot.get_chat_member.return_value = user_member

        result = await get_user_status(mock_bot, group_id=123, user_id=456)

        assert result == "member"
        mock_bot.get_chat_member.assert_called_once_with(chat_id=123, user_id=456)

    async def test_get_user_status_administrator(self, mock_bot):
        """Test getting status of an administrator."""
        user_admin = MagicMock()
        user_admin.status = "administrator"
        mock_bot.get_chat_member.return_value = user_admin

        result = await get_user_status(mock_bot, group_id=123, user_id=456)

        assert result == "administrator"

    async def test_get_user_status_restricted(self, mock_bot):
        """Test getting status of a restricted user."""
        user_restricted = MagicMock()
        user_restricted.status = "restricted"
        mock_bot.get_chat_member.return_value = user_restricted

        result = await get_user_status(mock_bot, group_id=123, user_id=456)

        assert result == "restricted"

    async def test_get_user_status_left(self, mock_bot):
        """Test getting status of a user who left."""
        user_left = MagicMock()
        user_left.status = "left"
        mock_bot.get_chat_member.return_value = user_left

        result = await get_user_status(mock_bot, group_id=123, user_id=456)

        assert result == "left"

    async def test_get_user_status_kicked(self, mock_bot):
        """Test getting status of a kicked user."""
        user_kicked = MagicMock()
        user_kicked.status = "kicked"
        mock_bot.get_chat_member.return_value = user_kicked

        result = await get_user_status(mock_bot, group_id=123, user_id=456)

        assert result == "kicked"

    async def test_get_user_status_creator(self, mock_bot):
        """Test getting status of a group creator."""
        user_creator = MagicMock()
        user_creator.status = "creator"
        mock_bot.get_chat_member.return_value = user_creator

        result = await get_user_status(mock_bot, group_id=123, user_id=456)

        assert result == "creator"

    async def test_get_user_status_bad_request(self, mock_bot):
        """Test handling of BadRequest exception."""
        mock_bot.get_chat_member.side_effect = BadRequest("User not found")

        result = await get_user_status(mock_bot, group_id=123, user_id=456)

        assert result is None

    async def test_get_user_status_forbidden(self, mock_bot):
        """Test handling of Forbidden exception."""
        mock_bot.get_chat_member.side_effect = Forbidden("Bot not in group")

        result = await get_user_status(mock_bot, group_id=123, user_id=456)

        assert result is None

    async def test_get_user_status_bot_not_in_group(self, mock_bot):
        """Test when bot is not in the group."""
        mock_bot.get_chat_member.side_effect = BadRequest("Bot not in group")

        result = await get_user_status(mock_bot, group_id=-1001234567890, user_id=456)

        assert result is None

    async def test_get_user_status_with_negative_group_id(self, mock_bot):
        """Test with negative group ID (supergroup)."""
        user_member = MagicMock()
        user_member.status = "member"
        mock_bot.get_chat_member.return_value = user_member

        result = await get_user_status(mock_bot, group_id=-1001234567890, user_id=456)

        assert result == "member"
        mock_bot.get_chat_member.assert_called_once_with(chat_id=-1001234567890, user_id=456)

    async def test_get_user_status_with_large_ids(self, mock_bot):
        """Test with large user and group IDs."""
        user_member = MagicMock()
        user_member.status = "member"
        mock_bot.get_chat_member.return_value = user_member

        large_group_id = 9999999999
        large_user_id = 8888888888

        result = await get_user_status(mock_bot, group_id=large_group_id, user_id=large_user_id)

        assert result == "member"
        mock_bot.get_chat_member.assert_called_once_with(
            chat_id=large_group_id, user_id=large_user_id
        )


class TestIsUserAdminOrTrusted:
    @patch("bot.services.telegram_utils.get_database")
    def test_admin_hit_does_not_touch_db(self, mock_get_database):
        context = MagicMock()
        context.bot_data = {
            "group_admin_ids": {-100: [123]},
            "trusted_user_ids": set(),
        }

        assert is_user_admin_or_trusted(context, -100, 123) is True
        mock_get_database.assert_not_called()

    @patch("bot.services.telegram_utils.get_database")
    def test_trusted_cache_hit_does_not_touch_db(self, mock_get_database):
        context = MagicMock()
        context.bot_data = {
            "group_admin_ids": {-100: []},
            "trusted_user_ids": {123},
        }

        assert is_user_admin_or_trusted(context, -100, 123) is True
        mock_get_database.assert_not_called()

    @patch("bot.services.telegram_utils.get_database")
    def test_missing_cache_lazy_loads_from_db_once(self, mock_get_database):
        context = MagicMock()
        context.bot_data = {"group_admin_ids": {-100: []}}

        db = MagicMock()
        db.get_trusted_user_ids.return_value = {321, 654}
        mock_get_database.return_value = db

        # First call: triggers lazy load.
        assert is_user_admin_or_trusted(context, -100, 321) is True
        assert mock_get_database.call_count == 1
        assert db.get_trusted_user_ids.call_count == 1

        # Cache is now a set.
        cached = context.bot_data["trusted_user_ids"]
        assert isinstance(cached, set)
        assert cached == {321, 654}

        # Second call: no additional DB calls.
        assert is_user_admin_or_trusted(context, -100, 654) is True
        assert mock_get_database.call_count == 1
        assert db.get_trusted_user_ids.call_count == 1

    @patch("bot.services.telegram_utils.get_database")
    def test_returns_false_for_unknown_user_with_populated_cache(self, mock_get_database):
        context = MagicMock()
        context.bot_data = {
            "group_admin_ids": {-100: []},
            "trusted_user_ids": {1, 2},
        }

        assert is_user_admin_or_trusted(context, -100, 999) is False
        mock_get_database.assert_not_called()

    @patch("bot.services.telegram_utils.get_database")
    def test_runtime_error_caches_empty_set(self, mock_get_database):
        context = MagicMock()
        context.bot_data = {"group_admin_ids": {-100: []}}

        mock_get_database.side_effect = RuntimeError("Database not initialized")

        assert is_user_admin_or_trusted(context, -100, 321) is False
        # Empty set cached so retries don't hit DB again.
        assert context.bot_data["trusted_user_ids"] == set()

        # Second call: no additional DB call attempted.
        assert is_user_admin_or_trusted(context, -100, 321) is False
        assert mock_get_database.call_count == 1


class TestFetchGroupAdminIds:
    async def test_fetch_single_admin(self, mock_bot):
        """Test fetching admin IDs when there is one admin."""
        admin = MagicMock()
        admin.user = MagicMock()
        admin.user.id = 123
        admin.user.is_bot = False
        mock_bot.get_chat_administrators.return_value = [admin]

        result = await fetch_group_admin_ids(mock_bot, group_id=456)

        assert result == [123]
        mock_bot.get_chat_administrators.assert_called_once_with(
            456, api_kwargs={"return_bots": False}
        )

    async def test_fetch_multiple_admins(self, mock_bot):
        """Test fetching multiple admin IDs."""
        admin1 = MagicMock()
        admin1.user = MagicMock()
        admin1.user.id = 111
        admin1.user.is_bot = False

        admin2 = MagicMock()
        admin2.user = MagicMock()
        admin2.user.id = 222
        admin2.user.is_bot = False

        admin3 = MagicMock()
        admin3.user = MagicMock()
        admin3.user.id = 333
        admin3.user.is_bot = False

        mock_bot.get_chat_administrators.return_value = [admin1, admin2, admin3]

        result = await fetch_group_admin_ids(mock_bot, group_id=456)

        assert result == [111, 222, 333]

    async def test_fetch_admins_preserves_order(self, mock_bot):
        """Test that admin order is preserved."""
        admins = []
        expected_ids = [999, 888, 777, 666, 555]

        for admin_id in expected_ids:
            admin = MagicMock()
            admin.user = MagicMock()
            admin.user.id = admin_id
            admin.user.is_bot = False
            admins.append(admin)

        mock_bot.get_chat_administrators.return_value = admins

        result = await fetch_group_admin_ids(mock_bot, group_id=456)

        assert result == expected_ids

    async def test_fetch_admins_bad_request(self, mock_bot):
        """Test handling of BadRequest exception."""
        mock_bot.get_chat_administrators.side_effect = BadRequest("Group not found")

        with pytest.raises(Exception, match="Failed to fetch admins from group"):
            await fetch_group_admin_ids(mock_bot, group_id=456)

    async def test_fetch_admins_forbidden(self, mock_bot):
        """Test handling of Forbidden exception."""
        mock_bot.get_chat_administrators.side_effect = Forbidden("Bot not in group")

        with pytest.raises(Exception, match="Failed to fetch admins from group"):
            await fetch_group_admin_ids(mock_bot, group_id=456)

    async def test_fetch_admins_bot_not_in_group(self, mock_bot):
        """Test when bot is not in the group."""
        mock_bot.get_chat_administrators.side_effect = Forbidden("Bot not in group")

        with pytest.raises(Exception, match="Failed to fetch admins from group"):
            await fetch_group_admin_ids(mock_bot, group_id=-1001234567890)

    async def test_fetch_admins_with_negative_group_id(self, mock_bot):
        """Test with negative group ID (supergroup)."""
        admin = MagicMock()
        admin.user = MagicMock()
        admin.user.id = 123
        admin.user.is_bot = False
        mock_bot.get_chat_administrators.return_value = [admin]

        result = await fetch_group_admin_ids(mock_bot, group_id=-1001234567890)

        assert result == [123]
        mock_bot.get_chat_administrators.assert_called_once_with(
            -1001234567890, api_kwargs={"return_bots": False}
        )

    async def test_fetch_admins_empty_list(self, mock_bot):
        """Test when group has no admins (edge case)."""
        mock_bot.get_chat_administrators.return_value = []

        result = await fetch_group_admin_ids(mock_bot, group_id=456)

        assert result == []

    async def test_fetch_admins_large_group(self, mock_bot):
        """Test with many admins."""
        admins = []
        expected_ids = list(range(1000, 1100))  # 100 admins

        for admin_id in expected_ids:
            admin = MagicMock()
            admin.user = MagicMock()
            admin.user.id = admin_id
            admin.user.is_bot = False
            admins.append(admin)

        mock_bot.get_chat_administrators.return_value = admins

        result = await fetch_group_admin_ids(mock_bot, group_id=456)

        assert result == expected_ids
        assert len(result) == 100

    async def test_fetch_admins_with_large_ids(self, mock_bot):
        """Test with large user IDs."""
        admin = MagicMock()
        admin.user = MagicMock()
        admin.user.id = 9999999999
        admin.user.is_bot = False
        mock_bot.get_chat_administrators.return_value = [admin]

        result = await fetch_group_admin_ids(mock_bot, group_id=123)

        assert result == [9999999999]

    async def test_fetch_admins_exception_includes_group_id(self, mock_bot):
        """Test that exception message includes group ID."""
        mock_bot.get_chat_administrators.side_effect = BadRequest("Group not found")

        with pytest.raises(Exception) as exc_info:
            await fetch_group_admin_ids(mock_bot, group_id=456)

        assert "456" in str(exc_info.value)

    async def test_fetch_admins_different_exceptions(self, mock_bot):
        """Test that both BadRequest and Forbidden raise Exception."""
        # Test BadRequest
        mock_bot.get_chat_administrators.side_effect = BadRequest("Error")

        with pytest.raises(Exception):
            await fetch_group_admin_ids(mock_bot, group_id=456)

        # Test Forbidden
        mock_bot.get_chat_administrators.side_effect = Forbidden("Error")

        with pytest.raises(Exception):
            await fetch_group_admin_ids(mock_bot, group_id=456)

    async def test_fetch_admins_excludes_bots(self, mock_bot):
        """Test that bot accounts are excluded from admin IDs."""
        human_admin = MagicMock()
        human_admin.user = MagicMock()
        human_admin.user.id = 111
        human_admin.user.is_bot = False

        bot_admin = MagicMock()
        bot_admin.user = MagicMock()
        bot_admin.user.id = 222
        bot_admin.user.is_bot = True

        mock_bot.get_chat_administrators.return_value = [human_admin, bot_admin]

        result = await fetch_group_admin_ids(mock_bot, group_id=456)

        assert result == [111]
        assert 222 not in result


class TestSendMessageWithRetry:
    """send_message_with_retry handles RetryAfter correctly."""

    async def test_success_no_retry(self):
        """Normal success: no retry, no sleep, returns True."""
        bot = MagicMock()
        bot.send_message = AsyncMock(return_value=MagicMock())

        result = await send_message_with_retry(bot, chat_id=-100, text="hello")

        assert result is True
        bot.send_message.assert_awaited_once_with(chat_id=-100, text="hello")

    async def test_retries_on_retry_after(self):
        """RetryAfter once then success: sleeps, retries, returns True."""
        bot = MagicMock()
        bot.send_message = AsyncMock(
            side_effect=[
                RetryAfter(retry_after=2),
                MagicMock(),
            ]
        )

        with patch("bot.services.telegram_utils.asyncio.sleep") as mock_sleep:
            mock_sleep.return_value = None
            result = await send_message_with_retry(bot, chat_id=-100, text="hello")

        assert result is True
        assert bot.send_message.await_count == 2
        mock_sleep.assert_called_once_with(3)

    async def test_gives_up_after_second_retry_after(self):
        """Second RetryAfter: returns False."""
        bot = MagicMock()
        bot.send_message = AsyncMock(
            side_effect=RetryAfter(retry_after=1),
        )

        with patch("bot.services.telegram_utils.asyncio.sleep") as mock_sleep:
            mock_sleep.return_value = None
            result = await send_message_with_retry(bot, chat_id=-100, text="hello")

        assert result is False
        assert bot.send_message.await_count == 2

    async def test_propagates_other_telegram_error(self):
        """Non-RetryAfter TelegramError re-raises (caller's except catches it)."""
        bot = MagicMock()
        bot.send_message = AsyncMock(side_effect=BadRequest("User not found"))

        with pytest.raises(BadRequest):
            await send_message_with_retry(bot, chat_id=-100, text="hello")

        bot.send_message.assert_awaited_once()


class TestRestrictChatMemberWithRetry:
    """restrict_chat_member_with_retry handles RetryAfter correctly."""

    async def test_success_no_retry(self):
        """Normal success: returns True."""
        bot = MagicMock()
        bot.restrict_chat_member = AsyncMock(return_value=MagicMock())
        permissions = MagicMock()

        result = await restrict_chat_member_with_retry(
            bot, chat_id=-100, user_id=123, permissions=permissions,
        )

        assert result is True
        bot.restrict_chat_member.assert_awaited_once_with(
            chat_id=-100, user_id=123, permissions=permissions,
        )

    async def test_retries_on_retry_after(self):
        """RetryAfter once then success: sleeps, retries, returns True."""
        bot = MagicMock()
        permissions = MagicMock()
        bot.restrict_chat_member = AsyncMock(
            side_effect=[
                RetryAfter(retry_after=2),
                MagicMock(),
            ]
        )

        with patch("bot.services.telegram_utils.asyncio.sleep") as mock_sleep:
            mock_sleep.return_value = None
            result = await restrict_chat_member_with_retry(
                bot, chat_id=-100, user_id=123, permissions=permissions,
            )

        assert result is True
        assert bot.restrict_chat_member.await_count == 2
        mock_sleep.assert_called_once_with(3)

    async def test_gives_up_after_second_retry_after(self):
        """Second RetryAfter: returns False."""
        bot = MagicMock()
        permissions = MagicMock()
        bot.restrict_chat_member = AsyncMock(
            side_effect=RetryAfter(retry_after=1),
        )

        with patch("bot.services.telegram_utils.asyncio.sleep") as mock_sleep:
            mock_sleep.return_value = None
            result = await restrict_chat_member_with_retry(
                bot, chat_id=-100, user_id=123, permissions=permissions,
            )

        assert result is False
        assert bot.restrict_chat_member.await_count == 2

    async def test_propagates_other_telegram_error(self):
        """Non-RetryAfter TelegramError re-raises."""
        bot = MagicMock()
        permissions = MagicMock()
        bot.restrict_chat_member = AsyncMock(
            side_effect=BadRequest("User not found"),
        )

        with pytest.raises(BadRequest):
            await restrict_chat_member_with_retry(
                bot, chat_id=-100, user_id=123, permissions=permissions,
            )

        bot.restrict_chat_member.assert_awaited_once()
