"""Tests for the /testalert DM admin command."""

from unittest.mock import AsyncMock, MagicMock, patch

from bot.dispatch import AppState, HandlerContext
from bot.handlers.testalert import get_handlers, handle_testalert_command

GROUP_ID = -1001052242766
ALERT_CHAT_ID = -100999888777


def make_update(chat_type="private", user_id=1, args_text="/testalert"):
    update = MagicMock()
    message = MagicMock()
    message.text = args_text
    message.reply = AsyncMock()
    chat = MagicMock()
    chat.id = 111
    chat.type = chat_type
    message.chat = chat
    user = MagicMock()
    user.id = user_id
    message.from_user = user
    update.message = message
    update.edited_message = None
    update.callback_query = None
    update.chat_member = None
    return update


def make_context(admin_ids=(1,)):
    bot = MagicMock()
    bot.send_message = AsyncMock()
    state = AppState(bot=bot)
    state.admin_ids = set(admin_ids)
    context = HandlerContext(bot=bot, state=state)
    context.args = []
    return context


def make_group_config(alert_chat_id=ALERT_CHAT_ID):
    config = MagicMock()
    config.ai_spam_alert_chat_id = alert_chat_id
    return config


class TestHandleTestalertCommand:
    @patch("bot.handlers.testalert.get_admin_groups")
    @patch("bot.handlers.testalert.get_group_registry")
    async def test_rejects_group_chat(self, mock_registry, mock_admin_groups):
        update = make_update(chat_type="supergroup")
        context = make_context()
        await handle_testalert_command(update, context)
        update.message.reply.assert_called_once()
        assert "pribadi" in update.message.reply.call_args.args[0]
        context.bot.send_message.assert_not_called()

    @patch("bot.handlers.testalert.get_admin_groups")
    @patch("bot.handlers.testalert.get_group_registry")
    async def test_rejects_non_admin(self, mock_registry, mock_admin_groups):
        update = make_update(user_id=99)
        context = make_context()
        await handle_testalert_command(update, context)
        update.message.reply.assert_called_once()
        assert "izin" in update.message.reply.call_args.args[0]
        context.bot.send_message.assert_not_called()

    @patch("bot.handlers.testalert.get_admin_groups")
    @patch("bot.handlers.testalert.get_group_registry")
    async def test_reports_unconfigured_alert_chat(
        self, mock_registry, mock_admin_groups
    ):
        mock_admin_groups.return_value = [GROUP_ID]
        mock_registry.return_value.get.return_value = make_group_config(
            alert_chat_id=None
        )
        update = make_update()
        context = make_context()
        await handle_testalert_command(update, context)
        context.bot.send_message.assert_not_called()
        reply_text = update.message.reply.call_args.args[0]
        assert "belum dikonfigurasi" in reply_text

    @patch("bot.handlers.testalert.get_admin_groups")
    @patch("bot.handlers.testalert.get_group_registry")
    async def test_sends_test_alert_on_success(
        self, mock_registry, mock_admin_groups
    ):
        mock_admin_groups.return_value = [GROUP_ID]
        mock_registry.return_value.get.return_value = make_group_config()
        update = make_update()
        context = make_context()
        await handle_testalert_command(update, context)
        context.bot.send_message.assert_called_once()
        call_kwargs = context.bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == ALERT_CHAT_ID
        assert "Test Alert" in call_kwargs["text"]
        reply_text = update.message.reply.call_args.args[0]
        assert "✅" in reply_text
        assert str(ALERT_CHAT_ID) in reply_text

    @patch("bot.handlers.testalert.get_admin_groups")
    @patch("bot.handlers.testalert.get_group_registry")
    async def test_reports_send_failure(self, mock_registry, mock_admin_groups):
        mock_admin_groups.return_value = [GROUP_ID]
        mock_registry.return_value.get.return_value = make_group_config()
        update = make_update()
        context = make_context()
        context.bot.send_message.side_effect = RuntimeError("chat not found")
        await handle_testalert_command(update, context)
        reply_text = update.message.reply.call_args.args[0]
        assert "❌" in reply_text
        assert "chat not found" in reply_text

    @patch("bot.handlers.testalert.get_admin_groups")
    @patch("bot.handlers.testalert.get_group_registry")
    async def test_group_id_arg_scopes_to_one_group(
        self, mock_registry, mock_admin_groups
    ):
        mock_admin_groups.return_value = [GROUP_ID, -200]
        mock_registry.return_value.get.return_value = make_group_config()
        update = make_update(args_text=f"/testalert {GROUP_ID}")
        context = make_context()
        context.args = [str(GROUP_ID)]
        await handle_testalert_command(update, context)
        assert context.bot.send_message.call_count == 1
        mock_registry.return_value.get.assert_called_once_with(GROUP_ID)

    @patch("bot.handlers.testalert.get_admin_groups")
    @patch("bot.handlers.testalert.get_group_registry")
    async def test_rejects_group_id_not_administered(
        self, mock_registry, mock_admin_groups
    ):
        mock_admin_groups.return_value = [GROUP_ID]
        update = make_update(args_text="/testalert -999")
        context = make_context()
        context.args = ["-999"]
        await handle_testalert_command(update, context)
        context.bot.send_message.assert_not_called()
        assert "bukan admin" in update.message.reply.call_args.args[0]

    @patch("bot.handlers.testalert.get_admin_groups")
    @patch("bot.handlers.testalert.get_group_registry")
    async def test_rejects_invalid_arg(self, mock_registry, mock_admin_groups):
        mock_admin_groups.return_value = [GROUP_ID]
        update = make_update(args_text="/testalert abc")
        context = make_context()
        context.args = ["abc"]
        await handle_testalert_command(update, context)
        context.bot.send_message.assert_not_called()
        assert "Format" in update.message.reply.call_args.args[0]


class TestGetHandlers:
    def test_returns_command_spec(self):
        state = AppState(bot=MagicMock())
        state.bot_username = "testbot"
        specs = get_handlers(state)
        assert len(specs) == 1
        spec = specs[0]
        assert spec.plugin_name == "testalert"
        assert spec.label == "testalert_command"
        assert spec.command == "testalert"
        assert spec.group == 0
