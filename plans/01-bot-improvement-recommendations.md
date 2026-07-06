# PythonID Bot — Improvement Recommendations

Status: proposed, nothing implemented yet.
Scope: whole repo, `main` branch as of 2026-07-04 (PR #21 merged, PR #20 open/mergeable).

## Phase 0 — Discovery method (what was actually checked)

Findings below are grounded in one of: reading the source directly, running the
project's own test/lint/type tools, or `gh` against the real repo. Where a
`tokensave` graph-query signal disagreed with ground truth, the graph signal
was discarded — noted explicitly so a future pass doesn't re-trust it:

- `tokensave_test_risk` reported **0% test coverage / has_test=false everywhere**.
  Actual: `uv run pytest --cov=bot --cov-report=term-missing` → **2326 stmts,
  22 missed, 99% coverage, 947 passed**. The graph's static reachability
  heuristic can't see through this project's heavy `AsyncMock`/fixture-based
  test style, so it undercounts coverage to zero. Don't trust it for this repo.
- `tokensave_unused_imports` reported **598 unused imports**. Actual:
  `uv run ruff check .` (which owns F401 in this project) → **zero
  findings**. Same false-positive pattern. Don't trust it for this repo.
- `tokensave_dead_code` flagged **104 symbols**, but the overwhelming majority
  are pytest fixtures (`temp_db`, `mock_update`, `mock_registry`, …) that
  are "dead" only because the graph doesn't model pytest's dependency
  injection by parameter name. Not a real finding.
- `tokensave_complexity`, `tokensave_gini`, and `tokensave_redundancy` line up
  with what a direct read of the flagged files shows — these *are* used
  below.
- Confirmed via `gh pr list` / `gh issue list`: no open issues, PR #20 (the
  ponytail dead-code refactor, which also carries the AGENTS.md/README sync
  and the rebuilt mermaid diagram) is `MERGEABLE` with all 5 CI checks green
  and only comment-level reviews — nothing blocking it.

## Phase 1 — Reliability fixes (do these first, small and concrete)

### 1a. `duplicate_spam`'s per-user cache never shrinks

**File:** `src/bot/handlers/duplicate_spam.py:69` (`_get_recent_messages`)

```python
def _get_recent_messages(context, group_id, user_id) -> deque[RecentMessage]:
    return context.bot_data.setdefault(RECENT_MESSAGES_KEY, {}).setdefault(
        (group_id, user_id), deque()
    )
```

`_prune_old_messages` empties a user's `deque` once their messages age out of
the window, but the outer dict entry for `(group_id, user_id)` is never
removed — it sits there holding an empty deque forever. Every distinct
poster across the bot's uptime adds one permanent entry. For an
active community over weeks/months this is an unbounded, monotonically
growing in-memory structure that's only reclaimed by a process restart.

`bio_bait.py` already solved this exact problem for its own per-user cache
(`USER_BIO_CACHE_MAX_SIZE = 2000` with LRU-style eviction by oldest
timestamp — see `get_cached_user_bio`, `src/bot/handlers/bio_bait.py:278`).
Apply the same pattern here: cap `RECENT_MESSAGES_KEY` and evict the oldest
entries with an empty (or fully-pruned) deque once the cap is hit.

**Verification:** add a test asserting the dict size stops growing past the
cap even as new `(group_id, user_id)` pairs keep appearing — mirror the
existing bio-bait cache-eviction test if one exists (check
`tests/test_bio_bait.py`), otherwise write one fresh in
`tests/test_duplicate_spam.py`.

### 1b. No flood-control (`RetryAfter`) handling on multi-group broadcast loops

**Files:** `src/bot/handlers/check.py:257` (`handle_warn_callback`),
`src/bot/services/scheduler.py`, `src/bot/handlers/dm.py`'s per-group
unrestrict loop, `src/bot/handlers/bio_bait.py`'s alert chunking.

Every one of these loops sends a Telegram API call per monitored group
inside a `try/except Exception`, logs on failure, and moves on. None of them
special-case `telegram.error.RetryAfter` (HTTP 429 / flood control) — an
admin action or scheduled job that fans out across N groups either eats the
`RetryAfter.retry_after` wait as an unhandled generic exception (losing that
group's message) or, if PTB's own retry wrapper isn't in play at that call
site, just fails outright. Fine at today's group counts; becomes a real
"messages silently don't send" bug as the number of monitored groups grows.

**Recommendation:** add one small helper (e.g.
`services/telegram_utils.py::send_with_retry`) that catches `RetryAfter`,
sleeps `retry_after` (capped, e.g. at 30s, to avoid blocking a handler
indefinitely), and retries once — then swap the four call sites above to use
it instead of a bare `context.bot.send_message`/`restrict_chat_member`
inside their existing per-iteration `try/except`.

**Verification:** unit test the helper directly (mock `RetryAfter` raise
then success), plus one existing broadcast test per call site confirming
the new helper is invoked instead of the raw bot method.

## Phase 2 — Housekeeping (near-zero effort, do it now)

### 2a. Merge PR #20

`MERGEABLE`, all 5 CI checks (lint + test × 3.11/3.12/3.13/3.14) green, only
comment-level reviews outstanding (already replied to, per prior session
notes on the `has_link()` and bio-bait-metrics removals). It also carries the
AGENTS.md/README sync and the rebuilt architecture diagram from this
branch's later commits, so merging it is what brings `main`'s docs back in
sync with the actual plugin system (group=0-6 breakdown, `guard_plugin`
mechanics, bio-bait detection) instead of the stale copy `main` has today.

Nothing else in this plan depends on it landing first, but do it early so
future work builds on the post-refactor tree.

## Phase 3 — Complexity / maintainability (real signal, cross-checked by hand)

`tokensave_complexity` + a direct read of each flagged function agree these
five are genuinely doing too much in one function body (Maintainability
Index in the 24–28 range — "hard to maintain" by the tool's own scale):

| Function | File:line | Lines | Cyclomatic | Cognitive | MI |
|---|---|---|---|---|---|
| `handle_bio_bait_spam` | `handlers/bio_bait.py:314` | 127 | 22 | **43** | 27.8 |
| `handle_dm` | `handlers/dm.py:37` | 150 | 15 | 29 | 25.8 |
| `handle_new_user_spam` | `handlers/anti_spam.py:350` | 144 | 14 | 21 | 27.4 |
| `handle_message` | `handlers/message.py:32` | 172 | 13 | 18 | 24.8 |
| `handle_warn_callback` | `handlers/check.py:207` | 85 | 13 | 17 | 33.4 |

All five are 100% test-covered already (per the real coverage report), so
this is a pure refactor-for-readability pass, not a coverage gap. Suggested
split points (from reading each function, not guessed):

- `handle_bio_bait_spam`: extract the "monitor-only vs enforce" branch (the
  delete+restrict+notify tail, ~40 lines) into its own helper — it's the
  single biggest contributor to the cognitive-complexity score (deep nesting
  from the `detection_reason` branch × restrict-success branch × template
  branch cross-product).
- `handle_dm`: extract the "per-restricted-group unrestrict loop" (steps 8–10
  in the flow already documented in `AGENTS.md`) into its own function —
  it's the loop with 4 levels of nesting that Phase 0's complexity report
  flags (`max_nesting: 3`, `loops: 4`).
- `handle_new_user_spam` / `handle_message`: both interleave the "should this
  even apply" guard clauses with the actual state-machine transition logic;
  splitting the guard clauses into one early-return helper each would drop
  cyclomatic complexity without touching behavior.
- `handle_warn_callback`: the callback-data parsing + missing-item text
  building (lines 233–246) is unrelated to the broadcast loop and can move to
  a small pure helper (also makes it independently unit-testable without a
  mocked `Application`).

**Verification:** existing tests for each handler must keep passing
unmodified (behavior-preserving refactor); `tokensave_complexity` (or just
eyeballing the new line/branch counts) should show each split function under
~80 lines / cyclomatic ~8.

## Phase 4 — Observability (net-new, admin-facing)

There is currently no way for an admin to introspect bot state without
server/log access. Recommend one new DM-only admin command, e.g. `/status`:

- Uptime since last restart
- Per-group: captcha/spam plugin toggle summary (from
  `bot_data["plugin_effective_map"]`), active `NewUserProbation` count,
  pending captcha count
- `DatabaseService` file size (cheap `os.path.getsize` on `database_path`)
- Last successful `refresh_admin_ids_job` / `auto_restrict_job` run timestamp
  (would need each job to stamp a timestamp into `bot_data` on success —
  small addition to `services/admin_cache.py` and `services/scheduler.py`)

This directly plugs the gap left by PR #20's metrics-infrastructure removal:
that removal was correct (the old metrics were write-only, no consumer), but
"no consumer" isn't the same as "no one needs this data" — a pull-based
`/status` command is a lighter-weight way to serve the same operational need
without reintroducing a write-only counter nobody reads.

**Verification:** new command follows the existing DM-only + admin-only gate
pattern (`require_admin_dm_target` or the pattern in `handlers/trust.py`);
add a `tests/test_status_command.py` following the fixture conventions in
`AGENTS.md`'s Testing section.

## Phase 5 — Nice-to-haves (low priority, mention only)

- **Dockerfile has no `HEALTHCHECK`.** Low value for a polling bot (no HTTP
  server to probe), but a minimal liveness check — e.g. a script that checks
  the process is still alive and the log file has been written to
  recently — would let container orchestration restart a silently-hung bot
  instead of relying on manual detection.
- **Single SQLite file** is a real ceiling on horizontal scaling (one bot
  process only), but is almost certainly fine at this project's actual scale
  (Indonesian tech community groups) — flagging only so it's a known,
  deliberate tradeoff rather than a surprise if the bot is ever asked to run
  as multiple replicas.

## What was explicitly NOT recommended, and why

- **Re-adding bio-bait metrics** (removed in PR #20) — the removal was
  correct at the time (no consumer existed). Phase 4's `/status` command is
  the better-shaped fix if that operational visibility is wanted again.
- **Renumbering PTB handler groups** to avoid future group-collision bugs
  like the one fixed in PR #21 — the `block=False` fix already closes that
  specific hole with a 2-line diff; a renumbering scheme is speculative
  infrastructure for a problem that's now guarded by a regression test
  (`tests/test_main_plugins_bootstrap.py::test_duplicate_spam_and_bio_bait_spam_share_group_and_filter_shape`).
