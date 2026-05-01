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
   (e.g. "VIP BCL t.me/+KVUG7Nzphek0N2M1"). In this case the group message
   may be innocuous; the spam is in the bio. We fetch the bio once per
   hour per user and cache it.

On match the handler deletes the message, restricts the user, and posts a
notification to the warning topic.
"""

import logging
import re
import unicodedata
from time import monotonic

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from bot.constants import (
    BIO_BAIT_SPAM_NOTIFICATION,
    BIO_BAIT_SPAM_NOTIFICATION_NO_RESTRICT,
    BIO_LINK_SPAM_NOTIFICATION,
    BIO_LINK_SPAM_NOTIFICATION_NO_RESTRICT,
    RESTRICTED_PERMISSIONS,
    WHITELISTED_TELEGRAM_PATHS,
)
from bot.group_config import get_group_config_for_update
from bot.handlers.anti_spam import is_url_whitelisted
from bot.services.telegram_utils import get_user_mention

logger = logging.getLogger(__name__)

# Maximum normalized text length to consider as bait. Real bait is short.
BIO_BAIT_MAX_LENGTH = 80

# Per-user bio cache (TTL in seconds). Stored in context.bot_data.
USER_BIO_CACHE_KEY = "user_bio_cache"
USER_BIO_CACHE_TTL_SECONDS = 3600

# Strip common zero-width characters used to break keyword filters.
ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u2060-\u2064\ufeff]")

# Canonicalize obfuscated "bio" variants to a plain "bio" token.
# Covers: bio, b1o, b!o, b.i.o, b i o, b-i-o, bioh, bioo, bioohh, plus
# Cyrillic look-alikes ь and і. (Input is already lowercased.)
BIO_OBFUSCATED_RE = re.compile(
    r"\b[bь][\s._\-]*[i1!і][\s._\-]*[o0о](?:[\s._\-]*h+)?\b"
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
#   (a) imperative cue + bio (with optional address particle), OR
#   (b) bio + first-person possessive at end of message, OR
#   (c) imperative cue + profil/profile + possessive, OR
#   (d) imperative cue + my + profile/bio.
BIO_BAIT_PATTERNS = (
    re.compile(
        r"\b(?:cek|check|liat|lihat|buka|open|view|see|kunjungi|kunjungin)\b"
        rf"(?:\s+\w+){{0,2}}\s+\bbio\b{_BIO_SUFFIX_RE}"
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

# Telegram private invite links (e.g. t.me/+KVUG7Nzphek0N2M1).
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
    "open", "available", "ready",
})


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

    mentions = {
        m.group(1).lower()
        for m in TELEGRAM_USERNAME_RE.finditer(normalized)
        if m.group(1).lower() not in WHITELISTED_TELEGRAM_PATHS
    }
    if len(mentions) >= 2:
        return True
    if mentions and any(hint in lowered for hint in BIO_PROMO_HINTS):
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


async def get_cached_user_bio(
    context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> str | None:
    """
    Fetch the user's profile bio with a per-user TTL cache.

    Returns the cached bio if the entry is still fresh. Otherwise calls
    bot.get_chat(user_id) and stores the result. Errors are swallowed and
    cause this function to return None for that call.
    """
    cache = _get_user_bio_cache(context)
    now = monotonic()

    cached = cache.get(user_id)
    if cached and cached[0] > now:
        return cached[1]

    try:
        chat = await context.bot.get_chat(user_id)
        bio = (getattr(chat, "bio", None) or "").strip() or None
    except Exception:
        logger.debug("Failed to fetch user bio: user_id=%s", user_id, exc_info=True)
        return None

    cache[user_id] = (now + USER_BIO_CACHE_TTL_SECONDS, bio)
    return bio


async def handle_bio_bait_spam(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle bio-bait spam (phrase in message OR promo links in user's bio).

    Skips bots and admins. On match, deletes the message, restricts the
    user, and notifies the warning topic. Always raises ApplicationHandlerStop
    after handling a detected message to prevent downstream handlers from
    re-processing it.

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

    admin_ids = context.bot_data.get("group_admin_ids", {}).get(group_config.group_id, [])
    if user.id in admin_ids:
        return

    text = update.message.text or update.message.caption or ""

    detection_reason: str | None = None
    if text and is_bio_bait_spam(text):
        detection_reason = "message_bait"
    else:
        user_bio = await get_cached_user_bio(context, user.id)
        if user_bio and has_suspicious_bio_links(user_bio):
            detection_reason = "bio_links"

    if detection_reason is None:
        return

    user_mention = get_user_mention(user)
    logger.info(
        f"Bio bait spam detected: user_id={user.id}, "
        f"group_id={group_config.group_id}, reason={detection_reason}"
    )

    try:
        await update.message.delete()
        logger.info(f"Deleted bio bait spam from user_id={user.id}")
    except Exception:
        logger.error(
            f"Failed to delete bio bait spam: user_id={user.id}",
            exc_info=True,
        )

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
        logger.error(
            f"Failed to restrict user for bio bait spam: user_id={user.id}",
            exc_info=True,
        )

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
        logger.error(
            f"Failed to send bio bait spam notification: user_id={user.id}",
            exc_info=True,
        )

    raise ApplicationHandlerStop
