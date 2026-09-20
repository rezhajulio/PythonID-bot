"""
Client for the classifier.dev zero-shot text classification API.

Provides :func:`classify_text` for single-input classification and a
small circuit breaker + daily budget so a dead or rate-limited upstream
never turns into a per-message failure loop. All functions fail soft:
they return ``None`` instead of raising, and every failure mode is
logged.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

CLASSIFIER_API_URL = "https://classifier.dev"

_WIB = ZoneInfo("Asia/Jakarta")

DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_FAILURE_THRESHOLD = 3
DEFAULT_COOLDOWN_SECONDS = 600.0
DEFAULT_DAILY_BUDGET = 15_000


@dataclass
class ClassificationResult:
    """Single-input classification outcome.

    ``confidence`` is ``None`` when the upstream reports no calibrated
    score (treat it as "not confident").
    """

    label: str
    confidence: float | None
    model: str | None = None


@dataclass
class CircuitState:
    """Mutable circuit-breaker state for the classifier API."""

    consecutive_failures: int = 0
    opened_at: float | None = None


def circuit_allows(
    state: CircuitState, now: float, cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS
) -> bool:
    """Return True if a request may go out.

    An open breaker stops blocking once the cooldown elapses; a
    successful request then closes the breaker, a failed one re-opens
    it (``opened_at`` is only cleared by a success).
    """
    if state.opened_at is None:
        return True
    return now - state.opened_at >= cooldown_seconds


def circuit_on_success(state: CircuitState) -> None:
    """Close the breaker after a successful request."""
    state.consecutive_failures = 0
    state.opened_at = None


def circuit_on_failure(
    state: CircuitState, now: float, failure_threshold: int = DEFAULT_FAILURE_THRESHOLD
) -> None:
    """Record a failure, opening the breaker once the threshold is reached."""
    state.consecutive_failures += 1
    if state.consecutive_failures >= failure_threshold:
        state.opened_at = now


@dataclass
class _DailyBudget:
    """In-process daily classification counter, reset at midnight WIB."""

    day: str = field(default_factory=lambda: datetime.now(_WIB).strftime("%Y-%m-%d"))
    used: int = 0

    def try_spend(self, limit: int, *, now: datetime | None = None) -> bool:
        current_day = (now or datetime.now(_WIB)).strftime("%Y-%m-%d")
        if current_day != self.day:
            self.day = current_day
            self.used = 0
        if self.used >= limit:
            return False
        self.used += 1
        return True


_budget = _DailyBudget()
_circuit = CircuitState()

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        # No httpx-level timeout: asyncio.wait_for in classify_text is the
        # single timeout knob (settings.classifier_timeout_seconds).
        _client = httpx.AsyncClient(timeout=None)
    return _client


def get_circuit_state() -> CircuitState:
    """Return the shared circuit-breaker state (for tests and introspection)."""
    return _circuit


def reset_shared_state() -> None:
    """Reset breaker and budget to defaults (for tests)."""
    global _client
    _circuit.consecutive_failures = 0
    _circuit.opened_at = None
    _budget.day = datetime.now(_WIB).strftime("%Y-%m-%d")
    _budget.used = 0
    _client = None


def breaker_is_open(now: float, cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS) -> bool:
    """Return True when the shared breaker blocks outgoing requests."""
    return not circuit_allows(_circuit, now, cooldown_seconds)


def daily_budget_exhausted(limit: int = DEFAULT_DAILY_BUDGET) -> bool:
    """Return True when the shared daily budget is spent (without spending)."""
    return _budget.day == datetime.now(_WIB).strftime("%Y-%m-%d") and _budget.used >= limit


def try_spend_budget(limit: int = DEFAULT_DAILY_BUDGET) -> bool:
    """Spend one classification from the shared daily budget."""
    return _budget.try_spend(limit)


async def classify_text(
    text: str,
    *,
    labels: list[str],
    instructions: str | None = None,
    api_url: str = CLASSIFIER_API_URL,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> ClassificationResult | None:
    """Classify one text via the classifier.dev fast tier.

    Returns ``None`` on any failure (timeout, HTTP error, rate limit,
    malformed response). Never raises.
    """
    global _client
    payload: dict[str, object] = {"input": text, "labels": labels}
    if instructions:
        payload["instructions"] = instructions
    try:
        if _client is None:
            _client = _get_client()
        response = await asyncio.wait_for(
            _client.post(api_url, json=payload), timeout=timeout
        )
        if response.status_code != 200:
            circuit_on_failure(_circuit, time.monotonic())
            logger.warning(
                f"classifier.dev returned HTTP {response.status_code}; "
                f"consecutive_failures={_circuit.consecutive_failures}"
            )
            return None
        data = response.json()
        result = data["results"][0]
        label = result.get("label")
        if not isinstance(label, str):
            logger.warning("classifier.dev response missing label field")
            return None
        confidence = result.get("confidence")
        if confidence is not None and not isinstance(confidence, (int, float)):
            confidence = None
        model = result.get("model")
        circuit_on_success(_circuit)
        return ClassificationResult(
            label=label,
            confidence=float(confidence) if confidence is not None else None,
            model=model if isinstance(model, str) else None,
        )
    except (TimeoutError, asyncio.TimeoutError):
        circuit_on_failure(_circuit, time.monotonic())
        logger.warning("classifier.dev request timed out")
        return None
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        circuit_on_failure(_circuit, time.monotonic())
        logger.warning(f"classifier.dev request failed: {exc}")
        return None
