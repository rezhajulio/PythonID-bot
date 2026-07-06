# Task for delegate

Branch: `improvement/status-command` (already created). Worktree cwd: `/tmp/pw-4`. Do NOT push, do NOT create PR. Just commit on the branch when done.

Goal: add a DM-only, admin-only `/status` command that shows bot operational state. Per `plans/01-bot-improvement-recommendations.md` Phase 4. Mirror existing DM-admin-command patterns.

Reference patterns to follow (read first):
- `src/bot/handlers/trust.py` — has `/trust`, `/untrust`, `/trusted` DM-admin commands. Look at how `require_admin_dm_target` is called (from `src/bot/services/telegram_utils.py:280+`). And look at how `get_handlers()` is defined at the bottom of trust.py for registration.
- `src/bot/plugins/builtin/commands.py` — wraps admin command plugins. Read it to understand how to register a new DM-only command.
- `src/bot/plugins/definitions.py` — `MANIFEST_ORDER` list. Add your new plugin name there at the right position (alphabetical within group=0; between existing admin commands).
- `src/bot/plugins/manager.py` — `_REGISTRY` dict. Add your plugin's registrar function there.

Steps:

1. **`src/bot/handlers/status.py`** (new file). Define:
   - `async def handle_status(update, context) -> None` — the command handler.
   - It calls `require_admin_dm_target(update, context, usage_message="/status", command_label="/status command")` (returns None after sending error message on any check failure). But note: `/status` takes NO user-id arg, so adapt: write your own thin guard `await _check_status_prereqs(update, context)` that does just the first 3 checks (message exists, chat is private, caller is admin) — DON'T use `require_admin_dm_target` because that requires args. Copy its structure but skip the args check.
   - On success, build the status text with these sections:
     - **Uptime**: `time.monotonic() - bot_data["start_time"]`. Format as `Xd Yh Zm`. Store `start_time` in `bot_data` during the post_init flow (you'll add that step).
     - **Per-group summary**: iterate `get_group_registry().all_configs()`. For each group: group title (from `bot_data["group_titles"][group_id]` if cached else group_id), captcha enabled (from `group_config.captcha_enabled`), effective plugin toggles (from `bot_data["plugin_effective_map"][group_id]`). Format as a compact list.
     - **Probation**: `get_database().session.exec(select(NewUserProbation)).all()` length.
     - **Pending captcha**: `len(get_database().get_all_pending_captchas())`.
     - **DB size**: `os.path.getsize(database_path)` formatted as KB/MB. `database_path` is on `Settings` (`src/bot/config.py`).
     - **Last jobs**: `bot_data["last_admin_refresh"]` and `bot_data["last_auto_restrict"]` formatted as `time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(ts))` or "never" if missing.
   - Use a single `send_message` (or `reply_text`) with the whole status block. Use markdown formatting. Add section headers in bold (escape names via `escape_markdown` if needed).
   - Define `def get_handlers() -> list` returning `[CommandHandler("status", handle_status)]`.
   - Add module docstring.

2. **`src/bot/plugins/builtin/status.py`** (new file). Mirror `src/bot/plugins/builtin/captcha.py`:
   ```python
   """Built-in plugin: status.
   Wraps bot.handlers.status for the /status DM-admin command.
   """
   from __future__ import annotations
   import copy
   import logging
   from typing import TYPE_CHECKING
   from bot.handlers import status
   # NOTE: /status is admin-only, NOT gated per-group. Do NOT wrap with guard_plugin.
   if TYPE_CHECKING:
       from telegram.ext import Application, BaseHandler
   logger = logging.getLogger(__name__)
   def register_status(application: Application) -> list[BaseHandler]:
       handlers = status.get_handlers()
       registered = []
       for h in handlers:
           cloned = copy.copy(h)
           # No guard_plugin wrap — /status is admin-gated by require_admin_dm_target-style checks
           application.add_handler(cloned)
           registered.append(cloned)
       logger.info("Registered handler: status (group=0)")
       return registered
   ```

3. **`src/bot/plugins/definitions.py`**: add `"status"` to `MANIFEST_ORDER` (alphabetical in group=0 — find existing `commands`/`trust` group-0 entries and slot it between them).

4. **`src/bot/plugins/manager.py`**: in `_REGISTRY` (or whatever dict maps name → registrar), add `"status": register_status`. Read the file first to find the exact dict name and structure.

5. **`src/bot/services/admin_cache.py`** + **`src/bot/services/scheduler.py`**: at the END of `refresh_admin_ids` and `auto_restrict_expired_warnings` (after successful iteration), stamp `context.bot_data["last_admin_refresh"] = time.time()` / `last_auto_restrict` respectively. Only stamp on success (not on partial failure). Wrap each in try/except so a stamping failure doesn't mask the real result.

6. **`src/bot/main.py`** (the post_init section): add `application.bot_data["start_time"] = time.monotonic()`. Read `main.py` first to find the right spot (likely inside `post_init` after the existing setup, before `PluginManager.register_all()`).

Tests in `tests/test_status_command.py` (new file, follow fixture pattern from `tests/test_trust.py` or `tests/test_admin_cache.py`):
1. `test_handle_status_non_private_chat_rejected` — chat type=group, handler replies with "DM-only" error.
2. `test_handle_status_non_admin_rejected` — private chat but caller not in admin_ids, handler replies with "no permission" error.
3. `test_handle_status_admin_success` — private chat, caller in admin_ids, bot_data has start_time, plugin_effective_map for one group, no captcha/probation. Handler sends a single reply containing "Uptime", "Group", "Probation", "Captcha", "Database", "Last jobs".
4. `test_handle_status_shows_pending_captcha_count` — add 2 pending captchas via `temp_db`, handler reply contains "Captcha: 2" (or similar substring).
5. `test_handle_status_shows_last_job_timestamps` — set `bot_data["last_admin_refresh"] = time.time() - 60`, handler reply contains formatted timestamp.

Use `mock_update`, `mock_context`, `temp_db` fixtures copied from existing tests in the same style. Don't create `conftest.py`.

Verification — run from `/tmp/pw-4`:
```
uv run pytest tests/test_status_command.py tests/test_main_plugins_bootstrap.py -v
uv run pytest --cov=bot --cov-report=term-missing
uv run ruff check .
uv run mypy src/bot/ tests/
```
All must pass. Coverage 99%+.

Then commit on `improvement/status-command`. Do NOT push. Report: branch, files changed (5-6 files expected), test result, coverage delta.

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