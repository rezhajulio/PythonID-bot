"""Tests for admin /warn command handler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.group_config import GroupConfig, GroupRegistry
from bot.handlers.warn import handle_warn_command


@pytest.fixture
def group_config():
    return GroupConfig(
        group_id=-1001234567890,
        warning_topic_id=12345,
        rules_link="https://t.me/test/rules",
    )


@pytest.fixture
def mock_registry(group_config):
    registry = GroupRegistry()
    registry.register(group_config)
    return registry


@pytest.fixture
def mock_update():
    update = MagicMock()
    update.message = MagicMock()
    update.message.from_user = MagicMock()
    update.message.from_user.id = 12345
    update.message.from_user.full_name = "Admin User"
    update.message.from_user.is_bot = False
    update.message.reply_text = AsyncMock()
    update.message.delete = AsyncMock()
    update.message.chat_id = -1001234567890
    update.message.message_id = 999
    update.message.reply_to_message = None
    update.message.forum_topic_created = None
    update.effective_chat = MagicMock()
    update.effective_chat.id = -1001234567890
    update.effective_chat.type = "supergroup"
    return update


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.get_chat_member = AsyncMock()
    context.bot_data = {
        "admin_ids": [12345],
        "group_admin_ids": {-1001234567890: [12345]},
    }
    context.args = []
    return context


def _make_target_user(user_id=67890, full_name="Bad Member", username="badmember"):
    user = MagicMock()
    user.id = user_id
    user.full_name = full_name
    user.username = username
    user.is_bot = False
    return user


def _make_reply_message(target_user):
    msg = MagicMock()
    msg.from_user = target_user
    msg.forum_topic_created = None
    return msg


def _make_chat_member(user, status="member"):
    member = MagicMock()
    member.user = user
    member.status = status
    return member


class TestHandleWarnCommand:
    async def test_non_admin_silent_ignore(
        self, mock_update, mock_context, mock_registry
    ):
        """Non-admin callers are silently ignored."""
        mock_update.message.from_user.id = 99999
        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.send_message.assert_not_called()
        mock_update.message.reply_text.assert_not_called()
        mock_update.message.delete.assert_not_called()

    async def test_admin_of_other_group_silent_ignore(
        self, mock_update, mock_context, mock_registry
    ):
        """Admin of a different group is silently ignored in this group."""
        mock_context.bot_data = {
            "admin_ids": [12345],
            "group_admin_ids": {
                -1001234567890: [],
                -1009876543210: [12345],
            },
        }
        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.send_message.assert_not_called()
        mock_update.message.reply_text.assert_not_called()
        mock_update.message.delete.assert_not_called()

    async def test_reply_mode_with_reason(
        self, mock_update, mock_context, mock_registry
    ):
        """Admin replies to a member with /warn <reason>."""
        target = _make_target_user()
        mock_update.message.reply_to_message = _make_reply_message(target)
        mock_context.args = ["uploading", "copyrighted", "material"]

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == -1001234567890
        assert "message_thread_id" not in call_kwargs
        assert "badmember" in call_kwargs["text"]
        assert "copyrighted" in call_kwargs["text"]
        mock_update.message.delete.assert_called_once()

    async def test_reply_mode_without_reason(
        self, mock_update, mock_context, mock_registry
    ):
        """Admin replies with /warn and no reason."""
        target = _make_target_user()
        mock_update.message.reply_to_message = _make_reply_message(target)
        mock_context.args = []

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args.kwargs
        assert "patuhi aturan grup" in call_kwargs["text"]
        mock_update.message.delete.assert_called_once()

    async def test_id_mode_with_reason(
        self, mock_update, mock_context, mock_registry
    ):
        """Admin uses /warn USER_ID <reason>."""
        target = _make_target_user()
        mock_context.bot.get_chat_member.return_value = _make_chat_member(target)
        mock_context.args = ["67890", "spam", "links"]

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.get_chat_member.assert_called_once_with(
            chat_id=-1001234567890, user_id=67890
        )
        mock_context.bot.send_message.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args.kwargs
        assert "spam links" in call_kwargs["text"]
        mock_update.message.delete.assert_called_once()

    async def test_id_mode_without_reason(
        self, mock_update, mock_context, mock_registry
    ):
        """Admin uses /warn USER_ID with no reason."""
        target = _make_target_user()
        mock_context.bot.get_chat_member.return_value = _make_chat_member(target)
        mock_context.args = ["67890"]

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args.kwargs
        assert "patuhi aturan grup" in call_kwargs["text"]
        mock_update.message.delete.assert_called_once()

    async def test_id_mode_left_member_shows_error(
        self, mock_update, mock_context, mock_registry
    ):
        """User who left the group cannot be warned."""
        target = _make_target_user()
        mock_context.bot.get_chat_member.return_value = _make_chat_member(target, status="left")
        mock_context.args = ["67890"]

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        reply_text = mock_update.message.reply_text.call_args
        assert "bukan member" in reply_text.args[0]
        assert reply_text.kwargs.get("do_quote") is False
        mock_context.bot.send_message.assert_not_called()

    async def test_id_mode_banned_member_shows_error(
        self, mock_update, mock_context, mock_registry
    ):
        """Banned user cannot be warned."""
        target = _make_target_user()
        mock_context.bot.get_chat_member.return_value = _make_chat_member(target, status="kicked")
        mock_context.args = ["67890"]

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "bukan member" in mock_update.message.reply_text.call_args.args[0]
        mock_context.bot.send_message.assert_not_called()

    async def test_no_reply_no_args_shows_usage(
        self, mock_update, mock_context, mock_registry
    ):
        """No reply and no args shows usage error."""
        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "Penggunaan" in mock_update.message.reply_text.call_args.args[0]
        assert mock_update.message.reply_text.call_args.kwargs.get("do_quote") is False
        mock_context.bot.send_message.assert_not_called()

    async def test_invalid_user_id_shows_usage(
        self, mock_update, mock_context, mock_registry
    ):
        """Non-numeric user ID shows usage error."""
        mock_context.args = ["not_a_number"]

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "Penggunaan" in mock_update.message.reply_text.call_args.args[0]

    async def test_get_chat_member_failure_shows_error(
        self, mock_update, mock_context, mock_registry
    ):
        """If get_chat_member fails, shows error."""
        mock_context.args = ["67890"]
        mock_context.bot.get_chat_member.side_effect = Exception("User not found")

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "67890" in mock_update.message.reply_text.call_args.args[0]
        mock_context.bot.send_message.assert_not_called()

    async def test_warn_bot_silent_ignore(
        self, mock_update, mock_context, mock_registry
    ):
        """Cannot warn a bot — silent ignore."""
        target = _make_target_user()
        target.is_bot = True
        mock_update.message.reply_to_message = _make_reply_message(target)
        mock_context.args = []

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.send_message.assert_not_called()

    async def test_warn_self_silent_ignore(
        self, mock_update, mock_context, mock_registry
    ):
        """Admin cannot warn themselves — silent ignore."""
        target = _make_target_user(user_id=12345)  # same as admin
        mock_update.message.reply_to_message = _make_reply_message(target)
        mock_context.args = []

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.send_message.assert_not_called()

    async def test_unmonitored_group_silent_ignore(
        self, mock_update, mock_context
    ):
        """Command in a non-monitored group is silently ignored."""
        with patch("bot.handlers.warn.get_group_config_for_update", return_value=None):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.send_message.assert_not_called()
        mock_update.message.reply_text.assert_not_called()
        mock_update.message.delete.assert_not_called()

    async def test_send_message_failure_does_not_break(
        self, mock_update, mock_context, mock_registry
    ):
        """If send_message fails, handler exits gracefully."""
        target = _make_target_user()
        mock_update.message.reply_to_message = _make_reply_message(target)
        mock_context.args = []
        mock_context.bot.send_message.side_effect = Exception("Flood control")

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        mock_update.message.delete.assert_called_once()

    async def test_delete_failure_does_not_break(
        self, mock_update, mock_context, mock_registry
    ):
        """Warning still sent even if message deletion fails."""
        from telegram.error import TelegramError
        target = _make_target_user()
        mock_update.message.reply_to_message = _make_reply_message(target)
        mock_context.args = []
        mock_update.message.delete.side_effect = TelegramError("no permission")

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        mock_update.message.delete.assert_called_once()

    async def test_reply_without_from_user_falls_to_id_mode(
        self, mock_update, mock_context, mock_registry
    ):
        """Reply to a channel message (no from_user) with ID arg uses ID mode."""
        target = _make_target_user()
        mock_context.bot.get_chat_member.return_value = _make_chat_member(target)
        mock_update.message.reply_to_message = MagicMock()
        mock_update.message.reply_to_message.from_user = None
        mock_update.message.reply_to_message.forum_topic_created = None
        mock_context.args = ["67890", "spam"]

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.get_chat_member.assert_called_once_with(
            chat_id=-1001234567890, user_id=67890
        )
        mock_context.bot.send_message.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args.kwargs
        assert "spam" in call_kwargs["text"]
        assert "badmember" in call_kwargs["text"]

    async def test_reason_with_markdown_is_escaped(
        self, mock_update, mock_context, mock_registry
    ):
        """Reason with Markdown metacharacters is escaped."""
        target = _make_target_user()
        mock_update.message.reply_to_message = _make_reply_message(target)
        mock_context.args = ["stop", "_spamming_", "and", "[links]"]

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args.kwargs
        text = call_kwargs["text"]
        assert "\\_spamming\\_" in text
        assert "\\[links]" in text

    async def test_moderation_topic_when_configured(
        self, mock_update, mock_context
    ):
        """When moderation_topic_id is set, warning goes to that topic."""
        config = GroupConfig(
            group_id=-1001234567890,
            warning_topic_id=12345,
            moderation_topic_id=67890,
            rules_link="https://t.me/test/rules",
        )
        registry = GroupRegistry()
        registry.register(config)

        target = _make_target_user()
        mock_update.message.reply_to_message = _make_reply_message(target)
        mock_context.args = []

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == -1001234567890
        assert call_kwargs["message_thread_id"] == 67890
        assert call_kwargs["message_thread_id"] != 12345
        mock_update.message.delete.assert_called_once()

    async def test_no_moderation_topic_sends_to_main_chat(
        self, mock_update, mock_context
    ):
        """When moderation_topic_id is None, warning goes to main chat."""
        config = GroupConfig(
            group_id=-1001234567890,
            warning_topic_id=12345,
            rules_link="https://t.me/test/rules",
        )
        registry = GroupRegistry()
        registry.register(config)

        target = _make_target_user()
        mock_update.message.reply_to_message = _make_reply_message(target)
        mock_context.args = []

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == -1001234567890
        assert "message_thread_id" not in call_kwargs

    async def test_moderation_topic_id_defaults_to_none(self):
        """moderation_topic_id defaults to None."""
        config = GroupConfig(
            group_id=-1001234567890,
            warning_topic_id=12345,
        )
        assert config.moderation_topic_id is None

    async def test_command_deleted_before_send_message(
        self, mock_update, mock_context, mock_registry
    ):
        """Command message is deleted before send_message is called."""
        target = _make_target_user()
        mock_update.message.reply_to_message = _make_reply_message(target)
        mock_context.args = []

        call_order = []

        async def mock_delete():
            call_order.append("delete")

        async def mock_send(**kwargs):
            call_order.append("send_message")

        mock_update.message.delete = AsyncMock(side_effect=mock_delete)
        mock_context.bot.send_message = AsyncMock(side_effect=mock_send)

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        assert call_order == ["delete", "send_message"]

    async def test_command_deleted_before_get_chat_member(
        self, mock_update, mock_context, mock_registry
    ):
        """Command message is deleted before get_chat_member is called in ID mode."""
        target = _make_target_user()
        mock_context.bot.get_chat_member.return_value = _make_chat_member(target)
        mock_context.args = ["67890"]

        call_order = []

        async def mock_delete():
            call_order.append("delete")

        async def mock_get_member(**kwargs):
            call_order.append("get_chat_member")
            return _make_chat_member(target)

        mock_update.message.delete = AsyncMock(side_effect=mock_delete)
        mock_context.bot.get_chat_member = AsyncMock(side_effect=mock_get_member)

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        assert call_order[0] == "delete"

    async def test_id_mode_takes_priority_over_reply(
        self, mock_update, mock_context, mock_registry
    ):
        """Bug fix: /warn USER_ID reason as a reply warns the ID target, not the replied-to user."""
        reply_target = _make_target_user(user_id=11111, full_name="Replied User", username="replieduser")
        id_target = _make_target_user(user_id=67890, full_name="ID Target", username="idtarget")
        mock_update.message.reply_to_message = _make_reply_message(reply_target)
        mock_context.bot.get_chat_member.return_value = _make_chat_member(id_target)
        mock_context.args = ["67890", "spamming"]

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.get_chat_member.assert_called_once_with(
            chat_id=-1001234567890, user_id=67890
        )
        mock_context.bot.send_message.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args.kwargs
        assert "idtarget" in call_kwargs["text"]
        assert "replieduser" not in call_kwargs["text"]
        assert "spamming" in call_kwargs["text"]

    async def test_forum_topic_anchor_not_treated_as_reply(
        self, mock_update, mock_context, mock_registry
    ):
        """Bug fix: forum topic anchor (auto reply_to_message) is not treated as a real reply."""
        target = _make_target_user()
        mock_context.bot.get_chat_member.return_value = _make_chat_member(target)
        # Simulate a forum topic anchor: reply_to_message exists with forum_topic_created set
        mock_update.message.reply_to_message = MagicMock()
        mock_update.message.reply_to_message.from_user = _make_target_user(user_id=11111, full_name="Topic Creator")
        mock_update.message.reply_to_message.forum_topic_created = MagicMock()
        mock_context.args = ["67890", "reason"]

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.get_chat_member.assert_called_once_with(
            chat_id=-1001234567890, user_id=67890
        )
        mock_context.bot.send_message.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args.kwargs
        assert "badmember" in call_kwargs["text"]
        assert "11111" not in call_kwargs["text"]

    async def test_forum_topic_anchor_no_args_shows_usage(
        self, mock_update, mock_context, mock_registry
    ):
        """Forum topic anchor with no args shows usage (not treated as reply)."""
        mock_update.message.reply_to_message = MagicMock()
        mock_update.message.reply_to_message.from_user = _make_target_user(user_id=11111)
        mock_update.message.reply_to_message.forum_topic_created = MagicMock()
        mock_context.args = []

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "Penggunaan" in mock_update.message.reply_text.call_args.args[0]
        mock_context.bot.send_message.assert_not_called()

    async def test_username_mode_with_reason(
        self, mock_update, mock_context, mock_registry
    ):
        """Admin uses /warn @username <reason>."""
        mock_context.args = ["@badmember", "stop", "spamming"]

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.get_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args.kwargs
        assert "@badmember" in call_kwargs["text"]
        assert "stop spamming" in call_kwargs["text"]

    async def test_username_mode_without_reason(
        self, mock_update, mock_context, mock_registry
    ):
        """Admin uses /warn @username with no reason."""
        mock_context.args = ["@badmember"]

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.get_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args.kwargs
        assert "@badmember" in call_kwargs["text"]
        assert "patuhi aturan grup" in call_kwargs["text"]

    async def test_username_mode_takes_priority_over_reply(
        self, mock_update, mock_context, mock_registry
    ):
        """@username takes priority over a real reply."""
        reply_target = _make_target_user(user_id=11111, full_name="Replied User", username="replieduser")
        mock_update.message.reply_to_message = _make_reply_message(reply_target)
        mock_context.args = ["@badmember", "reason"]

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.get_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args.kwargs
        assert "@badmember" in call_kwargs["text"]
        assert "replieduser" not in call_kwargs["text"]
        assert "reason" in call_kwargs["text"]

    async def test_username_mode_skips_bot_and_self_checks(
        self, mock_update, mock_context, mock_registry
    ):
        """Username mode cannot check is_bot/self since we don't have the User object."""
        mock_context.args = ["@somebot"]

        with patch("bot.handlers.warn.get_group_config_for_update", return_value=mock_registry.get(-1001234567890)):
            await handle_warn_command(mock_update, mock_context)

        mock_context.bot.send_message.assert_called_once()
