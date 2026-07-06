# Task for delegate

Branch: `improvement/refactor-complex-handlers` (already created). Worktree cwd: `/tmp/pw-3`. Do NOT push, do NOT create PR. Just commit on the branch when done.

Goal: pure readability refactor of 5 complex handlers from `plans/01-bot-improvement-recommendations.md` Phase 3. Behavior-preserving — every existing test must pass UNMODIFIED. No coverage loss.

Files + functions to split (read each first to understand structure):
1. `src/bot/handlers/bio_bait.py` — `handle_bio_bait_spam` at line 315. Extract the "monitor-only vs enforce" delete+restrict+notify tail (the ~40 lines after the detection_reason branch crosses the restrict-success branch and template branch cross-product) into `_enforce_bio_bait_restriction(...)`. Leave detection logic + monitoring-vs-enforcing decision in the parent function. Keep `ApplicationHandlerStop` raise in the parent.
2. `src/bot/handlers/dm.py` — `handle_dm` at line 38. Extract the per-restricted-group unrestrict loop into `_unrestrict_in_groups(context, user_id, group_ids) -> int` (returns success count). This helper is independently unit-testable without a mocked `Application`. The parent just resolves group IDs and calls this.
3. `src/bot/handlers/anti_spam.py` — `handle_new_user_spam` at line 351. Look for repeated guard-clause boilerplate (admin checks, is_bot checks, profile-only-fresh check, etc.) — extract a `_should_skip_new_user_spam_check(update, context, group_config) -> bool` predicate that returns True if the message should be skipped. Apply it at the top of the parent. Keep detection logic intact.
4. `src/bot/handlers/message.py` — `handle_message` at line 33. Same pattern: extract `_should_skip_profile_check(update, context, group_config) -> bool` predicate for early returns. Parent does early-return then continues with profile logic.
5. `src/bot/handlers/check.py` — `handle_warn_callback` at line 208. Extract the callback-data parsing (`captcha_verify_{group_id}_{user_id}` etc.) into `_parse_warn_callback_data(data: str) -> tuple[int, int] | None` returning `(group_id, user_id)` or None. Apply it at the top of the parent. The parent calls the parser and early-returns None on parse failure.

Rules:
- Each new helper must be `async` if and only if it does I/O. `_should_skip_*` predicates are sync (they just inspect update/context). `_enforce_*` and `_unrestrict_in_groups` are async.
- New helpers stay in the same file as the parent (don't create new modules).
- Don't add new imports.
- Don't change function signatures of public handler functions (`handle_*`).
- Don't rename anything.
- Don't add new logging — preserve existing log messages exactly.
- Each split function: target ≤ 80 lines, ≤ 8 cyclomatic complexity.

Verification — run from `/tmp/pw-3`:
```
uv run pytest -v
uv run pytest --cov=bot --cov-report=term-missing
uv run ruff check .
uv run mypy src/bot/ tests/
```
- All 947 tests pass.
- Coverage 99%+ (currently 22 missed stmts; refactor doesn't change that).
- Ruff + mypy clean.

Then commit on `improvement/refactor-complex-handlers`. Do NOT push. Report: branch, files changed (5 files expected), line counts before/after for each parent function, test result, coverage delta.

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