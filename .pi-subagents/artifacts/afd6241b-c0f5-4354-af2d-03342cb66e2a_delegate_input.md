# Task for delegate

Branch: `improvement/duplicate-spam-cache-cap` (already created). Worktree cwd: `/tmp/pw-1a`. Do NOT push, do NOT create PR. Just commit on the branch when done.

Goal: cap the unbounded in-memory `RECENT_MESSAGES_KEY` dict in `src/bot/handlers/duplicate_spam.py` — the outer dict (keyed by `(group_id, user_id)`) grows monotonically and is never reclaimed. Mirror the existing bio_bait pattern.

Reference pattern (mirror exactly):
- `src/bot/handlers/bio_bait.py:54-56` defines `USER_BIO_CACHE_KEY`, `USER_BIO_CACHE_TTL_SECONDS`, `USER_BIO_CACHE_MAX_SIZE = 2000`
- `src/bot/handlers/bio_bait.py:226-230` defines `_get_user_bio_cache(context)` returning `context.bot_data.setdefault(KEY, {})`
- `src/bot/handlers/bio_bait.py:296-307` shows the eviction logic:
  ```python
  if len(cache) >= USER_BIO_CACHE_MAX_SIZE:
      sorted_keys = sorted(cache, key=lambda k: cache[k][0])
      for k in sorted_keys[: USER_BIO_CACHE_MAX_SIZE // 2]:
          del cache[k]
  ```

Changes to make in `src/bot/handlers/duplicate_spam.py`:
1. Add module constant `RECENT_MESSAGES_MAX_SIZE = 2000` near line 35 where `RECENT_MESSAGES_KEY` lives.
2. Eviction must run when the outer dict (`context.bot_data[RECENT_MESSAGES_KEY]`) reaches the cap. Since inner entries are deques, you need an eviction timestamp per `(group_id, user_id)` — track when the deque was last touched (i.e. now of last append OR max of timestamps in deque). Simplest: add a small companion dict `_RECENT_LAST_TOUCH_KEY = "duplicate_spam_recent_last_touch"` mapping `(group_id, user_id) -> datetime`, update it in `handle_duplicate_spam` when a new message is appended. Eviction sorts by that timestamp and deletes oldest half when cap hit.
3. Eviction check should happen INSIDE `_get_recent_messages` or in `handle_duplicate_spam` right after `_get_recent_messages` returns — pick one. Recommend doing it in `handle_duplicate_spam` (one call site) to keep `_get_recent_messages` a pure get-or-create helper, matching bio_bait's structure where eviction lives inside `get_cached_user_bio` not in `_get_user_bio_cache`.
4. When evicting outer entries, also delete from the inner last-touch dict for the same keys (keep them in sync). And `del dq` from the outer dict for evicted keys (otherwise the outer dict still holds the empty deques).

Tests in `tests/test_duplicate_spam.py`:
1. New test: appending for N > RECENT_MESSAGES_MAX_SIZE distinct (group_id, user_id) pairs keeps the outer dict size bounded — after eviction, size ≤ RECENT_MESSAGES_MAX_SIZE.
2. New test: after eviction, recently-active (group_id, user_id) pairs (touched after the eviction cut-off) remain in the dict; older ones are gone.

Mirror the existing test fixtures/style in that file (read it first; use the same `mock_context`/`mock_settings`/`temp_db` patterns).

Verification — run all of these from the worktree cwd `/tmp/pw-1a`:
```
uv run pytest tests/test_duplicate_spam.py -v
uv run pytest --cov=bot --cov-report=term-missing
uv run ruff check .
uv run mypy src/bot/ tests/
```
All must pass. Coverage must stay at 99%+ (current 22 missed statements — eviction adds new branches; ensure tests cover them).

Then `git add -A && git commit -m "fix(duplicate_spam): cap in-memory recent-messages dict to prevent unbounded growth"` on the current branch (`improvement/duplicate-spam-cache-cap`). Do NOT push. Report: branch name, files changed, test result, coverage delta, ruff/mypy output.

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