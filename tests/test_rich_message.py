"""Tests for rich message text/URL extraction and rich spam detection."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import (
    Chat,
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LoginUrl,
    Message,
    RichBlockButtons,
    RichBlockList,
    RichBlockListItem,
    RichBlockParagraph,
    RichBlockPullQuotation,
    RichBlockSectionHeading,
    RichBlockTable,
    RichBlockTableCell,
    RichMessage,
    RichMessageButton,
    RichTextBold,
    RichTextButton,
    RichTextCustomEmoji,
    RichTextUrl,
    Update,
    User,
    WebAppInfo,
)

from bot.dispatch import AppState, HandlerContext, StopPropagation
from bot.group_config import GroupConfig
from bot.handlers import ai_spam_monitor
from bot.handlers.ai_spam_monitor import (
    AI_SPAM_CLASSIFY_MAX_LEN,
    _classifiable_text,
)
from bot.handlers.anti_spam import (
    handle_inline_keyboard_spam,
    has_non_whitelisted_link,
    has_rich_message_buttons,
)
from bot.services.rich_message import extract_rich_text, extract_rich_urls, has_rich_buttons

SPAM_URL = "https://t.me/base6d1ef16_bot?startapp=138762"


def _spam_blocks():
    """Rich blocks mirroring the 2026-10-17 adult-spam incident."""
    return [
        RichBlockSectionHeading(text="HOT 2026 DROP", size=1),
        RichBlockParagraph(
            text=[
                RichTextBold(text="FRESH LEAKS"),
                " ",
                RichTextCustomEmoji(
                    custom_emoji_id="5375191900686927814", alternative_text="🍑"
                ),
            ]
        ),
        RichBlockTable(
            cells=[
                [
                    RichBlockTableCell(
                        text=RichTextUrl(text="BIKINI SHOWS", url=SPAM_URL),
                        align="center",
                        valign="middle",
                    ),
                    RichBlockTableCell(
                        text="EXCLUSIVE PICS", align="center", valign="middle"
                    ),
                ]
            ]
        ),
        RichBlockButtons(
            buttons=[
                RichMessageButton(text="OPEN LINK", url=SPAM_URL),
                RichMessageButton(text="ENTER NOW", url=SPAM_URL),
            ]
        ),
    ]


def _make_message(blocks=None, text=None):
    return Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=-100123456, type="supergroup"),
        text=text,
        rich_message=RichMessage(blocks=blocks) if blocks is not None else None,
    )


class TestExtractRichText:
    def test_extracts_heading_paragraph_table_and_buttons(self):
        text = extract_rich_text(RichMessage(blocks=_spam_blocks()))
        for expected in (
            "HOT 2026 DROP",
            "FRESH LEAKS",
            "🍑",
            "BIKINI SHOWS",
            "EXCLUSIVE PICS",
            "OPEN LINK",
            "ENTER NOW",
        ):
            assert expected in text

    def test_none_returns_empty(self):
        assert extract_rich_text(None) == ""

    def test_empty_blocks_returns_empty(self):
        assert extract_rich_text(RichMessage(blocks=[])) == ""

    def test_plain_string_blocks(self):
        text = extract_rich_text(
            RichMessage(blocks=[RichBlockParagraph(text="hello world")])
        )
        assert text == "hello world"

    def test_quotation_credit_included(self):
        blocks = [
            RichBlockPullQuotation(text="a wise quote", credit="— cited source")
        ]
        text = extract_rich_text(RichMessage(blocks=blocks))
        assert "a wise quote" in text
        assert "cited source" in text

    def test_inline_text_button_content_included(self):
        blocks = [
            RichBlockParagraph(
                text=[
                    "tap ",
                    RichTextButton(
                        button=RichMessageButton(text="here", url=SPAM_URL)
                    ),
                ]
            )
        ]
        text = extract_rich_text(RichMessage(blocks=blocks))
        assert "tap" in text
        assert "here" in text

    def test_walk_failure_returns_empty(self):
        class _Boom:
            @property
            def url(self):
                raise RuntimeError("boom")

        assert extract_rich_text(_Boom()) == ""


class TestExtractRichUrls:
    def test_extracts_button_and_text_link_urls_deduped(self):
        urls = extract_rich_urls(RichMessage(blocks=_spam_blocks()))
        assert urls == [SPAM_URL]

    def test_inline_text_button_url_extracted(self):
        blocks = [
            RichBlockParagraph(
                text=RichTextButton(
                    button=RichMessageButton(text="here", url=SPAM_URL)
                )
            )
        ]
        assert extract_rich_urls(RichMessage(blocks=blocks)) == [SPAM_URL]

    def test_bare_url_in_paragraph_detected(self):
        blocks = [RichBlockParagraph(text="visit https://spam.example/deal now")]
        assert extract_rich_urls(RichMessage(blocks=blocks)) == [
            "https://spam.example/deal"
        ]

    def test_url_fragment_without_host_ignored(self):
        blocks = [RichBlockParagraph(text="learn about the https:// protocol")]
        assert extract_rich_urls(RichMessage(blocks=blocks)) == []

    def test_none_returns_empty(self):
        assert extract_rich_urls(None) == []

    def test_no_urls_returns_empty(self):
        assert (
            extract_rich_urls(
                RichMessage(blocks=[RichBlockParagraph(text="no links here")])
            )
            == []
        )

    def test_walk_failure_returns_empty(self):
        class _Boom:
            @property
            def url(self):
                raise RuntimeError("boom")

        assert extract_rich_urls(_Boom()) == []


class TestHasRichButtons:
    def test_block_buttons_detected(self):
        assert has_rich_buttons(RichMessage(blocks=_spam_blocks())) is True

    def test_inline_text_button_detected(self):
        blocks = [
            RichBlockParagraph(
                text=[
                    "click ",
                    RichTextButton(
                        button=RichMessageButton(text="here", url="https://example.com")
                    ),
                ]
            )
        ]
        assert has_rich_buttons(RichMessage(blocks=blocks)) is True

    def test_no_buttons_returns_false(self):
        blocks = [
            RichBlockParagraph(
                text=RichTextUrl(text="just a link", url="https://spam.example/x")
            )
        ]
        assert has_rich_buttons(RichMessage(blocks=blocks)) is False

    def test_button_inside_credit_detected(self):
        blocks = [
            RichBlockPullQuotation(
                text="a wise quote",
                credit=RichTextButton(
                    button=RichMessageButton(text="source", url=SPAM_URL)
                ),
            )
        ]
        assert has_rich_buttons(RichMessage(blocks=blocks)) is True

    def test_none_returns_false(self):
        assert has_rich_buttons(None) is False

    def test_walk_failure_returns_false(self):
        class _Boom:
            @property
            def buttons(self):
                raise RuntimeError("boom")

        assert has_rich_buttons(_Boom()) is False


class TestHasRichMessageButtons:
    def test_spam_rich_message_detected(self):
        assert has_rich_message_buttons(_make_message(_spam_blocks())) is True

    def test_buttons_with_whitelisted_urls_still_detected(self):
        # Buttons are the trigger, not the URL: no stock client can
        # compose them, so even whitelisted targets mean automation.
        blocks = [
            RichBlockButtons(
                buttons=[
                    RichMessageButton(
                        text="Docs", url="https://docs.python.org/3/library/"
                    )
                ]
            )
        ]
        assert has_rich_message_buttons(_make_message(blocks)) is True

    def test_no_rich_message_ignored(self):
        assert has_rich_message_buttons(_make_message()) is False

    def test_rich_without_buttons_ignored(self):
        # URL-only rich content goes to the AI monitor, mirroring how
        # plain text links are handled.
        blocks = [
            RichBlockParagraph(
                text=RichTextUrl(text="shady link", url="https://spam.example/x")
            )
        ]
        assert has_rich_message_buttons(_make_message(blocks)) is False


class TestHasNonWhitelistedLinkRich:
    """Probation link check also sees URLs hidden in rich blocks."""

    def test_rich_text_link_detected(self):
        blocks = [
            RichBlockParagraph(
                text=RichTextUrl(text="shady link", url="https://spam.example/x")
            )
        ]
        assert has_non_whitelisted_link(_make_message(blocks)) is True

    def test_rich_button_url_detected(self):
        blocks = [
            RichBlockButtons(
                buttons=[RichMessageButton(text="OPEN", url=SPAM_URL)]
            )
        ]
        assert has_non_whitelisted_link(_make_message(blocks)) is True

    def test_rich_whitelisted_url_ignored(self):
        blocks = [
            RichBlockParagraph(
                text=RichTextUrl(
                    text="docs", url="https://docs.python.org/3/library/"
                )
            )
        ]
        assert has_non_whitelisted_link(_make_message(blocks)) is False

    def test_rich_without_urls_ignored(self):
        blocks = [RichBlockParagraph(text="just text, no links")]
        assert has_non_whitelisted_link(_make_message(blocks)) is False


class TestClassifiableTextRich:
    def test_rich_content_included(self):
        text = _classifiable_text(_make_message(_spam_blocks()))
        assert "HOT 2026 DROP" in text
        assert "BIKINI SHOWS" in text
        assert SPAM_URL in text

    def test_plain_text_unchanged(self):
        assert _classifiable_text(_make_message(text="hello")) == "hello"

    def test_caption_unchanged(self):
        msg = Message(
            message_id=1,
            date=datetime.now(UTC),
            chat=Chat(id=1, type="private"),
            caption="a caption",
        )
        assert _classifiable_text(msg) == "a caption"

    def test_empty_message_stays_empty(self):
        assert _classifiable_text(_make_message()) == ""

    def test_text_and_rich_combined(self):
        text = _classifiable_text(_make_message(_spam_blocks(), text="intro"))
        assert text.startswith("intro")
        assert "HOT 2026 DROP" in text


class TestHandleInlineKeyboardSpamRich:
    """Rich-message spam takes the auto-delete path at group=1."""

    @pytest.fixture
    def mock_update(self):
        update = MagicMock()
        update.message = MagicMock(spec=Message)
        update.message.from_user = MagicMock(spec=User)
        update.message.from_user.id = 12345
        update.message.from_user.is_bot = False
        update.message.from_user.full_name = "Spam User"
        update.message.from_user.username = "spamuser"
        update.message.delete = AsyncMock()
        update.message.reply_markup = None
        update.message.forward_origin = None
        update.edited_message = None
        return update

    @pytest.fixture
    def mock_context(self):
        bot = MagicMock()
        bot.send_message = AsyncMock()
        bot.restrict_chat_member = AsyncMock()
        state = AppState()
        state.group_admin_ids = {}
        state.trusted_user_ids = set()
        return HandlerContext(bot=bot, state=state, args=[])

    @pytest.fixture
    def group_config(self):
        return GroupConfig(
            group_id=-100123456,
            warning_topic_id=123,
            rules_link="https://example.com/rules",
        )

    async def test_rich_spam_deleted_restricted_notified(
        self, mock_update, mock_context, group_config
    ):
        mock_update.message.rich_message = RichMessage(blocks=_spam_blocks())

        with patch(
            "bot.handlers.anti_spam.get_group_config_for_update",
            return_value=group_config,
        ):
            with pytest.raises(StopPropagation):
                await handle_inline_keyboard_spam(mock_update, mock_context)

        mock_update.message.delete.assert_called_once()
        mock_context.bot.restrict_chat_member.assert_called_once()
        mock_context.bot.send_message.assert_called_once()
        sent_text = mock_context.bot.send_message.call_args.kwargs["text"]
        assert "tombol pada pesan rich text" in sent_text

    async def test_buttons_with_whitelisted_urls_still_deleted(
        self, mock_update, mock_context, group_config
    ):
        # Buttons are the trigger: no stock client can compose them, so the
        # URL whitelist does not apply to rich message buttons.
        mock_update.message.rich_message = RichMessage(
            blocks=[
                RichBlockButtons(
                    buttons=[
                        RichMessageButton(
                            text="Docs", url="https://docs.python.org/3/library/"
                        )
                    ]
                )
            ]
        )

        with patch(
            "bot.handlers.anti_spam.get_group_config_for_update",
            return_value=group_config,
        ):
            with pytest.raises(StopPropagation):
                await handle_inline_keyboard_spam(mock_update, mock_context)

        mock_update.message.delete.assert_called_once()
        mock_context.bot.restrict_chat_member.assert_called_once()

    async def test_rich_without_buttons_ignored(
        self, mock_update, mock_context, group_config
    ):
        # URL-only rich content is left to the AI monitor, like plain text.
        mock_update.message.rich_message = RichMessage(
            blocks=[
                RichBlockParagraph(
                    text=RichTextUrl(text="shady link", url="https://spam.example/x")
                )
            ]
        )

        with patch(
            "bot.handlers.anti_spam.get_group_config_for_update",
            return_value=group_config,
        ):
            await handle_inline_keyboard_spam(mock_update, mock_context)

        mock_update.message.delete.assert_not_called()
        mock_context.bot.restrict_chat_member.assert_not_called()

    async def test_no_rich_message_ignored(self, mock_update, mock_context, group_config):
        mock_update.message.rich_message = None

        with patch(
            "bot.handlers.anti_spam.get_group_config_for_update",
            return_value=group_config,
        ):
            await handle_inline_keyboard_spam(mock_update, mock_context)

        mock_update.message.delete.assert_not_called()

    async def test_automatic_forward_skipped(
        self, mock_update, mock_context, group_config
    ):
        # Linked-channel auto-forwards are admin-configured: never punish
        # the channel for rich buttons in its posts.
        mock_update.message.rich_message = RichMessage(blocks=_spam_blocks())
        mock_update.message.is_automatic_forward = True

        with patch(
            "bot.handlers.anti_spam.get_group_config_for_update",
            return_value=group_config,
        ):
            await handle_inline_keyboard_spam(mock_update, mock_context)

        mock_update.message.delete.assert_not_called()
        mock_context.bot.restrict_chat_member.assert_not_called()


def _make_update(blocks=None, text=None):
    return Update(
        update_id=1,
        message=Message(
            message_id=1,
            date=datetime.now(UTC),
            chat=Chat(id=-100, type="supergroup"),
            from_user=User(id=7, is_bot=False, first_name="U"),
            text=text,
            rich_message=RichMessage(blocks=blocks) if blocks is not None else None,
        ),
    )


class TestRichWalkerGaps:
    """Walker coverage for list labels, payload sub-objects, depth."""

    def test_list_item_label_extracted(self):
        blocks = [
            RichBlockList(
                items=[
                    RichBlockListItem(
                        label="PROMO SPESIAL HARI INI",
                        blocks=[RichBlockParagraph(text="detail")],
                    )
                ]
            )
        ]
        text = extract_rich_text(RichMessage(blocks=blocks))
        assert "PROMO SPESIAL HARI INI" in text

    def test_copy_text_payload_extracted(self):
        blocks = [
            RichBlockButtons(
                buttons=[
                    RichMessageButton(
                        text="copy",
                        copy_text=CopyTextButton(text="https://spam.example/steal"),
                    )
                ]
            )
        ]
        assert extract_rich_urls(RichMessage(blocks=blocks)) == [
            "https://spam.example/steal"
        ]
        assert has_rich_buttons(RichMessage(blocks=blocks)) is True

    def test_login_url_and_web_app_extracted(self):
        blocks = [
            RichBlockButtons(
                buttons=[
                    RichMessageButton(
                        text="login",
                        login_url=LoginUrl(
                            url="https://spam.example/login",
                            forward_text="open login",
                        ),
                    ),
                    RichMessageButton(
                        text="app",
                        web_app=WebAppInfo(url="https://spam.example/app"),
                    ),
                ]
            )
        ]
        urls = extract_rich_urls(RichMessage(blocks=blocks))
        assert urls == ["https://spam.example/login", "https://spam.example/app"]
        assert "open login" in extract_rich_text(RichMessage(blocks=blocks))

    def test_credit_nested_button_url_extracted(self):
        blocks = [
            RichBlockPullQuotation(
                text="a wise quote",
                credit=RichTextButton(
                    button=RichMessageButton(text="source", url=SPAM_URL)
                ),
            )
        ]
        assert extract_rich_urls(RichMessage(blocks=blocks)) == [SPAM_URL]

    def test_deep_nesting_buttons_fail_closed(self):
        node = ["deep"]
        for _ in range(3000):
            node = [node]
        assert has_rich_buttons(node) is True

    def test_deep_nesting_extract_terminates(self):
        node = ["deep"]
        for _ in range(3000):
            node = [node]
        assert extract_rich_text(node) == ""
        assert extract_rich_urls(node) == []


class TestAiSpamFilterRich:
    def test_rich_only_message_matches(self):
        update = _make_update(
            [RichBlockParagraph(text="this is a rich-only message with buttons")]
        )
        assert ai_spam_monitor.AI_SPAM_FILTER(update) is True

    def test_rich_empty_no_match(self):
        update = _make_update([])
        assert ai_spam_monitor.AI_SPAM_FILTER(update) is False

    def test_no_rich_no_match(self):
        assert ai_spam_monitor.AI_SPAM_FILTER(_make_update()) is False


class TestClassifyTruncation:
    async def test_long_input_truncated_before_classify(self):
        captured = {}

        async def fake_classify(text, **kwargs):
            captured["text"] = text
            return None

        settings = MagicMock()
        settings.classifier_cooldown_seconds = 600
        settings.classifier_timeout_seconds = 10
        settings.ai_spam_daily_budget = 15000
        context = HandlerContext(bot=MagicMock(), state=AppState(), args=[])
        user = User(id=1, is_bot=False, first_name="T")
        with (
            patch("bot.handlers.ai_spam_monitor.classify_text", new=fake_classify),
            patch(
                "bot.handlers.ai_spam_monitor.get_settings", return_value=settings
            ),
            patch(
                "bot.handlers.ai_spam_monitor.breaker_is_open", return_value=False
            ),
            patch(
                "bot.handlers.ai_spam_monitor.try_spend_budget", return_value=True
            ),
        ):
            await ai_spam_monitor._classify_and_alert(
                context,
                group_id=-100,
                user=user,
                message_id=1,
                message_text="x" * 20000,
            )
        assert len(captured["text"]) == AI_SPAM_CLASSIFY_MAX_LEN


class TestInlineKeyboardAutoForward:
    """The is_automatic_forward guard covers the pre-existing keyboard path too."""

    @pytest.fixture
    def mock_update(self):
        update = MagicMock()
        update.message = MagicMock(spec=Message)
        update.message.from_user = MagicMock(spec=User)
        update.message.from_user.id = 12345
        update.message.from_user.is_bot = False
        update.message.from_user.full_name = "Spam User"
        update.message.from_user.username = "spamuser"
        update.message.delete = AsyncMock()
        update.message.reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="x", url="https://evil.example/")]
            ]
        )
        update.message.rich_message = None
        update.message.is_automatic_forward = True
        update.message.forward_origin = None
        update.edited_message = None
        return update

    @pytest.fixture
    def mock_context(self):
        bot = MagicMock()
        bot.send_message = AsyncMock()
        bot.restrict_chat_member = AsyncMock()
        state = AppState()
        state.group_admin_ids = {}
        state.trusted_user_ids = set()
        return HandlerContext(bot=bot, state=state, args=[])

    @pytest.fixture
    def group_config(self):
        return GroupConfig(
            group_id=-100123456,
            warning_topic_id=123,
            rules_link="https://example.com/rules",
        )

    async def test_keyboard_auto_forward_skipped(
        self, mock_update, mock_context, group_config
    ):
        with patch(
            "bot.handlers.anti_spam.get_group_config_for_update",
            return_value=group_config,
        ):
            await handle_inline_keyboard_spam(mock_update, mock_context)

        mock_update.message.delete.assert_not_called()
        mock_context.bot.restrict_chat_member.assert_not_called()


class TestRichNoRestrictAndExemptions:
    @pytest.fixture
    def mock_update(self):
        update = MagicMock()
        update.message = MagicMock(spec=Message)
        update.message.from_user = MagicMock(spec=User)
        update.message.from_user.id = 12345
        update.message.from_user.is_bot = False
        update.message.from_user.full_name = "Spam User"
        update.message.from_user.username = "spamuser"
        update.message.delete = AsyncMock()
        update.message.reply_markup = None
        update.message.rich_message = RichMessage(blocks=_spam_blocks())
        update.message.is_automatic_forward = False
        update.message.forward_origin = None
        update.edited_message = None
        return update

    @pytest.fixture
    def mock_context(self):
        bot = MagicMock()
        bot.send_message = AsyncMock()
        bot.restrict_chat_member = AsyncMock()
        state = AppState()
        state.group_admin_ids = {}
        state.trusted_user_ids = set()
        return HandlerContext(bot=bot, state=state, args=[])

    @pytest.fixture
    def group_config(self):
        return GroupConfig(
            group_id=-100123456,
            warning_topic_id=123,
            rules_link="https://example.com/rules",
        )

    async def test_no_restrict_template_on_failure(
        self, mock_update, mock_context, group_config
    ):
        mock_context.bot.restrict_chat_member = AsyncMock(
            side_effect=Exception("Restrict failed")
        )
        with patch(
            "bot.handlers.anti_spam.get_group_config_for_update",
            return_value=group_config,
        ):
            with pytest.raises(StopPropagation):
                await handle_inline_keyboard_spam(mock_update, mock_context)

        text = mock_context.bot.send_message.call_args.kwargs["text"]
        assert "dibatasi" not in text
        assert "tombol pada pesan rich text" in text

    async def test_admin_exempt_from_rich_delete(
        self, mock_update, mock_context, group_config
    ):
        mock_context.state.group_admin_ids = {
            group_config.group_id: [mock_update.message.from_user.id]
        }
        with patch(
            "bot.handlers.anti_spam.get_group_config_for_update",
            return_value=group_config,
        ):
            await handle_inline_keyboard_spam(mock_update, mock_context)

        mock_update.message.delete.assert_not_called()

    async def _notification_text(
        self, mock_update, mock_context, group_config, forwarded: bool
    ) -> str:
        mock_update.message.forward_origin = MagicMock() if forwarded else None
        with patch(
            "bot.handlers.anti_spam.get_group_config_for_update",
            return_value=group_config,
        ):
            with pytest.raises(StopPropagation):
                await handle_inline_keyboard_spam(mock_update, mock_context)
        return mock_context.bot.send_message.call_args.kwargs["text"]

    async def test_forwarded_wording_and_appeal_line(
        self, mock_update, mock_context, group_config
    ):
        text = await self._notification_text(
            mock_update, mock_context, group_config, forwarded=True
        )
        assert "Pesan terusan dari" in text
        assert "Hubungi admin grup" in text

    async def test_non_forwarded_wording_and_appeal_line(
        self, mock_update, mock_context, group_config
    ):
        text = await self._notification_text(
            mock_update, mock_context, group_config, forwarded=False
        )
        assert "Pesan dari" in text
        assert "Pesan terusan" not in text
        assert "Hubungi admin grup" in text
