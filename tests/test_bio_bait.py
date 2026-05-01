"""Tests for the bio bait spam detection handler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Message, User
from telegram.ext import ApplicationHandlerStop

from bot.group_config import GroupConfig
from bot.handlers.bio_bait import (
    BIO_BAIT_MAX_LENGTH,
    USER_BIO_CACHE_KEY,
    USER_BIO_CACHE_TTL_SECONDS,
    clear_cached_user_bio,
    get_cached_user_bio,
    handle_bio_bait_spam,
    has_suspicious_bio_links,
    is_bio_bait_spam,
    normalize_bio_bait_text,
)


class TestNormalizeBioBaitText:
    """Tests for the normalize_bio_bait_text function."""

    def test_lowercase(self):
        assert normalize_bio_bait_text("CEK BIO") == "cek bio"

    def test_strip_zero_width(self):
        result = normalize_bio_bait_text("cek b\u200bi\u200bo aku")
        assert "bio" in result
        assert "aku" in result

    def test_canonicalize_b1o(self):
        assert "bio" in normalize_bio_bait_text("cek b1o aku")

    def test_canonicalize_b_dot_i_dot_o(self):
        assert "bio" in normalize_bio_bait_text("cek b.i.o aku")

    def test_canonicalize_spaced(self):
        assert "bio" in normalize_bio_bait_text("cek b i o aku")

    def test_canonicalize_byoh(self):
        assert "bio" in normalize_bio_bait_text("liat byoh")

    def test_canonicalize_bioohh(self):
        assert "bio" in normalize_bio_bait_text("cek bioohh aku")

    def test_canonicalize_cyrillic(self):
        # Cyrillic Ь + і + о, gets lowercased then matched.
        assert "bio" in normalize_bio_bait_text("cek Ьіо aku")

    def test_strip_punctuation(self):
        assert normalize_bio_bait_text("cek bio, aku!") == "cek bio aku"

    def test_collapse_whitespace(self):
        assert normalize_bio_bait_text("cek    bio   aku") == "cek bio aku"

    def test_empty_string(self):
        assert normalize_bio_bait_text("") == ""


class TestIsBioBaitSpam:
    """Tests for the is_bio_bait_spam function."""

    @pytest.mark.parametrize("text", [
        "cek bio",
        "lihat bio aku",
        "liat byoh",
        "buka b1o aku",
        "cek b!o aku",
        "b.i.o aku",
        "b i o aku",
        "bioooo aku",
        "Ьіо aku",
        "open my bio",
        "check my profile",
        "cek\nbio aku",
        "lihat profil aku",
        "cek bioohh aku",
        "cek bio kak",
        "lihat bio dong",
        "bio aku update",
        "bio aku updated",
        "bio aku baru",
    ])
    def test_detects_bait(self, text):
        assert is_bio_bait_spam(text) is True

    @pytest.mark.parametrize("text", [
        "biology itu menarik banget",
        "bioinformatics adalah bidang yang luas",
        "biome dan biodiversity penting",
        "DM aku",
        "pm aku",
        "profile picture saya rusak",
        "halo semua",
        "info ada di sini bro",
        "thank you my bro",
        "bio aku ada di README",
        "bio aku untuk eksperimen regex",
        "",
    ])
    def test_does_not_detect_safe(self, text):
        assert is_bio_bait_spam(text) is False

    def test_too_long_not_detected(self):
        text = "cek bio aku " + ("padding " * 30)
        assert is_bio_bait_spam(text) is False

    def test_length_cap_constant(self):
        assert BIO_BAIT_MAX_LENGTH > 0


class TestHasSuspiciousBioLinks:
    """Tests for has_suspicious_bio_links."""

    def test_empty_bio(self):
        assert has_suspicious_bio_links("") is False

    def test_invite_link(self):
        bio = "VIP BCL t.me/+KVUG7Nzphek0N2M1 ASP"
        assert has_suspicious_bio_links(bio) is True

    def test_invite_link_with_https(self):
        assert has_suspicious_bio_links("https://t.me/+abcdefghij") is True

    def test_non_whitelisted_public_link(self):
        assert has_suspicious_bio_links("Join t.me/somerandomscamchannel") is True

    def test_whitelisted_public_link_alone(self):
        # A bio mentioning the official group is fine.
        assert has_suspicious_bio_links("Member of t.me/pythonid") is False

    def test_single_bare_mention_not_enough(self):
        assert has_suspicious_bio_links("Contact: @somerandomname") is False

    def test_two_non_whitelisted_mentions(self):
        assert has_suspicious_bio_links("@channel_one @channel_two") is True

    def test_single_mention_with_promo_hint(self):
        assert has_suspicious_bio_links("VIP @channel_one") is True

    def test_whitelisted_mention_alone(self):
        assert has_suspicious_bio_links("@pythonid") is False

    def test_plain_bio_no_links(self):
        assert has_suspicious_bio_links("Just a Python developer from Indonesia.") is False


class TestUserBioCache:
    """Tests for get_cached_user_bio / clear_cached_user_bio."""

    @pytest.fixture
    def context(self):
        ctx = MagicMock()
        ctx.bot_data = {}
        ctx.bot = MagicMock()
        ctx.bot.get_chat = AsyncMock()
        return ctx

    async def test_fetch_and_cache(self, context):
        chat = MagicMock()
        chat.bio = "  hello world  "
        context.bot.get_chat.return_value = chat

        bio = await get_cached_user_bio(context, 42)
        assert bio == "hello world"
        assert 42 in context.bot_data[USER_BIO_CACHE_KEY]

    async def test_cache_hit_skips_api(self, context):
        chat = MagicMock()
        chat.bio = "first"
        context.bot.get_chat.return_value = chat

        await get_cached_user_bio(context, 7)
        await get_cached_user_bio(context, 7)
        assert context.bot.get_chat.call_count == 1

    async def test_empty_bio_cached_as_none(self, context):
        chat = MagicMock()
        chat.bio = ""
        context.bot.get_chat.return_value = chat

        bio = await get_cached_user_bio(context, 9)
        assert bio is None
        assert context.bot_data[USER_BIO_CACHE_KEY][9][1] is None

    async def test_missing_bio_attribute_cached_as_none(self, context):
        chat = MagicMock(spec=[])  # no bio attribute
        context.bot.get_chat.return_value = chat

        bio = await get_cached_user_bio(context, 11)
        assert bio is None

    async def test_get_chat_error_returns_none(self, context):
        context.bot.get_chat = AsyncMock(side_effect=Exception("boom"))
        bio = await get_cached_user_bio(context, 13)
        assert bio is None
        # Failures are NOT cached so we retry next time.
        assert 13 not in context.bot_data.get(USER_BIO_CACHE_KEY, {})

    def test_clear_cache(self, context):
        context.bot_data[USER_BIO_CACHE_KEY] = {42: (123.0, "x")}
        clear_cached_user_bio(context, 42)
        assert 42 not in context.bot_data[USER_BIO_CACHE_KEY]

    def test_clear_cache_missing(self, context):
        # Should not raise even if the entry doesn't exist.
        clear_cached_user_bio(context, 999)

    def test_ttl_constant_positive(self):
        assert USER_BIO_CACHE_TTL_SECONDS > 0


class TestHandleBioBaitSpam:
    """Tests for the handle_bio_bait_spam handler."""

    @pytest.fixture
    def group_config(self):
        return GroupConfig(
            group_id=-100,
            warning_topic_id=999,
            bio_bait_enabled=True,
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
        update.message.text = "cek bio aku"
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
        # Default: empty bio so bio-link branch won't trigger unintentionally.
        chat = MagicMock()
        chat.bio = ""
        context.bot.get_chat = AsyncMock(return_value=chat)
        return context

    async def test_skips_no_message(self, mock_context, group_config):
        update = MagicMock()
        update.message = None
        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            await handle_bio_bait_spam(update, mock_context)

    async def test_skips_no_user(self, mock_context, group_config):
        update = MagicMock()
        update.message = MagicMock(spec=Message)
        update.message.from_user = None
        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            await handle_bio_bait_spam(update, mock_context)

    async def test_skips_unmonitored_group(self, mock_update, mock_context):
        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=None):
            await handle_bio_bait_spam(mock_update, mock_context)
        mock_update.message.delete.assert_not_called()

    async def test_skips_when_disabled(self, mock_update, mock_context, group_config):
        group_config.bio_bait_enabled = False
        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            await handle_bio_bait_spam(mock_update, mock_context)
        mock_update.message.delete.assert_not_called()

    async def test_skips_bots(self, mock_update, mock_context, group_config):
        mock_update.message.from_user.is_bot = True
        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            await handle_bio_bait_spam(mock_update, mock_context)
        mock_update.message.delete.assert_not_called()

    async def test_skips_admins(self, mock_update, mock_context, group_config):
        mock_update.message.from_user.id = 1
        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            await handle_bio_bait_spam(mock_update, mock_context)
        mock_update.message.delete.assert_not_called()

    async def test_skips_innocuous_message_with_clean_bio(
        self, mock_update, mock_context, group_config
    ):
        mock_update.message.text = "halo semua, ada yang tahu cara install python?"
        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            await handle_bio_bait_spam(mock_update, mock_context)
        mock_update.message.delete.assert_not_called()

    async def test_detects_message_bait_and_restricts(
        self, mock_update, mock_context, group_config
    ):
        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await handle_bio_bait_spam(mock_update, mock_context)

        mock_update.message.delete.assert_called_once()
        mock_context.bot.restrict_chat_member.assert_called_once()
        mock_context.bot.send_message.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args.kwargs
        assert "Bio Bait" in call_kwargs["text"]
        assert "dibatasi" in call_kwargs["text"]

    async def test_uses_caption_when_no_text(self, mock_update, mock_context, group_config):
        mock_update.message.text = None
        mock_update.message.caption = "lihat bio aku"
        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await handle_bio_bait_spam(mock_update, mock_context)
        mock_update.message.delete.assert_called_once()

    async def test_detects_via_bio_links_with_innocuous_message(
        self, mock_update, mock_context, group_config
    ):
        mock_update.message.text = "halo"
        chat = MagicMock()
        chat.bio = "VIP BCL t.me/+KVUG7Nzphek0N2M1"
        mock_context.bot.get_chat = AsyncMock(return_value=chat)

        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await handle_bio_bait_spam(mock_update, mock_context)

        mock_update.message.delete.assert_called_once()
        mock_context.bot.restrict_chat_member.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args.kwargs
        assert "Bio Profil" in call_kwargs["text"]

    async def test_no_text_no_bad_bio_does_nothing(
        self, mock_update, mock_context, group_config
    ):
        mock_update.message.text = None
        mock_update.message.caption = None
        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            await handle_bio_bait_spam(mock_update, mock_context)
        mock_update.message.delete.assert_not_called()

    async def test_no_text_with_bad_bio_triggers_restriction(
        self, mock_update, mock_context, group_config
    ):
        mock_update.message.text = None
        mock_update.message.caption = None
        chat = MagicMock()
        chat.bio = "VIP t.me/+abcdefghij"
        mock_context.bot.get_chat = AsyncMock(return_value=chat)

        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await handle_bio_bait_spam(mock_update, mock_context)
        mock_update.message.delete.assert_called_once()

    async def test_restriction_clears_bio_cache(
        self, mock_update, mock_context, group_config
    ):
        mock_update.message.text = "halo"
        chat = MagicMock()
        chat.bio = "VIP t.me/+abcdefghij"
        mock_context.bot.get_chat = AsyncMock(return_value=chat)

        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await handle_bio_bait_spam(mock_update, mock_context)

        cache = mock_context.bot_data.get(USER_BIO_CACHE_KEY, {})
        assert mock_update.message.from_user.id not in cache

    async def test_delete_failure_continues(self, mock_update, mock_context, group_config):
        mock_update.message.delete = AsyncMock(side_effect=Exception("Delete failed"))
        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await handle_bio_bait_spam(mock_update, mock_context)
        mock_context.bot.restrict_chat_member.assert_called_once()
        mock_context.bot.send_message.assert_called_once()

    async def test_restrict_failure_uses_no_restrict_template(
        self, mock_update, mock_context, group_config
    ):
        mock_context.bot.restrict_chat_member = AsyncMock(side_effect=Exception("Restrict failed"))
        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await handle_bio_bait_spam(mock_update, mock_context)
        mock_context.bot.send_message.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args.kwargs
        assert "dibatasi" not in call_kwargs["text"]

    async def test_restrict_failure_for_bio_link_uses_no_restrict_template(
        self, mock_update, mock_context, group_config
    ):
        mock_update.message.text = "halo"
        chat = MagicMock()
        chat.bio = "VIP t.me/+abcdefghij"
        mock_context.bot.get_chat = AsyncMock(return_value=chat)
        mock_context.bot.restrict_chat_member = AsyncMock(side_effect=Exception("fail"))

        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await handle_bio_bait_spam(mock_update, mock_context)
        call_kwargs = mock_context.bot.send_message.call_args.kwargs
        assert "Bio Profil" in call_kwargs["text"]
        assert "dibatasi" not in call_kwargs["text"]

    async def test_notification_failure_still_raises_stop(
        self, mock_update, mock_context, group_config
    ):
        mock_context.bot.send_message = AsyncMock(side_effect=Exception("Send failed"))
        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            with pytest.raises(ApplicationHandlerStop):
                await handle_bio_bait_spam(mock_update, mock_context)
