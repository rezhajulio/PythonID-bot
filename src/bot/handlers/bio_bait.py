"""
Bio bait spam detection handler.

Spammers commonly post short messages telling other members to check their
profile bio, where the bio itself contains a link to a Telegram channel/group
(typically scam/promo/gambling). To evade keyword filters they obfuscate the
word "bio" with misspellings, separators, and Cyrillic look-alikes
(e.g. "byooh", "b.i.o", "Ьіо", "b1o", "bioohh").

This handler covers TWO related vectors:

1. Bait phrase in the message text (e.g. "cek bio aku", "liat byoh").
2. The user's *Telegram profile bio* itself contains promo/scam links
   (private t.me/+ invite links and/or non-whitelisted @mentions). In
   this case the group message may be innocuous; the spam is in the bio.
   We fetch the bio once per hour per user and cache it.

On match the handler deletes the message, restricts the user, and posts a
notification to the warning topic.
"""

import logging
import re
import unicodedata
from time import monotonic

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes, filters as _filters

from bot.constants import (
    BIO_BAIT_MONITOR_ALERT,
    BIO_BAIT_SPAM_NOTIFICATION,
    BIO_BAIT_SPAM_NOTIFICATION_NO_RESTRICT,
    BIO_LINK_SPAM_NOTIFICATION,
    BIO_LINK_SPAM_NOTIFICATION_NO_RESTRICT,
    RESTRICTED_PERMISSIONS,
    WHITELISTED_TELEGRAM_PATHS,
)
from bot.group_config import get_group_config_for_update
from bot.services.telegram_utils import (
    get_user_mention,
    is_user_admin_or_trusted,
    is_url_whitelisted,
    send_message_with_retry,
)

# Filter for bio-bait handler registration in main.py.
# Must NOT restrict to TEXT|CAPTION so non-text messages (e.g. photos
# without caption) reach the handler for bio-link detection.
BIO_BAIT_FILTER = _filters.ChatType.GROUPS & ~_filters.COMMAND


logger = logging.getLogger(__name__)

# Maximum normalized text length to consider as bait. Real bait is short.
BIO_BAIT_MAX_LENGTH = 80

# Per-user bio cache (TTL in seconds). Stored in context.bot_data.
USER_BIO_CACHE_KEY = "user_bio_cache"
USER_BIO_CACHE_TTL_SECONDS = 3600
USER_BIO_CACHE_MAX_SIZE = 2000

# Failure cache TTL (shorter than success TTL)
USER_BIO_FAILURE_CACHE_TTL_SECONDS = 300  # 5 minutes

# Sentinel value to indicate a cached failure
_BIO_CACHE_FAILURE = "__FAILURE__"

# Telegram hard limit per message text.
MAX_TELEGRAM_MESSAGE_LENGTH = 4096

# Strip common zero-width characters used to break keyword filters.
ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u2060-\u2064\ufeff]")

# Canonicalize obfuscated "bio" variants to a plain "bio" token.
# Covers: bio, b1o, b!o, b.i.o, b i o, b-i-o, bioh, bioo, bioohh, plus
# Cyrillic look-alikes ь and і. (Input is already lowercased.)
BIO_OBFUSCATED_RE = re.compile(
    r"\b[bь][ь\s._\-]*[i1!і][\s._\-]*[o0о](?:[\s._\-]*h+)?\b"
)

# Canonicalize "byo / byoh / byooh" variants.
BYO_OBFUSCATED_RE = re.compile(
    r"\b[bь][\s._\-]*y[\s._\-]*[o0о](?:[\s._\-]*h+)?\b"
)

# Catch elongated forms after partial canonicalization, e.g. "biooo", "byoooh".
BIO_ELONGATED_RE = re.compile(r"\bb(?:i|y)o+h*\b")

# Common Indonesian first-person possessives + English equivalents.
_BIO_OWNER_RE = r"\b(?:aku|gw|gue|saya|ku|ane|me|my)\b"
# Optional address particle that often follows bait phrases.
_BIO_SUFFIX_RE = r"(?:\s+\b(?:dong|ya|kak|bro|sis)\b)?"

# Bait phrase patterns matched against the normalized text.
# Each requires either:
#   (a) imperative cue + bio + ownership cue OR end-of-string, OR
#   (b) bio + first-person possessive at end of message, OR
#   (c) imperative cue + profil/profile + possessive, OR
#   (d) imperative cue + my + profile/bio.
BIO_BAIT_PATTERNS = (
    re.compile(
        r"\b(?:cek|check|liat|lihat|buka|open|view|see|kunjungi|kunjungin)\b"
        rf"(?:\s+\w+){{0,2}}\s+\bbio\b"
        rf"(?:\s+{_BIO_OWNER_RE})?"  # optional ownership
        rf"{_BIO_SUFFIX_RE}$"  # must be at end of message
    ),
    re.compile(
        rf"\bbio\b\s+{_BIO_OWNER_RE}"
        rf"(?:\s+\b(?:update|updated|baru|new)\b)?"
        rf"{_BIO_SUFFIX_RE}$"
    ),
    re.compile(
        r"\b(?:cek|check|liat|lihat|buka|open|view|see)\b"
        r"\s+\b(?:profil|profile)\b"
        rf"\s+{_BIO_OWNER_RE}{_BIO_SUFFIX_RE}"
    ),
    re.compile(
        r"\b(?:cek|check|liat|lihat|buka|open|view|see)\b"
        r"\s+\bmy\b"
        r"\s+\b(?:profile|bio)\b"
    ),
)

# Telegram private invite links (t.me/+<hash>).
TELEGRAM_INVITE_LINK_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/\+[A-Za-z0-9_-]{8,}",
    re.IGNORECASE,
)

# Telegram public channel/user links (e.g. t.me/somechannel).
TELEGRAM_LINK_RE = re.compile(
    r"((?:https?://)?(?:t\.me|telegram\.me)/[A-Za-z][A-Za-z0-9_]{4,31}(?:/[^\s]+)?)",
    re.IGNORECASE,
)

# Bare @username mentions.
TELEGRAM_USERNAME_RE = re.compile(r"(?<!\w)@([A-Za-z][A-Za-z0-9_]{4,31})\b")

# Promo hint words that, combined with a single non-whitelisted @mention,
# escalate a bio to suspicious. Single mentions alone are not enough.
BIO_PROMO_HINTS = frozenset({
    "vip", "join", "promo", "channel", "grup", "group", "asp", "bcl",
})

# Word-boundary regex for promo hints to avoid substring false positives.
_BIO_PROMO_HINTS_RE = re.compile(
    r"\b(?:" + "|".join(sorted(BIO_PROMO_HINTS)) + r")\b"
)

def normalize_bio_bait_text(text: str) -> str:
    """
    Normalize text for bio-bait detection.

    Applies NFKC, lowercases, strips zero-width characters, canonicalizes
    obfuscated bio/byo variants to "bio", strips remaining punctuation,
    and collapses whitespace.

    Args:
        text: Raw message text or caption.

    Returns:
        Normalized text suitable for regex matching.
    """
    text = unicodedata.normalize("NFKC", text).lower()
    text = ZERO_WIDTH_RE.sub("", text)
    text = BIO_OBFUSCATED_RE.sub(" bio ", text)
    text = BYO_OBFUSCATED_RE.sub(" bio ", text)
    text = BIO_ELONGATED_RE.sub(" bio ", text)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def is_bio_bait_spam(text: str) -> bool:
    """
    Check whether the given text matches any bio bait pattern.

    Args:
        text: Raw message text or caption.

    Returns:
        bool: True if text matches a bait pattern within the length cap.
    """
    normalized = normalize_bio_bait_text(text)
    if not normalized:
        return False
    if len(normalized) > BIO_BAIT_MAX_LENGTH:
        return False
    return any(pattern.search(normalized) for pattern in BIO_BAIT_PATTERNS)

def has_suspicious_bio_links(bio: str) -> bool:
    """
    Check whether a user's bio text contains suspicious Telegram promo refs.

    Triggers on:
        - Any t.me/+... private invite link.
        - Any non-whitelisted t.me/{username} link.
        - Two or more non-whitelisted bare @mentions.
        - A single non-whitelisted @mention combined with a promo hint word.

    Args:
        bio: Raw bio string from the user's profile.

    Returns:
        bool: True if the bio is considered spammy.
    """
    if not bio:
        return False

    normalized = unicodedata.normalize("NFKC", bio)
    lowered = normalized.lower()

    if TELEGRAM_INVITE_LINK_RE.search(normalized):
        return True

    for match in TELEGRAM_LINK_RE.finditer(normalized):
        if not is_url_whitelisted(match.group(1)):
            return True

    mention_count = sum(
        1 for m in TELEGRAM_USERNAME_RE.finditer(normalized)
        if m.group(1).lower() not in WHITELISTED_TELEGRAM_PATHS
    )
    if mention_count >= 2:
        return True
    if mention_count == 1 and _BIO_PROMO_HINTS_RE.search(lowered):
        return True

    return False

def _get_user_bio_cache(
    context: ContextTypes.DEFAULT_TYPE,
) -> dict[int, tuple[float, str | None]]:
    """Get or initialize the per-user bio cache stored in bot_data."""
    return context.bot_data.setdefault(USER_BIO_CACHE_KEY, {})

def clear_cached_user_bio(
    context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> None:
    """Remove a user's bio cache entry (call after restriction)."""
    _get_user_bio_cache(context).pop(user_id, None)



def _chunk_telegram_text(text: str, max_length: int = MAX_TELEGRAM_MESSAGE_LENGTH) -> list[str]:
    """Split text into Telegram-safe chunks."""
    if len(text) <= max_length:
        return [text]
    return [text[i : i + max_length] for i in range(0, len(text), max_length)]


async def send_monitor_alert_to_owner(
    context: ContextTypes.DEFAULT_TYPE,
    alert_chat_id: int,
    group_id: int,
    user_id: int,
    user_name: str,
    username: str | None,
    detection_reason: str,
    message_text: str,
    profile_bio: str | None,
) -> bool:
    """Send monitor-only detection details to owner/admin chat ID."""
    reason_label = "message_bait" if detection_reason == "message_bait" else "bio_links"
    alert_text = BIO_BAIT_MONITOR_ALERT.format(
        reason=reason_label,
        group_id=group_id,
        user_id=user_id,
        user_name=user_name,
        username=f"@{username}" if username else "-",
        message_text=message_text or "(kosong)",
        profile_bio=profile_bio or "(kosong)",
    )

    try:
        for chunk in _chunk_telegram_text(alert_text):
            ok = await send_message_with_retry(
                context.bot, chat_id=alert_chat_id, text=chunk
            )
            if not ok:
                logger.error(
                    f"Failed to send bio bait monitor alert chunk: user_id={user_id}, group_id={group_id}"
                )
                return False
        return True
    except Exception:
        logger.error(f"Failed to send bio bait monitor alert: user_id={user_id}, group_id={group_id}")
        return False


async def get_cached_user_bio(
    context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> str | None:
    """
    Fetch the user's profile bio with a per-user TTL cache.

    Returns the cached bio if the entry is still fresh. Otherwise calls
    bot.get_chat(user_id) and stores the result. Failures are cached for
    a shorter TTL (5 min) to prevent repeated API calls.
    """
    cache = _get_user_bio_cache(context)
    now = monotonic()

    cached = cache.get(user_id)
    if cached:
        ttl, value = cached
        if ttl > now:
            # Return None for cached failures, bio string for cached successes
            return None if value is _BIO_CACHE_FAILURE else value

    if len(cache) >= USER_BIO_CACHE_MAX_SIZE:
        sorted_keys = sorted(cache, key=lambda k: cache[k][0])
        for k in sorted_keys[: USER_BIO_CACHE_MAX_SIZE // 2]:
            del cache[k]

    try:
        chat = await context.bot.get_chat(user_id)
        bio = (getattr(chat, "bio", None) or "").strip() or None
        cache[user_id] = (now + USER_BIO_CACHE_TTL_SECONDS, bio)
        return bio
    except Exception:
        logger.debug(f"Failed to fetch user bio: user_id={user_id}", exc_info=True)
        # Cache failure with shorter TTL
        cache[user_id] = (now + USER_BIO_FAILURE_CACHE_TTL_SECONDS, _BIO_CACHE_FAILURE)
        return None


async def _enforce_bio_bait_restriction(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    group_config,
    user,
    detection_reason: str,
) -> None:
    """Delete, restrict, notify for confirmed bio bait spam. Caller raises ApplicationHandlerStop."""
    user_mention = get_user_mention(user)

    try:
        await update.message.delete()
        logger.info(f"Deleted bio bait spam from user_id={user.id}")
    except Exception:
        logger.error(f"Failed to delete bio bait spam: user_id={user.id}", exc_info=True)

    restricted = False
    try:
        await context.bot.restrict_chat_member(
            chat_id=group_config.group_id,
            user_id=user.id,
            permissions=RESTRICTED_PERMISSIONS,
        )
        restricted = True
        clear_cached_user_bio(context, user.id)
        logger.info(f"Restricted user_id={user.id} for bio bait spam")
    except Exception:
        logger.error(f"Failed to restrict user for bio bait spam: user_id={user.id}", exc_info=True)

    try:
        if detection_reason == "bio_links":
            template = (
                BIO_LINK_SPAM_NOTIFICATION if restricted
                else BIO_LINK_SPAM_NOTIFICATION_NO_RESTRICT
            )
        else:
            template = (
                BIO_BAIT_SPAM_NOTIFICATION if restricted
                else BIO_BAIT_SPAM_NOTIFICATION_NO_RESTRICT
            )
        notification_text = template.format(
            user_mention=user_mention,
            rules_link=group_config.rules_link,
        )
        await context.bot.send_message(
            chat_id=group_config.group_id,
            message_thread_id=group_config.warning_topic_id,
            text=notification_text,
            parse_mode="Markdown",
        )
        logger.info(f"Sent bio bait spam notification for user_id={user.id}")
    except Exception:
        logger.error(f"Failed to send bio bait spam notification: user_id={user.id}", exc_info=True)


async def handle_bio_bait_spam(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle bio-bait spam (phrase in message OR promo links in user's bio).

    Skips bots and admins. In enforcement mode, deletes the message,
    restricts the user, notifies the warning topic, and raises
    ApplicationHandlerStop. In monitor-only mode, only records metrics and
    optionally sends owner alerts without affecting user message flow.

    Args:
        update: Telegram update containing the message.
        context: Bot context with helper methods.
    """
    if not update.message or not update.message.from_user:
        return

    group_config = get_group_config_for_update(update)
    if group_config is None:
        return

    if not group_config.bio_bait_enabled:
        return

    user = update.message.from_user
    if user.is_bot:
        return

    if is_user_admin_or_trusted(context, group_config.group_id, user.id):
        return

    text = update.message.text or update.message.caption or ""

    detection_reason: str | None = None
    user_bio: str | None = None
    if text and is_bio_bait_spam(text):
        detection_reason = "message_bait"
    else:
        user_bio = await get_cached_user_bio(context, user.id)
        if user_bio and has_suspicious_bio_links(user_bio):
            detection_reason = "bio_links"

    if detection_reason is None:
        return

    logger.info(
        f"Bio bait spam detected: user_id={user.id}, group_id={group_config.group_id}, reason={detection_reason}"
    )

    monitor_only = group_config.bio_bait_monitor_only

    if monitor_only:
        alert_chat_id = group_config.bio_bait_alert_chat_id
        if alert_chat_id is not None:
            # Warning-topic guard: skip owner alert if target equals monitored group
            if alert_chat_id == group_config.group_id:
                logger.warning(
                    f"Skipping bio bait monitor alert: alert_chat_id matches monitored group (warning topic). group_id={group_config.group_id}"
                )
            else:
                if user_bio is None:
                    user_bio = await get_cached_user_bio(context, user.id)
                await send_monitor_alert_to_owner(
                    context=context,
                    alert_chat_id=alert_chat_id,
                    group_id=group_config.group_id,
                    user_id=user.id,
                    user_name=user.full_name,
                    username=user.username,
                    detection_reason=detection_reason,
                    message_text=text,
                    profile_bio=user_bio,
                )

        logger.info(
            f"Bio bait monitor-only mode: no delete/restrict (user_id={user.id}, group_id={group_config.group_id})"
        )
        return

    await _enforce_bio_bait_restriction(update, context, group_config, user, detection_reason)
    raise ApplicationHandlerStop
