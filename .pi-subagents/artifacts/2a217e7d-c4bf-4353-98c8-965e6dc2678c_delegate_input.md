# Task for delegate

Branch: `improvement/retry-after-helper` (already created). Worktree cwd: `/tmp/pw-1b`. Do NOT push, do NOT create PR. Just commit on the branch when done.

Goal: stop silently dropping messages on Telegram flood-control (`RetryAfter`, HTTP 429). Add ONE small helper in `src/bot/services/telegram_utils.py` and apply it at 4 call sites identified in `plans/01-bot-improvement-recommendations.md`.

Helper spec (add to `src/bot/services/telegram_utils.py`):
- `async def send_message_with_retry(bot, *, chat_id, **kwargs) -> bool` — calls `bot.send_message(...)`, catches `telegram.error.RetryAfter`, sleeps `e.retry_after + 1` seconds, retries once. Returns `True` on success, `False` on any exception (including second `RetryAfter`). Logs the retry at WARNING level.
- `async def restrict_chat_member_with_retry(bot, *, chat_id, user_id, permissions, **kwargs) -> bool` — same shape, wraps `bot.restrict_chat_member`. Returns `True` on success, `False` on any exception.
- Keep error handling narrow: catch `RetryAfter` explicitly for the retry, then let other `telegram.error.TelegramError` subclasses (BadRequest, Forbidden, etc.) bubble up — call sites already wrap those in their own `try/except Exception` for logging. Actually re-reading: the plan says current call sites eat everything as `except Exception`. So the helper should: (a) retry once on `RetryAfter`, (b) re-raise other `TelegramError` so the existing outer `except Exception` still catches and logs them. This preserves current behavior for non-429 errors while fixing the 429 silent-drop.

Imports: add `from telegram.error import RetryAfter` at the top of `telegram_utils.py` (alongside existing `BadRequest, Forbidden`).

Call sites to update:
1. `src/bot/handlers/check.py:257` — `handle_warn_callback`: replace the inner `await context.bot.send_message(...)` with `await send_message_with_retry(context.bot, chat_id=..., text=..., parse_mode=...)`.
2. `src/bot/services/scheduler.py` — wherever it sends Telegram messages per group in the auto-restrict loop. Read the file first; replace each `bot.send_message(...)` and `bot.restrict_chat_member(...)` with the wrappers.
3. `src/bot/handlers/dm.py` — per-group unrestrict loop. Read first; the unrestrict step is `await context.bot.restrict_chat_member(...)` — wrap with `restrict_chat_member_with_retry`. The "send notification message" step (if any) — wrap with `send_message_with_retry`.
4. `src/bot/handlers/bio_bait.py` — alert chunking around `send bio bait monitor alert` (around line 270). Wrap `context.bot.send_message(chat_id=alert_chat_id, text=chunk)` with `send_message_with_retry`.

For each call site: keep the outer `try/except Exception` block intact — the helper's re-raised errors still hit it. But the helper now succeeds on the first retry instead of bubbling up. Document the change with a `ponytail:` comment near the call site: `ponytail: send_message_with_retry handles RetryAfter in place; outer except still catches non-429 errors`.

Tests in `tests/test_telegram_utils.py` (read existing test style first; create if file doesn't exist following the `mock_*` fixture pattern in `tests/test_admin_cache.py`):
1. `test_send_message_with_retry_success_no_retry` — `bot.send_message` returns normally, no sleep, returns True.
2. `test_send_message_with_retry_retries_on_retry_after` — `bot.send_message` raises `RetryAfter(retry_after=2)` once then succeeds; `asyncio.sleep(3)` called once; returns True.
3. `test_send_message_with_retry_gives_up_after_second_retry_after` — `RetryAfter` raised twice; returns False.
4. `test_send_message_with_retry_propagates_other_telegram_error` — `bot.send_message` raises `BadRequest`; helper re-raises (caller's `except Exception` catches it).
5. `test_restrict_chat_member_with_retry_*` — same matrix for the restrict variant.

Mock `asyncio.sleep` so tests don't actually wait. Use `AsyncMock` for `bot.send_message`/`bot.restrict_chat_member`. Import `RetryAfter` from `telegram.error`.

Verification — run from `/tmp/pw-1b`:
```
uv run pytest tests/test_telegram_utils.py tests/test_check.py tests/test_dm.py tests/test_scheduler.py -v
uv run pytest --cov=bot --cov-report=term-missing
uv run ruff check .
uv run mypy src/bot/ tests/
```
All must pass. Coverage 99%+.

Then commit on `improvement/retry-after-helper`. Do NOT push. Report: branch, files changed, test result, coverage delta.

## Acceptance Contract
Acceptance level: reviewed
Completion is not accepted from prose alone. End with a structured acceptance report.

Criteria:
- criterion-1: Implement the requested change without widening scope
- criterion-2: Return evidence sufficient for an independent acceptance review

Required evidence: changed-files, tests-added, commands-run, validation-output, residual-risks, no-staged-files

Review gate: required by reviewer.

Finish with a fenced JSON block tagged `acceptance-report` in this shape:
Use empty arrays when no items apply; array fields contain strings unless object entries are shown.
```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "specific proof"
    }
  ],
  "changedFiles": [
    "src/file.ts"
  ],
  "testsAddedOrUpdated": [
    "test/file.test.ts"
  ],
  "commandsRun": [
    {
      "command": "command",
      "result": "passed",
      "summary": "short result"
    }
  ],
  "validationOutput": [
    "validation output or concise summary"
  ],
  "residualRisks": [
    "none"
  ],
  "noStagedFiles": true,
  "diffSummary": "short description of the diff",
  "reviewFindings": [
    "blocker: file.ts:12 - issue found, or no blockers"
  ],
  "manualNotes": "anything else the parent should know"
}
```