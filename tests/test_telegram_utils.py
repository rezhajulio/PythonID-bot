from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import BadRequest, Forbidden

from bot.services.telegram_utils import fetch_group_admin_ids, get_user_status


@pytest.fixture
def mock_bot():
    return AsyncMock()


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


class TestFetchGroupAdminIds:
    async def test_fetch_single_admin(self, mock_bot):
        """Test fetching admin IDs when there is one admin."""
        admin = MagicMock()
        admin.user = MagicMock()
        admin.user.id = 123
        mock_bot.get_chat_administrators.return_value = [admin]

        result = await fetch_group_admin_ids(mock_bot, group_id=456)

        assert result == [123]
        mock_bot.get_chat_administrators.assert_called_once_with(456)

    async def test_fetch_multiple_admins(self, mock_bot):
        """Test fetching multiple admin IDs."""
        admin1 = MagicMock()
        admin1.user = MagicMock()
        admin1.user.id = 111

        admin2 = MagicMock()
        admin2.user = MagicMock()
        admin2.user.id = 222

        admin3 = MagicMock()
        admin3.user = MagicMock()
        admin3.user.id = 333

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
        mock_bot.get_chat_administrators.return_value = [admin]

        result = await fetch_group_admin_ids(mock_bot, group_id=-1001234567890)

        assert result == [123]
        mock_bot.get_chat_administrators.assert_called_once_with(-1001234567890)

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
