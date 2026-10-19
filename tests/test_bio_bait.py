"""Tests for the bio bait spam detection handler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import (
    Message,
    RichBlockParagraph,
    RichMessage,
    User,
)

from bot.dispatch import AppState, HandlerContext, StopPropagation

from bot.group_config import GroupConfig
from bot.handlers.bio_bait import (
    BIO_BAIT_MAX_LENGTH,
    USER_BIO_CACHE_KEY,
    USER_BIO_CACHE_MAX_SIZE,
    USER_BIO_CACHE_TTL_SECONDS,
    clear_cached_user_bio,
    get_cached_user_bio,
    handle_bio_bait_spam,
    has_suspicious_bio_links,
    is_bio_bait_spam,
    normalize_bio_bait_text,
    send_monitor_alert_to_owner,
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

    def test_canonicalize_cyrillic_ь_filler(self):
        # Latin b + Cyrillic ь + Cyrillic і + Cyrillic о
        assert "bio" in normalize_bio_bait_text("bьіо aku")

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
        "bьіо aku",
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
        # Pattern 1 ownership: must end with bio + optional cue
        "open source bio library",
        "view bio data structure",
        "cek bio di website",
        "lihat bio orang lain",
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
        bio = "VIP promo t.me/+exampleinvitehash ASP"
        assert has_suspicious_bio_links(bio) is True

    def test_invite_link_with_https(self):
        assert has_suspicious_bio_links("https://t.me/+exampleinvitehash") is True

    def test_non_whitelisted_public_link(self):
        assert has_suspicious_bio_links("Join t.me/somerandomscamchannel") is True

    def test_whitelisted_public_link_alone(self):
        # A bio mentioning the official group is fine.
        assert has_suspicious_bio_links("Member of t.me/pythonid") is False

    def test_single_bare_mention_not_enough(self):
        assert has_suspicious_bio_links("Contact: @somerandomname") is False

    def test_two_non_whitelisted_mentions(self):
        assert has_suspicious_bio_links("@channel_one @channel_two") is True

    def test_duplicate_mention_counts(self):
        """Same @mention repeated counts as 2, not 1."""
        assert has_suspicious_bio_links("@scamch @scamch") is True

    def test_single_mention_with_promo_hint(self):
        assert has_suspicious_bio_links("VIP @channel_one") is True

    def test_whitelisted_mention_alone(self):
        assert has_suspicious_bio_links("@pythonid") is False

    def test_plain_bio_no_links(self):
        assert has_suspicious_bio_links("Just a Python developer from Indonesia.") is False

    def test_promo_hint_word_boundary(self):
        """'vip' should not match inside other words like 'advancement'."""
        assert has_suspicious_bio_links("advancement @some_user") is False

    def test_generic_words_no_longer_trigger(self):
        """'open', 'ready', 'available' removed from promo hints."""
        assert has_suspicious_bio_links("Open source @my_github") is False
        assert has_suspicious_bio_links("Ready @my_youtube") is False
        assert has_suspicious_bio_links("Available @my_handle") is False

    def test_strong_promo_hints_still_work(self):
        """'vip', 'promo', 'join' etc. still trigger with mention."""
        assert has_suspicious_bio_links("VIP @scam_channel") is True
        assert has_suspicious_bio_links("promo @scam_channel") is True
        assert has_suspicious_bio_links("join @scam_channel") is True

    # --- Dynamic self-whitelist: links/@mentions pointing at the bio
    # owner's own username are self-references, not promo links. ---

    def test_own_tme_link_not_suspicious(self):
        assert has_suspicious_bio_links("t.me/myusername", username="myusername") is False

    def test_own_tme_link_with_scheme_not_suspicious(self):
        assert has_suspicious_bio_links("https://t.me/myusername", username="myusername") is False

    def test_own_telegram_me_link_not_suspicious(self):
        assert has_suspicious_bio_links("telegram.me/myusername", username="myusername") is False

    def test_own_bare_mention_not_suspicious(self):
        assert has_suspicious_bio_links("@myusername", username="myusername") is False

    def test_own_username_case_insensitive(self):
        assert has_suspicious_bio_links("t.me/MyUserName", username="myusername") is False
        assert has_suspicious_bio_links("@MYUSERNAME", username="myusername") is False

    def test_own_link_plus_other_channel_still_suspicious(self):
        bio = "t.me/myusername and t.me/somechannel"
        assert has_suspicious_bio_links(bio, username="myusername") is True

    def test_own_mention_excluded_from_count(self):
        # Only one foreign mention left -> not enough without a promo hint.
        assert has_suspicious_bio_links("@myusername @somechannel", username="myusername") is False
        # Two foreign mentions -> still suspicious.
        assert has_suspicious_bio_links("@myusername @chan_one @chan_two", username="myusername") is True

    def test_own_mention_with_promo_hint_not_suspicious(self):
        assert has_suspicious_bio_links("VIP @myusername", username="myusername") is False

    def test_invite_link_still_suspicious_with_username(self):
        # Private invite links can never be a self-reference.
        assert has_suspicious_bio_links("t.me/+exampleinvitehash", username="myusername") is True

    def test_none_username_keeps_old_behavior(self):
        assert has_suspicious_bio_links("Join t.me/somerandomscamchannel", username=None) is True
        assert has_suspicious_bio_links("@somerandomname", username=None) is False

class TestUserBioCache:
    """Tests for get_cached_user_bio / clear_cached_user_bio."""

    @pytest.fixture
    def context(self):
        bot = MagicMock()
        bot.get_chat = AsyncMock()
        state = AppState()
        return HandlerContext(bot=bot, state=state, args=[])

    async def test_fetch_and_cache(self, context):
        chat = MagicMock()
        chat.bio = "  hello world  "
        context.bot.get_chat.return_value = chat

        bio = await get_cached_user_bio(context, 42)
        assert bio == "hello world"
        assert 42 in context.state.data[USER_BIO_CACHE_KEY]

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
        assert context.state.data[USER_BIO_CACHE_KEY][9][1] is None

    async def test_missing_bio_attribute_cached_as_none(self, context):
        chat = MagicMock(spec=[])  # no bio attribute
        context.bot.get_chat.return_value = chat

        bio = await get_cached_user_bio(context, 11)
        assert bio is None

    async def test_get_chat_error_returns_none(self, context):
        context.bot.get_chat = AsyncMock(side_effect=Exception("boom"))
        bio = await get_cached_user_bio(context, 13)
        assert bio is None
        # Failures ARE cached (with shorter TTL) to prevent repeated API calls.
        assert 13 in context.state.data.get(USER_BIO_CACHE_KEY, {})
        # Verify it's a failure sentinel
        cached = context.state.data[USER_BIO_CACHE_KEY][13]
        assert cached[1] == "__FAILURE__"

    def test_clear_cache(self, context):
        context.state.data[USER_BIO_CACHE_KEY] = {42: (123.0, "x")}
        clear_cached_user_bio(context, 42)
        assert 42 not in context.state.data[USER_BIO_CACHE_KEY]

    def test_clear_cache_missing(self, context):
        # Should not raise even if the entry doesn't exist.
        clear_cached_user_bio(context, 999)

    async def test_cache_eviction(self, context):
        """Cache eviction removes oldest entries when at max size."""
        from time import monotonic

        cache = context.state.data.setdefault(USER_BIO_CACHE_KEY, {})
        now = monotonic()
        # Fill cache to max
        for i in range(USER_BIO_CACHE_MAX_SIZE):
            cache[i] = (now + 3600, f"bio_{i}")

        # Next fetch should trigger eviction
        chat = MagicMock()
        chat.bio = "new bio"
        context.bot.get_chat = AsyncMock(return_value=chat)

        bio = await get_cached_user_bio(context, 99999)
        assert bio == "new bio"
        # Cache should be roughly half size after eviction
        assert len(cache) <= USER_BIO_CACHE_MAX_SIZE // 2 + 2

    def test_max_size_constant(self):
        assert USER_BIO_CACHE_MAX_SIZE > 0

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
        return update

    @pytest.fixture
    def mock_context(self):
        bot = MagicMock()
        bot.restrict_chat_member = AsyncMock()
        bot.send_message = AsyncMock()
        # Default: empty bio so bio-link branch won't trigger unintentionally.
        chat = MagicMock()
        chat.bio = ""
        bot.get_chat = AsyncMock(return_value=chat)
        state = AppState()
        state.group_admin_ids = {-100: [1, 2]}
        state.trusted_user_ids = set()
        return HandlerContext(bot=bot, state=state, args=[])

    async def test_skips_no_message(self, mock_context, group_config):
        update = MagicMock()
        update.message = None
        update.edited_message = None
        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            await handle_bio_bait_spam(update, mock_context)

    async def test_skips_no_user(self, mock_context, group_config):
        update = MagicMock()
        update.message = MagicMock(spec=Message)
        update.edited_message = None
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
            with pytest.raises(StopPropagation):
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
            with pytest.raises(StopPropagation):
                await handle_bio_bait_spam(mock_update, mock_context)
        mock_update.message.delete.assert_called_once()

    async def test_detects_bait_in_rich_text(self, mock_update, mock_context, group_config):
        mock_update.message.text = None
        mock_update.message.caption = None
        mock_update.message.rich_message = RichMessage(
            blocks=[RichBlockParagraph(text="cek bio aku dong")]
        )
        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            with pytest.raises(StopPropagation):
                await handle_bio_bait_spam(mock_update, mock_context)
        mock_update.message.delete.assert_called_once()

    async def test_detects_via_bio_links_with_innocuous_message(
        self, mock_update, mock_context, group_config
    ):
        mock_update.message.text = "halo"
        chat = MagicMock()
        chat.bio = "VIP promo t.me/+exampleinvitehash"
        mock_context.bot.get_chat = AsyncMock(return_value=chat)

        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            with pytest.raises(StopPropagation):
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
        chat.bio = "VIP t.me/+exampleinvitehash"
        mock_context.bot.get_chat = AsyncMock(return_value=chat)

        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            with pytest.raises(StopPropagation):
                await handle_bio_bait_spam(mock_update, mock_context)
        mock_update.message.delete.assert_called_once()

    async def test_restriction_clears_bio_cache(
        self, mock_update, mock_context, group_config
    ):
        mock_update.message.text = "halo"
        chat = MagicMock()
        chat.bio = "VIP t.me/+exampleinvitehash"
        mock_context.bot.get_chat = AsyncMock(return_value=chat)

        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            with pytest.raises(StopPropagation):
                await handle_bio_bait_spam(mock_update, mock_context)

        cache = mock_context.state.data.get(USER_BIO_CACHE_KEY, {})
        assert mock_update.message.from_user.id not in cache

    async def test_delete_failure_continues(self, mock_update, mock_context, group_config):
        mock_update.message.delete = AsyncMock(side_effect=Exception("Delete failed"))
        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            with pytest.raises(StopPropagation):
                await handle_bio_bait_spam(mock_update, mock_context)
        mock_context.bot.restrict_chat_member.assert_called_once()
        mock_context.bot.send_message.assert_called_once()

    async def test_restrict_failure_uses_no_restrict_template(
        self, mock_update, mock_context, group_config
    ):
        mock_context.bot.restrict_chat_member = AsyncMock(side_effect=Exception("Restrict failed"))
        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            with pytest.raises(StopPropagation):
                await handle_bio_bait_spam(mock_update, mock_context)
        mock_context.bot.send_message.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args.kwargs
        assert "dibatasi" not in call_kwargs["text"]

    async def test_restrict_failure_for_bio_link_uses_no_restrict_template(
        self, mock_update, mock_context, group_config
    ):
        mock_update.message.text = "halo"
        chat = MagicMock()
        chat.bio = "VIP t.me/+exampleinvitehash"
        mock_context.bot.get_chat = AsyncMock(return_value=chat)
        mock_context.bot.restrict_chat_member = AsyncMock(side_effect=Exception("fail"))

        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            with pytest.raises(StopPropagation):
                await handle_bio_bait_spam(mock_update, mock_context)
        call_kwargs = mock_context.bot.send_message.call_args.kwargs
        assert "Bio Profil" in call_kwargs["text"]
        assert "dibatasi" not in call_kwargs["text"]

    async def test_notification_failure_still_raises_stop(
        self, mock_update, mock_context, group_config
    ):
        mock_context.bot.send_message = AsyncMock(side_effect=Exception("Send failed"))
        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            with pytest.raises(StopPropagation):
                await handle_bio_bait_spam(mock_update, mock_context)

    async def test_monitor_only_sends_owner_alert(
        self, mock_update, mock_context, group_config
    ):
        group_config.bio_bait_monitor_only = True
        group_config.bio_bait_alert_chat_id = 57747812
        mock_update.message.text = "cek bio aku"

        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            await handle_bio_bait_spam(mock_update, mock_context)

        mock_update.message.delete.assert_not_called()
        mock_context.bot.restrict_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_called_once()

        kwargs = mock_context.bot.send_message.call_args.kwargs
        assert kwargs["chat_id"] == 57747812
        assert "message_thread_id" not in kwargs
        assert "cek bio aku" in kwargs["text"]

class TestBioBaitReviewFixes:
    """Tests for pending bio-bait review fixes (trusted bypass, monitor semantics,
    warning-topic guard, metrics)."""

    @pytest.fixture
    def group_config(self):
        return GroupConfig(
            group_id=-1001234567890,
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
        return update

    @pytest.fixture
    def mock_context(self):
        bot = MagicMock()
        bot.restrict_chat_member = AsyncMock()
        bot.send_message = AsyncMock()
        chat = MagicMock()
        chat.bio = ""
        bot.get_chat = AsyncMock(return_value=chat)
        state = AppState()
        state.group_admin_ids = {-1001234567890: [1, 2]}
        state.trusted_user_ids = set()
        return HandlerContext(bot=bot, state=state, args=[])

    # ── (a) trusted user bypass ──

    async def test_trusted_user_bypasses_bio_bait(
        self, mock_update, mock_context, group_config
    ):
        """Trusted user (not admin) should bypass bio bait detection."""
        mock_context.state.trusted_user_ids = {42}
        mock_context.state.group_admin_ids = {-1001234567890: [1, 2]}
        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            await handle_bio_bait_spam(mock_update, mock_context)
        mock_update.message.delete.assert_not_called()
        mock_context.bot.restrict_chat_member.assert_not_called()
        mock_context.bot.send_message.assert_not_called()

    # ── (b) enforcement mode + alert_chat_id does NOT send owner alert ──

    async def test_enforcement_mode_alert_chat_id_does_not_send_owner_alert(
        self, mock_update, mock_context, group_config
    ):
        """In enforcement mode, owner alert should NOT be sent even if alert_chat_id is set."""
        group_config.bio_bait_monitor_only = False
        group_config.bio_bait_alert_chat_id = 57747812
        mock_update.message.text = "cek bio aku"

        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            with pytest.raises(StopPropagation):
                await handle_bio_bait_spam(mock_update, mock_context)

        # Only the warning-topic notification should be sent, not the owner alert
        assert mock_context.bot.send_message.call_count == 1
        kwargs = mock_context.bot.send_message.call_args.kwargs
        assert kwargs.get("message_thread_id") == 999  # warning topic

    # ── (c) monitor-only + alert target = same group => alert skipped ──

    # ── (d) enforcement mode (no metrics tracking) ──

    async def test_monitor_only_alert_target_same_group_skipped(
        self, mock_update, mock_context, group_config
    ):
        """When monitor-only and alert_chat_id equals the monitored group,
        owner alert should be skipped."""
        group_config.bio_bait_monitor_only = True
        group_config.bio_bait_alert_chat_id = -1001234567890  # same as group_id
        mock_update.message.text = "cek bio aku"

        with patch("bot.handlers.bio_bait.get_group_config_for_update", return_value=group_config):
            await handle_bio_bait_spam(mock_update, mock_context)

        # No send_message calls at all
        mock_context.bot.send_message.assert_not_called()
        mock_update.message.delete.assert_not_called()
        mock_context.bot.restrict_chat_member.assert_not_called()


class TestBioBaitRegistrationFilter:
    """Tests for bio-bait handler filter registration.

    The handler filter MUST accept non-text messages (e.g., photo without
    caption) so bio-link detection works for users who post media with
    no text. If the filter includes TEXT|CAPTION, non-text messages never
    reach the handler — this test catches that regression.
    """

    def test_filter_accepts_non_text_group_message(self):
        """Non-text group message must pass bio-bait filter."""
        from datetime import datetime

        from aiogram.types import Chat, Message, Update, User

        from bot.handlers.bio_bait import BIO_BAIT_FILTER

        user = User(id=42, is_bot=False, first_name="Test")
        chat = Chat(id=-100, type="group", title="Test")
        msg = Message(
            message_id=1,
            date=datetime.now(),
            chat=chat,
            from_user=user,
        )
        update = Update(update_id=1, message=msg)

        assert BIO_BAIT_FILTER(update) is True, (
            "Bio-bait filter MUST accept non-text messages for bio-link detection"
        )

    def test_filter_accepts_text_group_message(self):
        """Text group message must still pass bio-bait filter."""
        from datetime import datetime

        from aiogram.types import Chat, Message, Update, User

        from bot.handlers.bio_bait import BIO_BAIT_FILTER

        user = User(id=42, is_bot=False, first_name="Test")
        chat = Chat(id=-100, type="group", title="Test")
        msg = Message(
            message_id=2,
            date=datetime.now(),
            chat=chat,
            from_user=user,
            text="cek bio aku",
        )
        update = Update(update_id=2, message=msg)

        assert BIO_BAIT_FILTER(update) is True

    def test_filter_excludes_group_commands(self):
        """Command messages must be excluded by bio-bait filter."""
        from datetime import datetime

        from aiogram.types import Chat, Message, MessageEntity, Update, User

        from bot.handlers.bio_bait import BIO_BAIT_FILTER

        user = User(id=42, is_bot=False, first_name="Test")
        chat = Chat(id=-100, type="group", title="Test")
        msg = Message(
            message_id=3,
            date=datetime.now(),
            chat=chat,
            from_user=user,
            text="/start",
            entities=[MessageEntity(type="bot_command", offset=0, length=6)],
        )
        update = Update(update_id=3, message=msg)

        assert BIO_BAIT_FILTER(update) is False, (
            "Bio-bait filter MUST exclude commands"
        )


class TestGetCachedUserBio:
    """Tests for the get_cached_user_bio function with negative caching."""

    async def test_caches_failures(self):
        """Test that bio fetch failures are cached to prevent repeated API calls."""
        bot = AsyncMock()
        mock_context = HandlerContext(bot=bot, state=AppState(), args=[])

        # First call fails
        mock_context.bot.get_chat.side_effect = Exception("API error")
        result1 = await get_cached_user_bio(mock_context, user_id=123)
        assert result1 is None

        # Second call should use cached failure, not call API again
        mock_context.bot.get_chat.reset_mock()
        result2 = await get_cached_user_bio(mock_context, user_id=123)
        assert result2 is None
        mock_context.bot.get_chat.assert_not_called()

    async def test_failure_cache_expires(self):
        """Test that cached failures expire and retry after TTL."""
        bot = AsyncMock()
        mock_context = HandlerContext(bot=bot, state=AppState(), args=[])

        # First call fails
        mock_context.bot.get_chat.side_effect = Exception("API error")
        await get_cached_user_bio(mock_context, user_id=123)

        # Advance time past failure TTL
        cache = mock_context.state.data[USER_BIO_CACHE_KEY]
        cached_entry = cache[123]
        # Set TTL to past (negative value means expired)
        cache[123] = (cached_entry[0] - 400, cached_entry[1])  # 400 seconds ago

        # Should retry after cache expires
        mock_context.bot.get_chat.reset_mock()
        mock_context.bot.get_chat.side_effect = None  # Clear side_effect
        mock_context.bot.get_chat.return_value = MagicMock(bio="new bio")
        result = await get_cached_user_bio(mock_context, user_id=123)
        assert result == "new bio"
        mock_context.bot.get_chat.assert_called_once()


class TestSendMonitorAlertToOwner:
    """Tests for send_monitor_alert_to_owner error handling."""

    @pytest.fixture
    def mock_context(self):
        context = MagicMock()
        context.bot = MagicMock()
        context.bot.send_message = AsyncMock()
        return context

    async def test_propagates_send_error_to_except(self, mock_context):
        """Non-RetryAfter error re-raises; caught by outer except Exception, returns False."""
        from aiogram.exceptions import TelegramBadRequest
        mock_context.bot.send_message = AsyncMock(
            side_effect=TelegramBadRequest(method=MagicMock(), message="Test error")
        )

        result = await send_monitor_alert_to_owner(
            context=mock_context,
            alert_chat_id=57747812,
            group_id=-100,
            user_id=42,
            user_name="Test",
            username="test",
            detection_reason="message_bait",
            message_text="cek bio",
            profile_bio=None,
        )
        assert result is False

    async def test_retry_after_failure_returns_false(self, mock_context):
        """Second RetryAfter in send_message_with_retry returns False; logs and returns False."""
        from aiogram.exceptions import TelegramRetryAfter
        mock_context.bot.send_message = AsyncMock(
            side_effect=TelegramRetryAfter(
                method=MagicMock(), message="Flood control", retry_after=1
            )
        )

        with patch("bot.services.telegram_utils.asyncio.sleep"):
            result = await send_monitor_alert_to_owner(
                context=mock_context,
                alert_chat_id=57747812,
                group_id=-100,
                user_id=42,
                user_name="Test",
                username="test",
                detection_reason="message_bait",
                message_text="cek bio",
                profile_bio=None,
            )
        assert result is False
