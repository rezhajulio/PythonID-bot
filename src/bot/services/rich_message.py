"""Extract searchable text and URLs from Telegram rich messages.

Rich messages (``Message.rich_message``, Bot API 10.1+/aiogram 3.29+)
carry their payload in page blocks instead of ``message.text``. Spam
filters that only read ``text``/``caption`` are blind to them — a rich
spam message arrives with empty text while its links and buttons hide
in the block tree. This module walks that tree and returns plain text
and URLs for the spam detectors.

The walker is duck-typed on purpose: aiogram exposes ~25 block types
and a ~30-variant rich-text union, and a newly added variant must not
silently become invisible to the filters again.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_URL_SHAPE_RE = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)


def _url_shaped_candidates(text: str) -> list[str]:
    """Find URL-shaped strings inside plain text.

    Bare URLs in rich blocks have no entity metadata (unlike text
    messages, where Telegram tags them), so shape-check them here.
    Requires a dotted hostname to avoid flagging fragments like
    ``https://`` on their own.
    """
    out: list[str] = []
    for match in _URL_SHAPE_RE.finditer(text):
        candidate = match.group(0).rstrip(".,;:!?)")
        try:
            hostname = urlparse(candidate).hostname
        except Exception:
            continue
        if hostname and "." in hostname:
            out.append(candidate)
    return list(dict.fromkeys(out))

# Attributes that hold nested blocks, cells, buttons, or list items.
# ``button`` is singular (``RichTextButton.button``); ``credit`` carries
# rich text inside quotation/media captions (``RichBlockCaption.credit``).
_CONTAINER_ATTRS = ("blocks", "cells", "buttons", "items", "button")
# Text-bearing attributes besides the generic ``text``. ``name`` (anchor /
# reference ids) is deliberately skipped: internal link targets, not content.
_TEXT_ATTRS = (
    "caption",
    "summary",
    "alternative_text",
    "credit",
    "label",
    "forward_text",
)
# Sub-objects whose own fields are walked for text/URLs: copy-text clipboard
# payloads, login URLs, web apps, inline-query chat pickers.
_PAYLOAD_ATTRS = (
    "login_url",
    "web_app",
    "copy_text",
    "switch_inline_query_chosen_chat",
)

# Nesting deeper than this cannot occur in genuine payloads (Telegram
# documents depth <= 16 for sending); deeper trees are treated as hostile.
_MAX_WALK_DEPTH = 64
# Total nodes visited per walk. Depth alone cannot bound the walk: an
# object with every attribute truthy (e.g. unittest mocks, or hostile
# crafted objects) branches exponentially, so the visited-node count
# is capped as well. Genuine payloads stay far below this.
_MAX_WALK_NODES = 10_000


def _is_rich_node(value: Any) -> bool:
    """Check whether a value is a traversable rich object.

    Rich nodes always come from aiogram's parser. Anything else —
    mocks, foreign objects, hostile lookalikes — is not content and
    must not be descended into (mocks in particular generate infinite
    attribute trees).
    """
    return type(value).__module__.split(".")[0] == "aiogram"


def _walk(
    node: Any,
    texts: list[str],
    urls: list[str],
    depth: int = 0,
    budget: list[int] | None = None,
) -> None:
    """Recursively collect text fragments and URLs from a rich node."""
    if node is None or depth > _MAX_WALK_DEPTH:
        return
    if budget is not None:
        if budget[0] <= 0:
            return
        budget[0] -= 1
    if isinstance(node, str):
        stripped = node.strip()
        if stripped:
            texts.append(stripped)
        return
    if isinstance(node, (list, tuple)):
        for item in node:
            _walk(item, texts, urls, depth + 1, budget)
        return
    if not _is_rich_node(node):
        return

    url = getattr(node, "url", None)
    if isinstance(url, str) and url.strip():
        urls.append(url.strip())
    for attr in _PAYLOAD_ATTRS:
        value = getattr(node, attr, None)
        if value is not None:
            _walk(value, texts, urls, depth + 1, budget)

    for attr in ("text",) + _TEXT_ATTRS:
        value = getattr(node, attr, None)
        if value is not None:
            _walk(value, texts, urls, depth + 1, budget)

    for attr in _CONTAINER_ATTRS:
        value = getattr(node, attr, None)
        if value:
            _walk(value, texts, urls, depth + 1, budget)


def extract_rich_text(rich_message: Any | None) -> str:
    """Return searchable plain text from a rich message, or "" when none.

    Covers headings, paragraphs, table cells, button labels, and custom
    emoji alternative text. URLs are intentionally excluded here — use
    :func:`extract_rich_urls` for those.
    """
    if rich_message is None:
        return ""
    texts: list[str] = []
    try:
        _walk(rich_message, texts, [], 0, [_MAX_WALK_NODES])
    except Exception:
        logger.info("extract_rich_text: failed to walk rich message")
        return ""
    return " ".join(texts)


def extract_rich_urls(rich_message: Any | None) -> list[str]:
    """Return deduplicated URLs from a rich message.

    Covers explicit URL fields (buttons, text links, login/web-app URLs)
    plus URL-shaped strings in plain text: rich blocks carry no entity
    metadata, so a bare ``https://…`` in a paragraph or a copy-text
    payload would otherwise evade link checks.
    """
    if rich_message is None:
        return []
    urls: list[str] = []
    texts: list[str] = []
    try:
        _walk(rich_message, texts, urls, 0, [_MAX_WALK_NODES])
    except Exception:
        logger.info("extract_rich_urls: failed to walk rich message")
        return []
    for text in texts:
        urls.extend(_url_shaped_candidates(text))
    return list(dict.fromkeys(urls))


def has_rich_buttons(rich_message: Any | None) -> bool:
    """Return True if a rich message contains any buttons.

    Buttons appear as ``RichBlockButtons`` blocks or as inline
    ``RichTextButton`` nodes in rich text. No stock Telegram client can
    compose buttons, so their presence marks the message as
    automation-crafted — the same rationale as the inline keyboard spam
    rule.

    The check is duck-typed (block containers plus the inline button
    class name) so new button-carrying variants do not silently slip
    through.
    """
    if rich_message is None:
        return False
    found = False
    budget = [_MAX_WALK_NODES]

    def _visit(node: Any, depth: int = 0) -> None:
        nonlocal found
        if found or node is None or isinstance(node, str):
            return
        if depth > _MAX_WALK_DEPTH or budget[0] <= 0:
            # Absurd nesting or an exploding attribute tree is only
            # craftable, never client-composed: treat as suspicious
            # rather than failing open.
            found = True
            return
        budget[0] -= 1
        if isinstance(node, (list, tuple)):
            for item in node:
                _visit(item, depth + 1)
            return
        if not _is_rich_node(node):
            return
        if getattr(node, "buttons", None):
            found = True
            return
        if getattr(node, "button", None) is not None:
            # Inline text button (``RichTextButton``); the only node type
            # with a singular ``button`` attribute.
            found = True
            return
        for attr in ("text",) + _TEXT_ATTRS + _CONTAINER_ATTRS:
            value = getattr(node, attr, None)
            if value:
                _visit(value, depth + 1)
                if found:
                    return

    try:
        _visit(rich_message)
    except Exception:
        logger.info("has_rich_buttons: failed to walk rich message")
        return False
    return found
