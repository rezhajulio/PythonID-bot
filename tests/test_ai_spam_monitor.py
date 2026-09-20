"""Tests for the AI spam monitor handler (classifier.dev, monitor-only)."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import CallbackQuery, Chat, Message, User
from telegram.error import BadRequest

from bot.group_config import GroupConfig
from bot.handlers import ai_spam_monitor
from bot.handlers.ai_spam_monitor import (
    ACTION_DELETE,
    ACTION_DELETE_BAN,
    ACTION_DELETE_RESTRICT,
    ACTION_DISMISS,
    ALERTS_KEY,
    handle_ai_spam_action,
    handle_ai_spam_monitor,
    truncate_alert_text,
)
from bot.services import classifier_client
from bot.services.classifier_client import ClassificationResult, circuit_on_failure
from bot.services.user_checker import ProfileCheckResult

GROUP_ID = -100
ALERT_CHAT_ID = -999
LONG_TEXT = "Jasa pencarian data orang, harga murah, minat chat privat ya kak"


@pytest.fixture(autouse=True)
async def reset_classifier_state():
    classifier_client.reset_shared_state()
    yield
    await classifier_client.close_client()


def make_settings(**overrides) -> MagicMock:
    settings = MagicMock()
    settings.ai_spam_daily_budget = 15_000
    settings.ai_spam_alert_threshold = 0.9
    settings.classifier_timeout_seconds = 5.0
    settings.classifier_cooldown_seconds = 600.0
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def make_group_config(alert_chat_id: int | None = ALERT_CHAT_ID) -> GroupConfig:
    return GroupConfig(
        group_id=GROUP_ID,
        warning_topic_id=11,
        ai_spam_alert_chat_id=alert_chat_id,
    )


def make_spam_result(confidence: float | None = 0.97) -> ClassificationResult:
    return ClassificationResult(label="spam", confidence=confidence, model="jev-1.13.0")


def make_context() -> MagicMock:
    context = MagicMock()
    context.bot_data = {"group_admin_ids": {GROUP_ID: [1, 2]}}
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.delete_message = AsyncMock()
    context.bot.ban_chat_member = AsyncMock()
    context.bot.restrict_chat_member = AsyncMock()
    application = MagicMock()
    application.create_task = MagicMock(
        side_effect=lambda coro, update=None: coro.close()
    )
    context.application = application
    return context


def make_update(
    text: str | None = LONG_TEXT,
    user_id: int = 42,
    is_bot: bool = False,
    message_id: int = 100,
) -> MagicMock:
    update = MagicMock()
    update.message = None
    update.effective_message = MagicMock(spec=Message)
    update.effective_message.text = text
    update.effective_message.message_id = message_id
    update.effective_message.chat_id = GROUP_ID
    update.effective_user = MagicMock(spec=User)
    update.effective_user.id = user_id
    update.effective_user.is_bot = is_bot
    update.effective_user.full_name = "Test User"
    update.effective_user.username = "testuser"
    update.effective_user.first_name = "Test"
    update.effective_chat = MagicMock(spec=Chat)
    update.effective_chat.id = GROUP_ID
    return update


class TestTruncateAlertText:
    """Tests for truncate_alert_text."""

    def test_short_text_untouched(self):
        assert truncate_alert_text("halo") == "halo"

    def test_long_text_truncated_with_ellipsis(self):
        text = "a" * 600
        result = truncate_alert_text(text)
        assert len(result) == ai_spam_monitor.AI_SPAM_ALERT_MESSAGE_MAX_LEN + 1
        assert result.endswith("…")


class TestBuildAlertKeyboard:
    """Tests for build_alert_keyboard."""

    def test_four_buttons_with_encoded_ids(self):
        keyboard = ai_spam_monitor.build_alert_keyboard(GROUP_ID, 42, 100)
        callback_data = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
        assert callback_data == [
            "aispam:del:-100:42:100",
            "aispam:dismiss:-100:42:100",
            "aispam:delres:-100:42:100",
            "aispam:delban:-100:42:100",
        ]


class TestHandleAiSpamMonitor:
    """Tests for the last-defense entry handler."""

    @pytest.fixture
    def context(self) -> MagicMock:
        return make_context()

    @patch("bot.handlers.ai_spam_monitor.get_settings")
    async def test_skips_non_admin_short_text(self, mock_settings, context):
        mock_settings.return_value = make_settings()
        update = make_update(text="ok siap")
        await handle_ai_spam_monitor(update, context)
        context.application.create_task.assert_not_called()

    @patch("bot.handlers.ai_spam_monitor.get_settings")
    async def test_skips_media_message(self, mock_settings, context):
        mock_settings.return_value = make_settings()
        update = make_update(text=None)
        await handle_ai_spam_monitor(update, context)
        context.application.create_task.assert_not_called()

    @patch("bot.handlers.ai_spam_monitor.get_settings")
    async def test_skips_bot_user(self, mock_settings, context):
        mock_settings.return_value = make_settings()
        update = make_update(user_id=99, is_bot=True)
        await handle_ai_spam_monitor(update, context)
        context.application.create_task.assert_not_called()

    @patch("bot.handlers.ai_spam_monitor.get_settings")
    async def test_skips_admin(self, mock_settings, context):
        mock_settings.return_value = make_settings()
        update = make_update(user_id=1)
        await handle_ai_spam_monitor(update, context)
        context.application.create_task.assert_not_called()

    @patch("bot.handlers.ai_spam_monitor.get_settings")
    async def test_skips_when_budget_exhausted(self, mock_settings, context):
        mock_settings.return_value = make_settings(ai_spam_daily_budget=0)
        update = make_update()
        await handle_ai_spam_monitor(update, context)
        context.application.create_task.assert_not_called()

    @patch("bot.handlers.ai_spam_monitor.breaker_is_open")
    @patch("bot.handlers.ai_spam_monitor.get_settings")
    async def test_skips_when_breaker_open(self, mock_settings, mock_breaker, context):
        mock_settings.return_value = make_settings()
        mock_breaker.return_value = True
        update = make_update()
        await handle_ai_spam_monitor(update, context)
        context.application.create_task.assert_not_called()

    @patch("bot.handlers.ai_spam_monitor.get_settings")
    async def test_spawns_background_task_for_regular_user(self, mock_settings, context):
        mock_settings.return_value = make_settings()
        update = make_update()
        await handle_ai_spam_monitor(update, context)
        context.application.create_task.assert_called_once()

    @patch("bot.handlers.ai_spam_monitor.get_settings")
    async def test_skips_trusted_user(self, mock_settings, context):
        mock_settings.return_value = make_settings()
        context.bot_data["trusted_user_ids"] = {42}
        update = make_update()
        await handle_ai_spam_monitor(update, context)
        context.application.create_task.assert_not_called()


class TestClassifyAndAlert:
    """Tests for the background classification + alert coroutine."""

    @pytest.fixture
    def context(self) -> MagicMock:
        return make_context()

    async def alert_on(
        self,
        context: MagicMock,
        result: ClassificationResult | None = make_spam_result(),
        alert_chat_id: int | None = ALERT_CHAT_ID,
        profile: ProfileCheckResult | None = None,
    ) -> None:
        with (
            patch("bot.handlers.ai_spam_monitor.classify_text", new=AsyncMock(return_value=result)),
            patch("bot.handlers.ai_spam_monitor.get_settings", return_value=make_settings()),
            patch("bot.handlers.ai_spam_monitor.get_group_registry") as mock_registry,
            patch(
                "bot.handlers.ai_spam_monitor.check_user_profile",
                new=AsyncMock(return_value=profile or ProfileCheckResult(True, True)),
            ),
        ):
            mock_registry.return_value.get.return_value = make_group_config(alert_chat_id)
            await ai_spam_monitor._classify_and_alert(
                context,
                group_id=GROUP_ID,
                user=make_update().effective_user,
                message_id=100,
                message_text=LONG_TEXT,
            )

    async def test_sends_alert_on_high_confidence(self, context):
        await self.alert_on(context, profile=ProfileCheckResult(False, False))
        context.bot.send_message.assert_awaited_once()
        kwargs = context.bot.send_message.await_args.kwargs
        assert kwargs["chat_id"] == ALERT_CHAT_ID
        assert "[AI SPAM MONITOR]" in kwargs["text"]
        assert "@testuser" in kwargs["text"]
        assert "97%" in kwargs["text"]
        assert "jev-1.13.0" in kwargs["text"]
        assert "foto profil publik" in kwargs["text"]
        assert kwargs["reply_markup"] is not None

    async def test_alert_mention_plain_without_username(self, context):
        update = make_update()
        update.effective_user.username = None
        update.effective_user.full_name = "Test User"
        with (
            patch("bot.handlers.ai_spam_monitor.classify_text", new=AsyncMock(return_value=make_spam_result())),
            patch("bot.handlers.ai_spam_monitor.get_settings", return_value=make_settings()),
            patch("bot.handlers.ai_spam_monitor.get_group_registry") as mock_registry,
            patch(
                "bot.handlers.ai_spam_monitor.check_user_profile",
                new=AsyncMock(return_value=ProfileCheckResult(True, True)),
            ),
        ):
            mock_registry.return_value.get.return_value = make_group_config()
            await ai_spam_monitor._classify_and_alert(
                context,
                group_id=GROUP_ID,
                user=update.effective_user,
                message_id=100,
                message_text=LONG_TEXT,
            )
        text = context.bot.send_message.await_args.kwargs["text"]
        assert "Test User (ID: 42)" in text
        assert "tg://user" not in text
        assert "\\_" not in text

    async def test_no_alert_below_threshold(self, context):
        await self.alert_on(context, result=make_spam_result(confidence=0.5))
        context.bot.send_message.assert_not_awaited()

    async def test_no_alert_on_null_confidence(self, context):
        await self.alert_on(context, result=make_spam_result(confidence=None))
        context.bot.send_message.assert_not_awaited()

    async def test_no_alert_for_not_spam_label(self, context):
        result = ClassificationResult(label="not spam", confidence=1.0)
        await self.alert_on(context, result=result)
        context.bot.send_message.assert_not_awaited()

    async def test_no_alert_without_alert_chat(self, context):
        await self.alert_on(context, alert_chat_id=None)
        context.bot.send_message.assert_not_awaited()

    async def test_no_alert_when_classification_fails(self, context):
        await self.alert_on(context, result=None)
        context.bot.send_message.assert_not_awaited()

    async def test_no_alert_without_registry_group(self, context):
        with (
            patch("bot.handlers.ai_spam_monitor.classify_text", new=AsyncMock(return_value=make_spam_result())),
            patch("bot.handlers.ai_spam_monitor.get_settings", return_value=make_settings()),
            patch("bot.handlers.ai_spam_monitor.get_group_registry") as mock_registry,
        ):
            mock_registry.return_value.get.return_value = None
            await ai_spam_monitor._classify_and_alert(
                context,
                group_id=GROUP_ID,
                user=make_update().effective_user,
                message_id=100,
                message_text=LONG_TEXT,
            )
        context.bot.send_message.assert_not_awaited()

    async def test_skips_when_circuit_open(self, context):
        state = classifier_client.get_circuit_state()
        for _ in range(3):
            circuit_on_failure(state, now=time.monotonic())
        with (
            patch("bot.handlers.ai_spam_monitor.classify_text", new=AsyncMock()) as mock_classify,
            patch("bot.handlers.ai_spam_monitor.get_settings", return_value=make_settings()),
        ):
            await ai_spam_monitor._classify_and_alert(
                context,
                group_id=GROUP_ID,
                user=make_update().effective_user,
                message_id=100,
                message_text=LONG_TEXT,
            )
        mock_classify.assert_not_awaited()
        context.bot.send_message.assert_not_awaited()

    async def test_skips_when_budget_spent(self, context):
        with (
            patch("bot.handlers.ai_spam_monitor.classify_text", new=AsyncMock()) as mock_classify,
            patch(
                "bot.handlers.ai_spam_monitor.get_settings",
                return_value=make_settings(ai_spam_daily_budget=0),
            ),
        ):
            await ai_spam_monitor._classify_and_alert(
                context,
                group_id=GROUP_ID,
                user=make_update().effective_user,
                message_id=100,
                message_text=LONG_TEXT,
            )
        mock_classify.assert_not_awaited()

    async def test_dedup_same_message(self, context):
        await self.alert_on(context)
        await self.alert_on(context)
        context.bot.send_message.assert_awaited_once()
        assert (GROUP_ID, 100) in context.bot_data[ALERTS_KEY]

    async def test_profile_check_failure_still_alerts(self, context):
        with (
            patch("bot.handlers.ai_spam_monitor.classify_text", new=AsyncMock(return_value=make_spam_result())),
            patch("bot.handlers.ai_spam_monitor.get_settings", return_value=make_settings()),
            patch("bot.handlers.ai_spam_monitor.get_group_registry") as mock_registry,
            patch(
                "bot.handlers.ai_spam_monitor.check_user_profile",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
        ):
            mock_registry.return_value.get.return_value = make_group_config()
            await ai_spam_monitor._classify_and_alert(
                context,
                group_id=GROUP_ID,
                user=make_update().effective_user,
                message_id=100,
                message_text=LONG_TEXT,
            )
        context.bot.send_message.assert_awaited_once()
        assert "tidak diketahui" in context.bot.send_message.await_args.kwargs["text"]

    async def test_send_failure_is_swallowed(self, context):
        context.bot.send_message = AsyncMock(side_effect=RuntimeError("telegram down"))
        await self.alert_on(context)
        assert (GROUP_ID, 100) in context.bot_data[ALERTS_KEY]

    async def test_registry_runtime_error_returns_none(self, context):
        with (
            patch("bot.handlers.ai_spam_monitor.classify_text", new=AsyncMock(return_value=make_spam_result())),
            patch("bot.handlers.ai_spam_monitor.get_settings", return_value=make_settings()),
            patch(
                "bot.handlers.ai_spam_monitor.get_group_registry",
                side_effect=RuntimeError("not initialized"),
            ),
        ):
            assert (
                ai_spam_monitor._get_group_config(context, GROUP_ID) is None
            )
            await ai_spam_monitor._classify_and_alert(
                context,
                group_id=GROUP_ID,
                user=make_update().effective_user,
                message_id=100,
                message_text=LONG_TEXT,
            )
        context.bot.send_message.assert_not_awaited()

    async def test_alert_dedup_evicts_old_entries(self, context):
        alerts = {(i, i): 0 for i in range(ai_spam_monitor.ALERTS_MAX_SIZE)}
        context.bot_data[ALERTS_KEY] = alerts
        await self.alert_on(context)
        assert len(context.bot_data[ALERTS_KEY]) < ai_spam_monitor.ALERTS_MAX_SIZE
        assert (GROUP_ID, 100) in context.bot_data[ALERTS_KEY]
        context.bot.send_message.assert_awaited_once()


def make_callback_update(action: str, admin_id: int = 1) -> MagicMock:
    update = MagicMock()
    update.callback_query = MagicMock(spec=CallbackQuery)
    update.callback_query.data = f"aispam:{action}:{GROUP_ID}:42:100"
    update.callback_query.from_user = MagicMock(spec=User)
    update.callback_query.from_user.id = admin_id
    update.callback_query.from_user.full_name = "Admin"
    update.callback_query.from_user.username = "admin"
    update.callback_query.message = MagicMock(spec=Message)
    update.callback_query.message.text = "[AI SPAM MONITOR]\nPesan"
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    return update


class TestHandleAiSpamAction:
    """Tests for the admin action callback handler."""

    async def test_non_admin_rejected(self):
        context = make_context()
        update = make_callback_update(ACTION_DELETE, admin_id=77)
        await handle_ai_spam_action(update, context)
        update.callback_query.answer.assert_awaited_once_with(
            ai_spam_monitor.AI_SPAM_CB_NOT_ADMIN, show_alert=True
        )
        context.bot.delete_message.assert_not_awaited()

    async def test_delete_removes_message_and_marks_handled(self):
        context = make_context()
        update = make_callback_update(ACTION_DELETE)
        await handle_ai_spam_action(update, context)
        context.bot.delete_message.assert_awaited_once_with(
            chat_id=GROUP_ID, message_id=100
        )
        update.callback_query.edit_message_text.assert_awaited_once()
        text = update.callback_query.edit_message_text.await_args.args[0]
        assert "hapus pesan" in text
        assert "@admin" in text

    async def test_dismiss_does_not_delete(self):
        context = make_context()
        update = make_callback_update(ACTION_DISMISS)
        await handle_ai_spam_action(update, context)
        context.bot.delete_message.assert_not_awaited()
        context.bot.restrict_chat_member.assert_not_awaited()
        context.bot.ban_chat_member.assert_not_awaited()
        text = update.callback_query.edit_message_text.await_args.args[0]
        assert "abaikan" in text

    async def test_delete_restrict_restricts_member(self):
        context = make_context()
        update = make_callback_update(ACTION_DELETE_RESTRICT)
        with patch("bot.handlers.ai_spam_monitor.restrict_chat_member_with_retry", new=AsyncMock(return_value=True)) as mock_restrict:
            await handle_ai_spam_action(update, context)
        mock_restrict.assert_awaited_once()
        context.bot.ban_chat_member.assert_not_awaited()
        text = update.callback_query.edit_message_text.await_args.args[0]
        assert "hapus + batasi" in text

    async def test_delete_ban_bans_member(self):
        context = make_context()
        update = make_callback_update(ACTION_DELETE_BAN)
        await handle_ai_spam_action(update, context)
        context.bot.ban_chat_member.assert_awaited_once_with(
            chat_id=GROUP_ID, user_id=42
        )
        text = update.callback_query.edit_message_text.await_args.args[0]
        assert "hapus + ban" in text

    async def test_gone_message_notes_it_but_still_bans(self):
        context = make_context()
        context.bot.delete_message = AsyncMock(side_effect=BadRequest("message to delete not found"))
        update = make_callback_update(ACTION_DELETE_BAN)
        await handle_ai_spam_action(update, context)
        context.bot.ban_chat_member.assert_awaited_once()
        text = update.callback_query.edit_message_text.await_args.args[0]
        assert ai_spam_monitor.AI_SPAM_CB_MESSAGE_GONE in text

    async def test_failed_ban_noted_in_alert(self):
        context = make_context()
        context.bot.ban_chat_member = AsyncMock(side_effect=BadRequest("not enough rights"))
        update = make_callback_update(ACTION_DELETE_BAN)
        await handle_ai_spam_action(update, context)
        text = update.callback_query.edit_message_text.await_args.args[0]
        assert "ban gagal" in text

    async def test_admin_of_other_group_rejected(self):
        context = make_context()
        update = MagicMock()
        update.callback_query = MagicMock(spec=CallbackQuery)
        update.callback_query.data = f"aispam:{ACTION_DELETE}:-200:42:100"
        update.callback_query.from_user = MagicMock(spec=User)
        update.callback_query.from_user.id = 1
        update.callback_query.answer = AsyncMock()
        await handle_ai_spam_action(update, context)
        update.callback_query.answer.assert_awaited_once_with(
            ai_spam_monitor.AI_SPAM_CB_NOT_ADMIN, show_alert=True
        )
        context.bot.delete_message.assert_not_awaited()

    async def test_no_callback_query_ignored(self):
        context = make_context()
        update = MagicMock()
        update.callback_query = None
        await handle_ai_spam_action(update, context)
        context.bot.delete_message.assert_not_awaited()

    async def test_no_callback_data_ignored(self):
        context = make_context()
        update = MagicMock()
        update.callback_query = MagicMock(spec=CallbackQuery)
        update.callback_query.data = None
        await handle_ai_spam_action(update, context)
        context.bot.delete_message.assert_not_awaited()

    async def test_restrict_retry_failure_noted(self):
        context = make_context()
        update = make_callback_update(ACTION_DELETE_RESTRICT)
        with patch(
            "bot.handlers.ai_spam_monitor.restrict_chat_member_with_retry",
            new=AsyncMock(return_value=False),
        ):
            await handle_ai_spam_action(update, context)
        text = update.callback_query.edit_message_text.await_args.args[0]
        assert "pembatasan gagal" in text

    async def test_restrict_exception_noted(self):
        context = make_context()
        update = make_callback_update(ACTION_DELETE_RESTRICT)
        with patch(
            "bot.handlers.ai_spam_monitor.restrict_chat_member_with_retry",
            new=AsyncMock(side_effect=BadRequest("not enough rights")),
        ):
            await handle_ai_spam_action(update, context)
        text = update.callback_query.edit_message_text.await_args.args[0]
        assert "pembatasan gagal" in text

    async def test_edit_failure_logged_not_raised(self):
        context = make_context()
        update = make_callback_update(ACTION_DELETE)
        update.callback_query.edit_message_text = AsyncMock(
            side_effect=BadRequest("cannot edit")
        )
        await handle_ai_spam_action(update, context)
        update.callback_query.answer.assert_awaited_once()


class TestGetHandlers:
    """Tests for get_handlers."""

    def test_returns_message_and_callback_handlers(self):
        from telegram.ext import CallbackQueryHandler, MessageHandler

        handlers = ai_spam_monitor.get_handlers()
        assert len(handlers) == 2
        assert isinstance(handlers[0], MessageHandler)
        assert isinstance(handlers[1], CallbackQueryHandler)
