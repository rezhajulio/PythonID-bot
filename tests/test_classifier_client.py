"""Tests for the classifier.dev client service."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from hypothesis import given, settings as hypothesis_settings
from hypothesis import strategies as st

from bot.services import classifier_client
from bot.services.classifier_client import (
    ClassificationResult,
    CircuitState,
    _DailyBudget,
    breaker_is_open,
    circuit_allows,
    circuit_on_failure,
    circuit_on_success,
    classify_text,
)

WIB = classifier_client._WIB


@pytest.fixture(autouse=True)
async def reset_state():
    classifier_client.reset_shared_state()
    yield
    await classifier_client.close_client()


def make_response(status_code: int = 200, payload: dict | None = None) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    if payload is not None:
        response.json.return_value = payload
    else:
        response.json.side_effect = ValueError("no json")
    return response


def make_client(response: MagicMock | None = None, exc: Exception | None = None) -> MagicMock:
    client = MagicMock(spec=httpx.AsyncClient)
    if exc is not None:
        client.post = AsyncMock(side_effect=exc)
    else:
        client.post = AsyncMock(return_value=response)
    return client


class TestCircuitAllows:
    """Tests for circuit breaker state transitions."""

    def test_closed_by_default(self):
        state = CircuitState()
        assert circuit_allows(state, now=0.0) is True

    def test_opens_after_threshold_failures(self):
        state = CircuitState()
        for i in range(3):
            circuit_on_failure(state, now=float(i), failure_threshold=3)
        assert state.opened_at == 2.0
        assert circuit_allows(state, now=2.0, cooldown_seconds=600.0) is False

    def test_stays_open_before_cooldown(self):
        state = CircuitState()
        circuit_on_failure(state, now=100.0, failure_threshold=1)
        assert circuit_allows(state, now=699.9, cooldown_seconds=600.0) is False

    def test_half_open_after_cooldown(self):
        state = CircuitState()
        circuit_on_failure(state, now=100.0, failure_threshold=1)
        assert circuit_allows(state, now=700.0, cooldown_seconds=600.0) is True

    def test_success_resets_failures(self):
        state = CircuitState()
        circuit_on_failure(state, now=1.0, failure_threshold=3)
        circuit_on_failure(state, now=2.0, failure_threshold=3)
        circuit_on_success(state)
        assert state.consecutive_failures == 0
        assert circuit_allows(state, now=3.0) is True

    def test_success_closes_open_breaker(self):
        state = CircuitState()
        circuit_on_failure(state, now=1.0, failure_threshold=1)
        circuit_on_success(state)
        assert circuit_allows(state, now=1.5) is True

    @hypothesis_settings(max_examples=200)
    @given(
        threshold=st.integers(min_value=1, max_value=10),
        failures=st.integers(min_value=1, max_value=50),
        now=st.floats(min_value=0, max_value=1e9, allow_nan=False),
        cooldown=st.floats(min_value=0.1, max_value=3600, allow_nan=False),
    )
    def test_breaker_opens_exactly_at_threshold(
        self, threshold: int, failures: int, now: float, cooldown: float
    ):
        state = CircuitState()
        for i in range(failures):
            circuit_on_failure(state, now=now + i, failure_threshold=threshold)
        if failures >= threshold:
            last_failure = now + failures - 1
            assert circuit_allows(state, now, cooldown_seconds=cooldown) is False
            assert (
                circuit_allows(state, last_failure + cooldown * 2, cooldown_seconds=cooldown)
                is True
            )
        else:
            assert circuit_allows(state, now, cooldown_seconds=cooldown) is True

    @hypothesis_settings(max_examples=200)
    @given(
        failures_before=st.integers(min_value=0, max_value=9),
        now=st.floats(min_value=0, max_value=1e9, allow_nan=False),
    )
    def test_success_always_closes_breaker(self, failures_before: int, now: float):
        state = CircuitState()
        for i in range(failures_before):
            circuit_on_failure(state, now=now + i, failure_threshold=1)
        circuit_on_failure(state, now=now, failure_threshold=1)
        circuit_on_success(state)
        assert circuit_allows(state, now + 0.001) is True
        assert state.consecutive_failures == 0


class TestBreakerIsOpen:
    """Tests for the shared-breaker convenience wrapper."""

    def test_closed_initially(self):
        assert breaker_is_open(0.0) is False

    def test_open_after_failures(self):
        state = classifier_client.get_circuit_state()
        for i in range(3):
            circuit_on_failure(state, now=float(i))
        assert breaker_is_open(0.0) is True


class TestDailyBudget:
    """Tests for the daily classification budget."""

    def test_spend_within_limit(self):
        budget = _DailyBudget()
        assert all(budget.try_spend(3) for _ in range(3)) is True

    def test_exhausted_at_limit(self):
        budget = _DailyBudget()
        for _ in range(3):
            budget.try_spend(3)
        assert budget.try_spend(3) is False

    def test_resets_on_new_day(self):
        budget = _DailyBudget()
        day1 = datetime(2026, 9, 19, 10, 0, tzinfo=WIB)
        day2 = datetime(2026, 9, 20, 10, 0, tzinfo=WIB)
        assert budget.try_spend(1, now=day1) is True
        assert budget.try_spend(1, now=day1) is False
        assert budget.try_spend(1, now=day2) is True
        assert budget.day == day2.strftime("%Y-%m-%d")
        assert budget.used == 1

    @hypothesis_settings(max_examples=200)
    @given(
        limit=st.integers(min_value=1, max_value=100),
        spends=st.integers(min_value=1, max_value=200),
    )
    def test_never_exceeds_limit(self, limit: int, spends: int):
        budget = _DailyBudget()
        results = [budget.try_spend(limit) for _ in range(spends)]
        assert sum(results) == min(limit, spends)
        assert budget.used == min(limit, spends)


class TestTrySpendBudget:
    """Tests for the shared-budget wrapper."""

    def test_shared_budget_spends(self):
        assert classifier_client.try_spend_budget(2) is True
        assert classifier_client.try_spend_budget(2) is True
        assert classifier_client.daily_budget_exhausted(2) is True
        assert classifier_client.daily_budget_exhausted(3) is False


class TestCloseClient:
    """Tests for the shared-client shutdown hook."""

    async def test_close_releases_client(self):
        classifier_client._get_client()
        assert classifier_client._client is not None
        await classifier_client.close_client()
        assert classifier_client._client is None

    async def test_close_is_noop_without_client(self):
        assert classifier_client._client is None
        await classifier_client.close_client()
        assert classifier_client._client is None


class TestClassifyText:
    """Tests for the classify_text API call."""

    async def test_success(self):
        payload = {
            "results": [{"label": "spam", "confidence": 0.97, "model": "jev-1.13.0"}]
        }
        client = make_client(make_response(200, payload))
        with patch.object(classifier_client, "_client", client):
            result = await classify_text("halo", labels=["spam", "not spam"])
        assert result == ClassificationResult(
            label="spam", confidence=0.97, model="jev-1.13.0"
        )
        body = client.post.await_args.kwargs["json"]
        assert body == {"input": "halo", "labels": ["spam", "not spam"]}

    async def test_instructions_included(self):
        payload = {"results": [{"label": "spam", "confidence": 1}]}
        client = make_client(make_response(200, payload))
        with patch.object(classifier_client, "_client", client):
            await classify_text("halo", labels=["spam"], instructions="pen judging")
        assert client.post.await_args.kwargs["json"]["instructions"] == "pen judging"

    async def test_null_confidence_becomes_none(self):
        payload = {"results": [{"label": "not spam", "confidence": None}]}
        client = make_client(make_response(200, payload))
        with patch.object(classifier_client, "_client", client):
            result = await classify_text("halo", labels=["spam", "not spam"])
        assert result is not None
        assert result.confidence is None

    async def test_non_200_returns_none_and_fails_circuit(self):
        client = make_client(make_response(429, {"error": "rate limited"}))
        with patch.object(classifier_client, "_client", client):
            assert await classify_text("halo", labels=["spam"]) is None
        assert classifier_client.get_circuit_state().consecutive_failures == 1

    async def test_malformed_json_returns_none(self):
        client = make_client(make_response(200, {}))
        with patch.object(classifier_client, "_client", client):
            assert await classify_text("halo", labels=["spam"]) is None

    async def test_timeout_returns_none_and_fails_circuit(self):
        client = make_client(exc=httpx.ReadTimeout("too slow"))
        with patch.object(classifier_client, "_client", client):
            assert await classify_text("halo", labels=["spam"], timeout=0.01) is None
        state = classifier_client.get_circuit_state()
        assert state.consecutive_failures == 1

    async def test_wait_for_timeout_returns_none(self):
        async def slow_post(*args, **kwargs):
            await asyncio.sleep(0.2)

        client = MagicMock(spec=httpx.AsyncClient)
        client.post = slow_post
        with patch.object(classifier_client, "_client", client):
            assert await classify_text("halo", labels=["spam"], timeout=0.01) is None
        assert classifier_client.get_circuit_state().consecutive_failures == 1

    async def test_lazy_client_creation(self):
        assert classifier_client._client is None
        assert classifier_client._get_client() is classifier_client._client
        assert classifier_client._client is not None

    async def test_classify_creates_shared_client_lazily(self):
        payload = {"results": [{"label": "spam", "confidence": 1}]}
        mock_client = make_client(make_response(200, payload))
        with (
            patch(
                "bot.services.classifier_client.httpx.AsyncClient",
                return_value=mock_client,
            ) as mock_ctor,
        ):
            result = await classify_text("halo", labels=["spam"])
        mock_ctor.assert_called_once()
        assert result is not None
        assert result.label == "spam"

    async def test_payload_without_instructions(self):
        payload = {"results": [{"label": "spam", "confidence": 1}]}
        client = make_client(make_response(200, payload))
        with patch.object(classifier_client, "_client", client):
            await classify_text("halo", labels=["spam"], instructions=None)
        assert "instructions" not in client.post.await_args.kwargs["json"]

    async def test_non_string_label_returns_none(self):
        payload = {"results": [{"confidence": 0.9}]}
        client = make_client(make_response(200, payload))
        with patch.object(classifier_client, "_client", client):
            assert await classify_text("halo", labels=["spam"]) is None

    async def test_non_numeric_confidence_becomes_none(self):
        payload = {"results": [{"label": "spam", "confidence": "very high"}]}
        client = make_client(make_response(200, payload))
        with patch.object(classifier_client, "_client", client):
            result = await classify_text("halo", labels=["spam"])
        assert result is not None
        assert result.confidence is None

    async def test_http_error_returns_none(self):
        client = make_client(exc=httpx.ConnectError("refused"))
        with patch.object(classifier_client, "_client", client):
            assert await classify_text("halo", labels=["spam"]) is None

    async def test_success_closes_circuit(self):
        payload = {"results": [{"label": "spam", "confidence": 0.9}]}
        client = make_client(make_response(200, payload))
        state = classifier_client.get_circuit_state()
        circuit_on_failure(state, now=1.0, failure_threshold=1)
        with patch.object(classifier_client, "_client", client):
            await classify_text("halo", labels=["spam"])
        assert state.consecutive_failures == 0
        assert state.opened_at is None
