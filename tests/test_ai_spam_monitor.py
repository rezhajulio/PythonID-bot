"""Tests for the AI spam monitor handler (classifier.dev, monitor-only)."""

import logging
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest

from bot.dispatch import AppState, HandlerContext

from bot.group_config import GroupConfig
from bot.handlers import ai_spam_monitor
from bot.handlers.ai_spam_monitor import (
    ACTION_DELETE,
    ACTION_DELETE_BAN,
    ACTION_DELETE_RESTRICT,
    ACTION_DISMISS,
    ALERTS_KEY,
    ai_spam_filter,
    flagged_aspects,
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
    result = ClassificationResult(label="spam", confidence=confidence, model="jev-1.13.0")
    if confidence is not None:
        result.labels = ["spam"]
        result.scores = {"spam": confidence, "hostile": 0.01, "trolling": 0.02, "benign": 0.02}
    return result


def make_multi_result(
    scores: dict[str, float], labels: list[str] | None = None
) -> ClassificationResult:
    qualifying = (
        labels
        if labels is not None
        else [label for label, score in scores.items() if score >= 0.7]
    )
    top = max(scores, key=scores.get)
    return ClassificationResult(
        label=qualifying[0] if qualifying else top,
        confidence=scores[qualifying[0]] if qualifying else scores[top],
        model="jev-1.13.0",
        labels=qualifying,
        scores=scores,
    )


def make_context() -> HandlerContext:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.delete_message = AsyncMock()
    bot.ban_chat_member = AsyncMock()
    bot.restrict_chat_member = AsyncMock()
    state = AppState(bot=bot)
    state.group_admin_ids = {GROUP_ID: [1, 2]}
    state.trusted_user_ids = set()
    context = HandlerContext(bot=bot, state=state)
    context.create_task = MagicMock(side_effect=lambda coro: coro.close())  # type: ignore[method-assign]
    return context


def make_update(
    text: str | None = LONG_TEXT,
    user_id: int = 42,
    is_bot: bool = False,
    message_id: int = 100,
    caption: str | None = None,
) -> MagicMock:
    update = MagicMock()
    message = MagicMock()
    message.text = text
    message.caption = caption
    message.message_id = message_id
    chat = MagicMock()
    chat.id = GROUP_ID
    chat.type = "supergroup"
    message.chat = chat
    user = MagicMock()
    user.id = user_id
    user.is_bot = is_bot
    user.full_name = "Test User"
    user.username = "testuser"
    user.first_name = "Test"
    message.from_user = user
    update.message = message
    update.edited_message = None
    update.callback_query = None
    update.chat_member = None
    # Convenience aliases used by tests (not read by the handler itself)
    update.effective_message = message
    update.effective_user = user
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
    def context(self) -> HandlerContext:
        return make_context()

    @patch("bot.handlers.ai_spam_monitor.get_settings")
    async def test_skips_non_admin_short_text(self, mock_settings, context):
        mock_settings.return_value = make_settings()
        update = make_update(text="ok siap")
        await handle_ai_spam_monitor(update, context)
        context.create_task.assert_not_called()

    @patch("bot.handlers.ai_spam_monitor.get_settings")
    async def test_skips_media_message_without_caption(self, mock_settings, context):
        mock_settings.return_value = make_settings()
        update = make_update(text=None, caption=None)
        await handle_ai_spam_monitor(update, context)
        context.create_task.assert_not_called()

    @patch("bot.handlers.ai_spam_monitor.get_settings")
    async def test_spawns_task_for_caption_message(self, mock_settings, context):
        mock_settings.return_value = make_settings()
        update = make_update(text=None, caption=LONG_TEXT)
        await handle_ai_spam_monitor(update, context)
        context.create_task.assert_called_once()

    @patch("bot.handlers.ai_spam_monitor.get_settings")
    async def test_skips_short_caption(self, mock_settings, context):
        mock_settings.return_value = make_settings()
        update = make_update(text=None, caption="ok siap")
        await handle_ai_spam_monitor(update, context)
        context.create_task.assert_not_called()

    @patch("bot.handlers.ai_spam_monitor.get_settings")
    async def test_skips_bot_user(self, mock_settings, context):
        mock_settings.return_value = make_settings()
        update = make_update(user_id=99, is_bot=True)
        await handle_ai_spam_monitor(update, context)
        context.create_task.assert_not_called()

    @patch("bot.handlers.ai_spam_monitor.get_settings")
    async def test_skips_admin(self, mock_settings, context):
        mock_settings.return_value = make_settings()
        update = make_update(user_id=1)
        await handle_ai_spam_monitor(update, context)
        context.create_task.assert_not_called()

    @patch("bot.handlers.ai_spam_monitor.get_settings")
    async def test_skips_when_budget_exhausted(self, mock_settings, context):
        mock_settings.return_value = make_settings(ai_spam_daily_budget=0)
        update = make_update()
        await handle_ai_spam_monitor(update, context)
        context.create_task.assert_not_called()

    @patch("bot.handlers.ai_spam_monitor.breaker_is_open")
    @patch("bot.handlers.ai_spam_monitor.get_settings")
    async def test_skips_when_breaker_open(self, mock_settings, mock_breaker, context):
        mock_settings.return_value = make_settings()
        mock_breaker.return_value = True
        update = make_update()
        await handle_ai_spam_monitor(update, context)
        context.create_task.assert_not_called()

    @patch("bot.handlers.ai_spam_monitor.get_settings")
    async def test_spawns_background_task_for_regular_user(self, mock_settings, context):
        mock_settings.return_value = make_settings()
        update = make_update()
        await handle_ai_spam_monitor(update, context)
        context.create_task.assert_called_once()

    @patch("bot.handlers.ai_spam_monitor.get_settings")
    async def test_skips_trusted_user(self, mock_settings, context):
        mock_settings.return_value = make_settings()
        context.state.trusted_user_ids = {42}
        update = make_update()
        await handle_ai_spam_monitor(update, context)
        context.create_task.assert_not_called()


class TestAiSpamFilter:
    """Tests for the group-7 filter: text or caption, never commands."""

    def test_matches_text_message(self):
        assert ai_spam_filter(make_update(text=LONG_TEXT)) is True

    def test_matches_caption_message(self):
        assert ai_spam_filter(make_update(text=None, caption=LONG_TEXT)) is True

    def test_rejects_media_without_caption(self):
        assert ai_spam_filter(make_update(text=None, caption=None)) is False

    def test_rejects_blank_text_and_caption(self):
        assert ai_spam_filter(make_update(text="   ", caption="  ")) is False


class TestClassifyAndAlert:
    """Tests for the background classification + alert coroutine."""

    @pytest.fixture
    def context(self) -> HandlerContext:
        return make_context()

    async def alert_on(
        self,
        context: HandlerContext,
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

    async def test_sends_multi_aspect_alert(self, context):
        result = make_multi_result(
            {"spam": 0.97, "hostile": 0.91, "trolling": 0.1, "benign": 0.01}
        )
        await self.alert_on(context, result=result)
        context.bot.send_message.assert_awaited_once()
        text = context.bot.send_message.await_args.kwargs["text"]
        assert "Alasan: spam (97%), hostile (91%)" in text
        assert "Model: jev-1.13.0" in text

    async def test_sends_hostile_only_alert(self, context):
        result = make_multi_result(
            {"spam": 0.02, "hostile": 0.95, "trolling": 0.1, "benign": 0.03}
        )
        await self.alert_on(context, result=result)
        context.bot.send_message.assert_awaited_once()
        text = context.bot.send_message.await_args.kwargs["text"]
        assert "Alasan: hostile (95%)" in text
        assert "spam (" not in text

    async def test_sends_scam_only_alert(self, context):
        result = make_multi_result(
            {"spam": 0.05, "scam": 0.96, "hostile": 0.1, "benign": 0.02}
        )
        await self.alert_on(context, result=result)
        context.bot.send_message.assert_awaited_once()
        text = context.bot.send_message.await_args.kwargs["text"]
        assert "Alasan: scam (96%)" in text
        assert "spam (" not in text

    async def test_sends_explicit_and_doxxing_alert(self, context):
        result = make_multi_result(
            {"explicit": 0.93, "doxxing": 0.91, "benign": 0.05}
        )
        await self.alert_on(context, result=result)
        context.bot.send_message.assert_awaited_once()
        text = context.bot.send_message.await_args.kwargs["text"]
        assert "Alasan: explicit (93%), doxxing (91%)" in text

    async def test_alert_ignores_unexpected_api_labels(self, context):
        result = make_multi_result(
            {"spam": 0.97, "phishing": 0.99, "benign": 0.01},
            labels=["spam", "phishing"],
        )
        await self.alert_on(context, result=result)
        context.bot.send_message.assert_awaited_once()
        text = context.bot.send_message.await_args.kwargs["text"]
        assert "Alasan: spam (97%)" in text
        assert "phishing" not in text

    async def test_no_alert_for_benign_only(self, context):
        result = make_multi_result(
            {"spam": 0.02, "hostile": 0.01, "trolling": 0.02, "benign": 0.97}
        )
        await self.alert_on(context, result=result)
        context.bot.send_message.assert_not_awaited()

    async def test_no_alert_when_only_hostile_below_threshold(self, context):
        result = make_multi_result(
            {"spam": 0.02, "hostile": 0.5, "trolling": 0.02, "benign": 0.4}
        )
        await self.alert_on(context, result=result)
        context.bot.send_message.assert_not_awaited()

    async def test_classify_called_with_multi_label_request(self, context):
        classify_mock = AsyncMock(return_value=make_spam_result())
        with (
            patch("bot.handlers.ai_spam_monitor.classify_text", new=classify_mock),
            patch("bot.handlers.ai_spam_monitor.get_settings", return_value=make_settings()),
            patch("bot.handlers.ai_spam_monitor.get_group_registry") as mock_registry,
            patch(
                "bot.handlers.ai_spam_monitor.check_user_profile",
                new=AsyncMock(return_value=ProfileCheckResult(True, True)),
            ),
        ):
            mock_registry.return_value.get.return_value = make_group_config(ALERT_CHAT_ID)
            await ai_spam_monitor._classify_and_alert(
                context,
                group_id=GROUP_ID,
                user=make_update().effective_user,
                message_id=100,
                message_text=LONG_TEXT,
            )
        kwargs = classify_mock.await_args.kwargs
        assert kwargs["multi"] is True
        assert kwargs["max_labels"] == 6
        assert kwargs["labels"] == [
            "spam",
            "scam",
            "hostile",
            "trolling",
            "explicit",
            "doxxing",
            "benign",
        ]
        assert "Hostile berarti" in kwargs["instructions"]
        assert "Scam berarti" in kwargs["instructions"]

    async def test_no_alert_without_alert_chat(self, context):
        await self.alert_on(context, alert_chat_id=None)
        context.bot.send_message.assert_not_awaited()

    async def test_no_alert_when_classification_fails(self, context, caplog):
        with caplog.at_level(logging.INFO):
            await self.alert_on(context, result=None)
        context.bot.send_message.assert_not_awaited()
        assert "classification failed for user_id=" in caplog.text
        assert "username=@testuser" in caplog.text
        assert "name='Test User'" in caplog.text
        assert f"text={LONG_TEXT!r}" in caplog.text

    async def test_logs_classification_outcome_with_message_and_user_info(self, context, caplog):
        with caplog.at_level(logging.INFO):
            await self.alert_on(context, result=make_spam_result())
        assert "ai_spam_monitor: group=" in caplog.text
        assert "username=@testuser" in caplog.text
        assert "name='Test User'" in caplog.text
        assert "labels=['spam']" in caplog.text
        assert "flags=spam (97%)" in caplog.text
        assert f"text={LONG_TEXT!r}" in caplog.text

    async def test_log_truncates_long_message_text(self, context, caplog):
        long_text = "x" * 600
        update = make_update(text=long_text)
        with (
            patch("bot.handlers.ai_spam_monitor.classify_text", new=AsyncMock(return_value=None)),
            patch("bot.handlers.ai_spam_monitor.get_settings", return_value=make_settings()),
            patch("bot.handlers.ai_spam_monitor.get_group_registry") as mock_registry,
            caplog.at_level(logging.INFO),
        ):
            mock_registry.return_value.get.return_value = make_group_config()
            await ai_spam_monitor._classify_and_alert(
                context,
                group_id=GROUP_ID,
                user=update.effective_user,
                message_id=100,
                message_text=long_text,
            )
        assert long_text not in caplog.text
        assert f"text={truncate_alert_text(long_text)!r}" in caplog.text

    async def test_log_shows_none_for_user_without_username(self, context, caplog):
        update = make_update()
        update.effective_user.username = None
        with (
            patch("bot.handlers.ai_spam_monitor.classify_text", new=AsyncMock(return_value=None)),
            patch("bot.handlers.ai_spam_monitor.get_settings", return_value=make_settings()),
            patch("bot.handlers.ai_spam_monitor.get_group_registry") as mock_registry,
            caplog.at_level(logging.INFO),
        ):
            mock_registry.return_value.get.return_value = make_group_config()
            await ai_spam_monitor._classify_and_alert(
                context,
                group_id=GROUP_ID,
                user=update.effective_user,
                message_id=100,
                message_text=LONG_TEXT,
            )
        assert "username=none" in caplog.text
        assert "@None" not in caplog.text

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
        assert (GROUP_ID, 100) in context.state.data[ALERTS_KEY]

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
        assert (GROUP_ID, 100) in context.state.data[ALERTS_KEY]

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
        context.state.data[ALERTS_KEY] = alerts
        await self.alert_on(context)
        assert len(context.state.data[ALERTS_KEY]) < ai_spam_monitor.ALERTS_MAX_SIZE
        assert (GROUP_ID, 100) in context.state.data[ALERTS_KEY]
        context.bot.send_message.assert_awaited_once()


def make_callback_update(action: str, admin_id: int = 1) -> MagicMock:
    update = MagicMock()
    query = MagicMock()
    query.data = f"aispam:{action}:{GROUP_ID}:42:100"
    query.from_user = MagicMock()
    query.from_user.id = admin_id
    query.from_user.full_name = "Admin"
    query.from_user.username = "admin"
    query.message = MagicMock()
    query.message.text = "[AI SPAM MONITOR]\nPesan"
    query.message.edit_text = AsyncMock()
    query.answer = AsyncMock()
    update.callback_query = query
    return update


class TestFlaggedAspects:
    """Unit tests for the pure flagged_aspects helper."""

    LABELS = ("spam", "scam", "hostile", "trolling", "explicit", "doxxing", "benign")

    def test_multi_label_flags_all_above_threshold_sorted_desc(self):
        result = make_multi_result(
            {"spam": 0.91, "hostile": 0.98, "trolling": 0.1, "benign": 0.01}
        )
        assert flagged_aspects(result, 0.9, self.LABELS) == [("hostile", 0.98), ("spam", 0.91)]

    def test_multi_label_boundary_score_is_flagged(self):
        result = make_multi_result({"spam": 0.9, "benign": 0.1})
        assert flagged_aspects(result, 0.9, self.LABELS) == [("spam", 0.9)]

    def test_multi_label_never_flags_benign(self):
        result = make_multi_result({"benign": 1.0})
        assert flagged_aspects(result, 0.0, self.LABELS) == []

    def test_multi_label_empty_when_all_below_threshold(self):
        result = make_multi_result({"spam": 0.5, "hostile": 0.6, "benign": 0.4})
        assert flagged_aspects(result, 0.9, self.LABELS) == []

    def test_multi_label_ignores_unexpected_labels(self):
        result = make_multi_result(
            {"spam": 0.97, "phishing": 0.99, "benign": 0.01},
            labels=["spam", "phishing"],
        )
        assert flagged_aspects(result, 0.9, self.LABELS) == [("spam", 0.97)]

    def test_legacy_single_label_spam_path(self):
        result = ClassificationResult(label="spam", confidence=0.95)
        assert flagged_aspects(result, 0.9, self.LABELS) == [("spam", 0.95)]

    def test_legacy_single_label_flags_any_requested_aspect(self):
        result = ClassificationResult(label="hostile", confidence=0.95)
        assert flagged_aspects(result, 0.9, self.LABELS) == [("hostile", 0.95)]

    def test_legacy_single_label_ignores_unrequested_label(self):
        result = ClassificationResult(label="not spam", confidence=1.0)
        assert flagged_aspects(result, 0.9, self.LABELS) == []

    def test_legacy_single_label_null_confidence_is_empty(self):
        result = ClassificationResult(label="spam", confidence=None)
        assert flagged_aspects(result, 0.9, self.LABELS) == []

    def test_legacy_single_label_below_threshold_is_empty(self):
        result = ClassificationResult(label="spam", confidence=0.5)
        assert flagged_aspects(result, 0.9, self.LABELS) == []


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
        update.callback_query.message.edit_text.assert_awaited_once()
        text = update.callback_query.message.edit_text.await_args.args[0]
        assert "hapus pesan" in text
        assert "@admin" in text

    async def test_dismiss_does_not_delete(self):
        context = make_context()
        update = make_callback_update(ACTION_DISMISS)
        await handle_ai_spam_action(update, context)
        context.bot.delete_message.assert_not_awaited()
        context.bot.restrict_chat_member.assert_not_awaited()
        context.bot.ban_chat_member.assert_not_awaited()
        text = update.callback_query.message.edit_text.await_args.args[0]
        assert "abaikan" in text

    async def test_delete_restrict_restricts_member(self):
        context = make_context()
        update = make_callback_update(ACTION_DELETE_RESTRICT)
        with patch("bot.handlers.ai_spam_monitor.restrict_chat_member_with_retry", new=AsyncMock(return_value=True)) as mock_restrict:
            await handle_ai_spam_action(update, context)
        mock_restrict.assert_awaited_once()
        context.bot.ban_chat_member.assert_not_awaited()
        text = update.callback_query.message.edit_text.await_args.args[0]
        assert "hapus + batasi" in text

    async def test_delete_ban_bans_member(self):
        context = make_context()
        update = make_callback_update(ACTION_DELETE_BAN)
        await handle_ai_spam_action(update, context)
        context.bot.ban_chat_member.assert_awaited_once_with(
            chat_id=GROUP_ID, user_id=42
        )
        text = update.callback_query.message.edit_text.await_args.args[0]
        assert "hapus + ban" in text

    async def test_gone_message_notes_it_but_still_bans(self):
        context = make_context()
        context.bot.delete_message = AsyncMock(side_effect=TelegramBadRequest(method=MagicMock(), message="message to delete not found"))
        update = make_callback_update(ACTION_DELETE_BAN)
        await handle_ai_spam_action(update, context)
        context.bot.ban_chat_member.assert_awaited_once()
        text = update.callback_query.message.edit_text.await_args.args[0]
        assert ai_spam_monitor.AI_SPAM_CB_MESSAGE_GONE in text

    async def test_failed_ban_noted_in_alert(self):
        context = make_context()
        context.bot.ban_chat_member = AsyncMock(side_effect=TelegramBadRequest(method=MagicMock(), message="not enough rights"))
        update = make_callback_update(ACTION_DELETE_BAN)
        await handle_ai_spam_action(update, context)
        text = update.callback_query.message.edit_text.await_args.args[0]
        assert "ban gagal" in text

    async def test_admin_of_other_group_rejected(self):
        context = make_context()
        update = MagicMock()
        query = MagicMock()
        query.data = f"aispam:{ACTION_DELETE}:-200:42:100"
        query.from_user = MagicMock()
        query.from_user.id = 1
        query.message = MagicMock()
        query.answer = AsyncMock()
        update.callback_query = query
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
        query = MagicMock()
        query.data = None
        query.message = MagicMock()
        update.callback_query = query
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
        text = update.callback_query.message.edit_text.await_args.args[0]
        assert "pembatasan gagal" in text

    async def test_restrict_exception_noted(self):
        context = make_context()
        update = make_callback_update(ACTION_DELETE_RESTRICT)
        with patch(
            "bot.handlers.ai_spam_monitor.restrict_chat_member_with_retry",
            new=AsyncMock(side_effect=TelegramBadRequest(method=MagicMock(), message="not enough rights")),
        ):
            await handle_ai_spam_action(update, context)
        text = update.callback_query.message.edit_text.await_args.args[0]
        assert "pembatasan gagal" in text

    async def test_edit_failure_logged_not_raised(self):
        context = make_context()
        update = make_callback_update(ACTION_DELETE)
        update.callback_query.message.edit_text = AsyncMock(
            side_effect=TelegramBadRequest(method=MagicMock(), message="cannot edit")
        )
        await handle_ai_spam_action(update, context)
        update.callback_query.answer.assert_awaited_once()


class TestGetHandlers:
    """Tests for get_handlers."""

    def test_returns_message_and_callback_specs(self):
        from bot.dispatch import HandlerSpec

        handlers = ai_spam_monitor.get_handlers()
        assert len(handlers) == 2
        assert all(isinstance(h, HandlerSpec) for h in handlers)
        kinds = [h.update_kinds for h in handlers]
        assert ("message", "edited_message") in kinds
        assert ("callback_query",) in kinds
        groups = {h.label: h.group for h in handlers}
        assert groups["ai_spam_monitor"] == 7
        assert groups["ai_spam_callback"] == 0
