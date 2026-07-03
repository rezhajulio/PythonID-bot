"""Property-based tests using Hypothesis.

Targets pure functions where the domain is well-defined and the function
should hold an invariant regardless of input. These tests complement
the unit/integration suite by stressing the input space in ways the
handwritten tests don't enumerate.

To run just these tests: ``uv run pytest tests/test_properties.py -v``
"""


import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from bot.constants import format_hours_display, format_threshold_display
from bot.handlers.trust import _format_person, _format_person_with_username
from bot.services.telegram_utils import is_url_whitelisted


# Strategies -----------------------------------------------------------------

# Telegram user IDs and group IDs are non-negative / negative integers
# within a plausible range. Not strictly bounded by Telegram but the
# test doesn't need real-world values.
user_id_st = st.integers(min_value=1, max_value=10**10)
group_id_st = st.integers(min_value=-10**12, max_value=0)

# Threshold in minutes: 0 is degenerate (would render as "0 menit") but
# still in the function's domain. Avoid floats since the function takes int.
threshold_minutes_st = st.integers(min_value=0, max_value=10**6)
hours_st = st.integers(min_value=0, max_value=10**6)

# Strings that look like a Telegram display name. Allow empty (degenerate
# but in domain) and printable unicode-ish text.
name_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Zs"),
        blacklist_characters="*_`[]",
    ),
    min_size=0,
    max_size=64,
)
username_st = st.one_of(st.none(), name_st)

# Whitelisted domains from bot.constants.WHITELISTED_URL_DOMAINS include
# github.com, docs.python.org, telegram.org, etc. We don't hardcode the
# list (it can change); instead assert invariants about the function.
url_scheme_st = st.sampled_from(["http", "https", "ftp"])
url_host_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_."),
    min_size=1,
    max_size=63,
).filter(lambda s: s and not s.startswith("-") and not s.startswith("."))


# format_threshold_display ---------------------------------------------------


class TestFormatThresholdDisplay:
    @given(threshold_minutes_st)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_never_contains_negative_numbers(self, minutes: int) -> None:
        """Output is human-readable Indonesian; never a negative number."""
        result = format_threshold_display(minutes)
        # The output may contain a digit, but never a minus sign.
        assert "-" not in result

    @given(threshold_minutes_st)
    @settings(max_examples=200)
    def test_uses_jam_for_hour_or_above(self, minutes: int) -> None:
        """For >= 60 minutes, output ends in 'jam' (hours), not 'menit'."""
        if minutes < 60:
            return
        result = format_threshold_display(minutes)
        assert result.endswith("jam")
        # Hours are minutes // 60
        assert str(minutes // 60) in result

    @given(threshold_minutes_st)
    @settings(max_examples=200)
    def test_uses_menit_for_sub_hour(self, minutes: int) -> None:
        """For < 60 minutes, output ends in 'menit' (minutes)."""
        if minutes >= 60:
            return
        result = format_threshold_display(minutes)
        assert result.endswith("menit")
        assert str(minutes) in result

    @given(threshold_minutes_st)
    @settings(max_examples=200)
    def test_idempotent_repr(self, minutes: int) -> None:
        """Re-formatting the same input produces the same output."""
        assert format_threshold_display(minutes) == format_threshold_display(minutes)


# format_hours_display -------------------------------------------------------


class TestFormatHoursDisplay:
    @given(hours_st)
    @settings(max_examples=200)
    def test_uses_hari_for_day_or_above(self, hours: int) -> None:
        if hours < 24:
            return
        result = format_hours_display(hours)
        assert result.endswith("hari")
        assert str(hours // 24) in result

    @given(hours_st)
    @settings(max_examples=200)
    def test_uses_jam_for_sub_day(self, hours: int) -> None:
        if hours >= 24:
            return
        result = format_hours_display(hours)
        assert result.endswith("jam")
        assert str(hours) in result

    @given(hours_st)
    @settings(max_examples=200)
    def test_idempotent(self, hours: int) -> None:
        assert format_hours_display(hours) == format_hours_display(hours)


# _format_person -------------------------------------------------------------


class TestFormatPerson:
    @given(name_st, user_id_st)
    @settings(max_examples=200)
    def test_empty_name_falls_back_to_user_id(self, name: str, uid: int) -> None:
        """Empty name → 'User <id>' fallback regardless of id."""
        result = _format_person(name, uid)
        if not name:
            assert result == f"User {uid}"
        else:
            assert result == name  # no escaping needed (name has no special chars)

    @given(name_st, user_id_st, username_st)
    @settings(max_examples=200)
    def test_with_username_format(self, name: str, uid: int, username: str | None) -> None:
        """If username given, output contains ' (@<username>)' suffix when truthy."""
        result = _format_person_with_username(name, username, uid)
        if username:
            assert f"(@{username})" in result
        else:
            assert "(@" not in result

    @given(name_st, user_id_st)
    @settings(max_examples=200)
    def test_markdown_special_chars_escaped(self, name: str, uid: int) -> None:
        """Names with MarkdownV1 special chars are escaped (idempotent)."""
        # Hand-pick a name with special chars
        special = "Test_User*name`with[special]chars"
        result = _format_person(special, uid)
        # After escape_markdown, *, _, `, [, ] are escaped.
        # The function is idempotent under repeated escape.
        from telegram.helpers import escape_markdown

        once = escape_markdown(special, version=1)
        twice = escape_markdown(once, version=1)
        # MarkdownV1 escaping is idempotent (PTB escapes the escape too).
        assert result == once or result == twice


# is_url_whitelisted ---------------------------------------------------------


class TestIsUrlWhitelisted:
    @given(url_scheme_st, url_host_st)
    @settings(max_examples=200)
    def test_random_host_is_deterministic_bool(self, scheme: str, host: str) -> None:
        """Random hosts aren't guaranteed unwhitelisted (a generated host could
        collide with a whitelist suffix), but the function must always return
        a plain bool and never raise."""
        url = f"{scheme}://{host}/path?q=1"
        result = is_url_whitelisted(url)
        assert isinstance(result, bool)

    @given(url_scheme_st, url_host_st, st.text(min_size=0, max_size=20))
    @settings(max_examples=100)
    def test_deterministic(self, scheme: str, host: str, path: str) -> None:
        """Same input → same output, every time."""
        url = f"{scheme}://{host}/{path}"
        assert is_url_whitelisted(url) == is_url_whitelisted(url)

    @given(url_scheme_st, url_host_st)
    @settings(max_examples=100)
    def test_query_and_fragment_dont_affect_match(self, scheme: str, host: str) -> None:
        """Query strings and fragments don't change the host match."""
        base = f"{scheme}://{host}/path"
        with_query = f"{base}?a=1&b=2"
        with_fragment = f"{base}#section"
        with_both = f"{base}?a=1#section"
        # All four should yield the same result (function is host-based).
        results = {is_url_whitelisted(u) for u in [base, with_query, with_fragment, with_both]}
        assert len(results) == 1, f"host={host} gave differing results: {results}"

    def test_empty_url_returns_false(self) -> None:
        """Defensive: empty/garbage input doesn't crash, returns False."""
        for bad in ["", "not a url", "://", "http://", "https://"]:
            assert is_url_whitelisted(bad) is False

    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/python/cpython",
            "https://docs.python.org/3/library/typing.html",
            "https://t.me/pythonid",
        ],
    )
    def test_known_whitelisted_urls(self, url: str) -> None:
        """The known tech-domain whitelist definitely matches these."""
        assert is_url_whitelisted(url) is True


# Healthcheck to make sure the strategies are reasonable
@given(st.integers(min_value=0, max_value=1000))
def test_sanity_integer_strategy(x: int) -> None:
    assert 0 <= x <= 1000
