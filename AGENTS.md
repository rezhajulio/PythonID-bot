# AGENTS.md - PythonID Telegram Bot

## Overview

Indonesian Telegram bot for multi-group profile enforcement (photo + username), captcha verification, and anti-spam protection. Built with python-telegram-bot v20+, SQLModel, Pydantic, and Logfire.

## Commands

```bash
# Install dependencies (including dev)
uv sync --dev

# Run tests (100% coverage maintained)
uv run pytest

# Run single test file
uv run pytest tests/test_check.py

# Run single test function
uv run pytest tests/test_check.py::TestHandleCheckCommand::test_check_command_non_admin

# Run only property-based tests
uv run pytest tests/test_properties.py -v

# Run with coverage
uv run pytest --cov=bot --cov-report=term-missing

# Run linter
uv run ruff check .

# Run type checker
uv run mypy src/bot/ tests/

# Run the bot
uv run pythonid-bot

# Run staging
BOT_ENV=staging uv run pythonid-bot
```

## Structure

```
PythonID/
├── src/bot/
│   ├── main.py           # Entry point + handler registration (priority groups!)
│   ├── config.py         # Pydantic settings (get_settings() cached)
│   ├── constants.py      # Indonesian templates + URL whitelists (739 lines)
│   ├── group_config.py   # Multi-group config (GroupConfig, GroupRegistry)
│   ├── plugins/          # Modular plugin system (wraps handlers)
│   │   ├── manager.py          # PluginManager — discovers + registers built-ins
│   │   ├── definitions.py      # Plugin class contract
│   │   ├── config.py           # guard_plugin("name") per-group runtime gate
│   │   └── builtin/            # Built-in plugins (one per handler domain)
│   │       ├── captcha.py
│   │       ├── profile_monitor.py
│   │       ├── spam.py
│   │       ├── topic_guard.py
│   │       ├── commands.py
│   │       ├── dm.py
│   │       └── jobs.py
│   ├── handlers/         # Underlying handler implementations (wrapped by plugins)
│   │   ├── captcha.py    # New member verification + profile check
│   │   ├── verify.py     # Admin /verify, /unverify commands
│   │   ├── check.py      # Admin /check command + forwarded message handling
│   │   ├── anti_spam.py  # Anti-spam (contact cards, inline keyboards, probation)
│   │   ├── message.py    # Profile compliance monitoring
│   │   ├── dm.py         # DM unrestriction flow
│   │   ├── topic_guard.py # Warning topic protection (group=-1)
│   │   ├── trust.py      # /trust, /untrust, /trusted admin commands
│   │   ├── warn.py       # Admin /warn command (reply or user ID)
│   │   ├── duplicate_spam.py # Duplicate message detection
│   │   └── bio_bait.py   # Bio-bait spam (bait phrases + suspicious profile bio links)
│   ├── services/
│   │   ├── user_checker.py      # Profile validation (photo + username)
│   │   ├── scheduler.py         # JobQueue auto-restriction (every 5 min)
│   │   ├── telegram_utils.py    # Shared API helpers
│   │   ├── bot_info.py          # Bot metadata cache (singleton)
│   │   ├── captcha_recovery.py  # Restart recovery for pending captchas
│   │   └── admin_cache.py       # Admin ID cache + refresh
│   └── database/
│       ├── models.py     # SQLModel schemas (5 tables: UserWarning, PhotoVerificationWhitelist, PendingCaptchaValidation, NewUserProbation, TrustedUser)
│       └── service.py    # DatabaseService singleton (645 lines)
├── tests/                # pytest-asyncio + Hypothesis (30+ files)
│   ├── test_properties.py # Property-based tests for pure functions
│   └── test_warn.py      # /warn command tests (23 tests)
├── scripts/
│   └── backfill_trusted_names.py  # One-shot backfill for trusted user names
└── data/bot.db           # SQLite (auto-created, WAL mode)
```

## Where to Look

| Task | Location | Notes |
|------|----------|-------|
| Add new handler | `plugins/definitions.py` + `plugins/builtin/X.py` | Add to `MANIFEST_ORDER` with a `handler_group` (-1, 0-6); handlers register via `PluginManager`, not directly in `main.py` |
| Modify messages | `constants.py` | All Indonesian templates centralized |
| Add DB table | `database/models.py` → `database/service.py` | Add model, then service methods |
| Change config | `config.py` | Pydantic BaseSettings with env vars |
| Add URL whitelist | `constants.py` → `WHITELISTED_URL_DOMAINS` | Suffix-based matching |
| Add Telegram whitelist | `constants.py` → `WHITELISTED_TELEGRAM_PATHS` | Lowercase, exact path match |
| Multi-group config | `group_config.py` | GroupConfig model, GroupRegistry, groups.json loading |
| Warn a member | `handlers/warn.py` + `plugins/builtin/commands.py` | Admin `/warn` by reply or user ID; registered as `warn_command` |

## Code Map (Key Files)

| File | Lines | Role |
|------|-------|------|
| `database/service.py` | 850 | **Complexity hotspot** - handles warnings, captcha, probation state |
| `constants.py` | 724 | Templates + massive whitelists (Indonesian tech community) |
| `handlers/anti_spam.py` | 494 | Anti-spam: contact cards, inline keyboards, probation enforcement |
| `handlers/bio_bait.py` | 441 | Bio-bait spam: obfuscated bait phrases + suspicious profile bio links |
| `handlers/check.py` | 437 | Admin /check: group selector + group-scoped action buttons |
| `handlers/captcha.py` | 427 | New member join → restrict → verify (with profile check) → unrestrict lifecycle |
| `handlers/verify.py` | 400 | Photo exemption + bot-owned unrestriction (group-scoped) |
| `handlers/trust.py` | 368 | /trust, /untrust, /trusted admin commands (no auto-unrestrict) |
| `handlers/dm.py` | 250 | DM unrestriction flow with deep-link group recovery |
| `handlers/message.py` | 208 | Profile compliance monitoring + stale warning clearing |
| `handlers/status.py` | 181 | Group-scoped /status (admin's groups only, Indonesian labels) |
| `handlers/warn.py` | 170 | Admin-issued generic warning by reply or user ID; optional moderation-topic routing |
| `services/scheduler.py` | 151 | Auto-restriction with pre-restriction profile recheck |
| `group_config.py` | 255 | Multi-group config, registry, JSON loading, .env fallback |
| `main.py` | 191 | Entry point, logging, post_init, PluginManager bootstrap |
| `plugins/manager.py` | 188 | PluginManager — static registry + deterministic registration order |
| `plugins/config.py` | 156 | `guard_plugin` runtime gate + toggle resolution |
| `plugins/definitions.py` | 72 | `MANIFEST_ORDER` / `PLUGIN_NAMES` — single source of truth for plugin names + groups |
| `plugins/builtin/commands.py` | 166 | Wraps all command + callback handlers with group-scoped patterns |
| `plugins/builtin/spam.py` | 93 | Wraps all 5 anti-spam handlers with `guard_plugin` |
| `plugins/builtin/captcha.py` | 43 | Wraps captcha handler + applies guard_plugin gating |

## Architecture Patterns

### Modular Plugin System
- Built-in plugins live in `src/bot/plugins/builtin/`, one per handler domain (captcha, spam, topic_guard, profile_monitor, commands, dm, jobs)
- `plugins/definitions.py` holds `MANIFEST_ORDER` — a static, hand-maintained tuple of 27 plugin names (topic_guard first, job plugins last) that is the single source of truth for registration order and for the group number each plugin runs in
- `PluginManager.register_all()` (called from `main.py:main`, not `post_init`) walks `MANIFEST_ORDER` against a static `_REGISTRY` dict (name → registrar function) and stores results in `application.bot_data["plugin_handlers"]`
- The plugin wrapper pattern: `bot.plugins.builtin.X` imports from `bot.handlers.X`, clones the handler list, and applies `guard_plugin("X")` for per-group runtime gating
- To add a new plugin: add a `register_*(application) -> list[BaseHandler]` function in `builtin/`, add its name + group to `_PLUGIN_DEFINITIONS` in `definitions.py`, wire it into `_REGISTRY` in `manager.py`
- Handler modules stay decoupled from plugin internals — changes to `bot/handlers/X.py` flow through transparently
- **Callback data format**: All admin action callbacks encode `group_id` for per-group authorization: `action:{group_id}:{user_id}[:missing_code]`. The captcha callback uses `captcha_verify_{group_id}_{user_id}`. Callback handlers verify the caller is an admin of the specific group via `is_user_admin_in_group()`
- **Trust does not unrestrict**: Adding a user to the trusted list only clears probation — it does NOT lift restrictions. Use the separate "Buka pembatasan bot" (unrestrict) action to lift bot-applied restrictions. This prevents trust from inadvertently lifting manual admin restrictions
- **Admin cache excludes bots**: `fetch_group_admin_ids` passes `return_bots=False` to the Telegram API and filters `is_bot` client-side, so automated admin-bots are not treated as human admins

### Handler Priority Groups
```python
# Registration order comes from MANIFEST_ORDER (plugins/definitions.py), not main.py directly
group=-1  # topic_guard: Runs FIRST
group=0   # commands (including warn_command), callbacks, captcha, dm (18 plugins, order-independent)
group=1   # inline_keyboard_spam: Catches inline keyboard URL spam
group=2   # contact_spam: Blocks contact card sharing
group=3   # new_user_spam: Probation enforcement (links/forwards)
group=4   # duplicate_spam + bio_bait_spam: Repeated messages / bio-bait detection
group=5   # profile_monitor: Runs LAST, profile compliance check
group=6   # JobQueue only (not a handler group): auto_restrict_job, refresh_admin_ids_job
```

### Plugin Gating (`guard_plugin`)
- `guard_plugin("name")` (`plugins/config.py`) wraps a handler callback; on each update it looks up `context.bot_data["plugin_effective_map"][group_id]["name"]` and no-ops the callback if disabled
- Only gates **group/supergroup** chats — private and channel updates always pass through unchanged
- Fail-open by design: unknown group, missing plugin key, or missing effective map all resolve to enabled
- Per-group toggle resolution (`resolve_plugin_toggles`), first match wins: (1) `GroupConfig.plugins` override in groups.json, (2) `Settings.plugins_default` (`PLUGINS_DEFAULT` env, JSON object), (3) `True`
- `PluginManager.compute_effective_map()` runs once at startup (after `register_all`) and caches the resolved per-group map in `bot_data["plugin_effective_map"]` — it is not recomputed per-update
- There is no bypass mechanism for admin commands beyond simply not wrapping them in `guard_plugin`

### Captcha Profile Check
- New members must have a public profile photo AND username before captcha verification completes
- `check_user_profile()` in `services/user_checker.py` queries both via Bot API
- Profile-incomplete path: alert shown, captcha record preserved, timeout still armed, user can fix profile and retry
- Telegram `unrestrict_user` runs **before** DB finalization (remove_pending_captcha + start_new_user_probation) — if unrestrict fails, the pending captcha stays in DB and the user can retry by pressing the button again

### Bio Bait Detection
- `handlers/bio_bait.py` catches two vectors: (1) a bait phrase in the message itself ("cek bio aku"), (2) the sender's Telegram **profile bio** containing a promo/invite link — bio is fetched via `get_chat` and cached per-user for 1 hour (5 min on fetch failure) to avoid hammering the API
- Bait-phrase matching normalizes obfuscation first: NFKC + lowercase, strips zero-width characters, canonicalizes obfuscated "bio"/"byo" spellings (leetspeak, separators, Cyrillic look-alikes) before running the bait regexes
- `bio_bait_monitor_only` (per-group) skips delete/restrict and only logs + optionally alerts `bio_bait_alert_chat_id` — use this to tune detection before enforcing
- Admins and trusted users are exempt (`is_user_admin_or_trusted`)

### Topic Guard Design
- Handles both `message` and `edited_message` updates (combined filter)
- Raises `ApplicationHandlerStop` after handling ANY warning-topic message (allows or deletes)
- This prevents downstream spam/profile handlers from processing warning-topic traffic
- **Fail-closed**: On `get_chat_member` API error, deletes the message (scoped to confirmed warning-topic only)
- Early returns (no message, wrong group, wrong topic) happen OUTSIDE the try/except block

### Singletons
- `get_settings()` — Pydantic settings, `@lru_cache`
- `get_database()` — DatabaseService, lazy init
- `BotInfoCache` — Class-level cache for bot username/ID

### Admin Cache
- `post_init()` order: `preload_admin_ids()` (fail-soft per group) → load all `TrustedUser` IDs into `bot_data["trusted_user_ids"]` → conditionally `recover_pending_captchas()` if any group has `captcha_enabled`
- Admin IDs stored in `bot_data["group_admin_ids"]` (per-group) and `bot_data["admin_ids"]` (union)
- Refreshed every 10 minutes via `refresh_admin_ids_job` JobQueue job
- On refresh failure for a group, falls back to existing cached data (not empty list)
- Spam handlers use cached admin IDs; topic_guard uses live `get_chat_member` API call
- Handler + JobQueue registration (`PluginManager.register_all()`) and effective-plugin-map computation happen later, in `main()` after `post_init` is wired up but before `run_polling` — not inside `post_init` itself

### Multi-Group Support
- `GroupConfig` — Pydantic model with 21 per-group settings: warning thresholds, captcha, probation, contact/duplicate/bio-bait spam tuning, `rules_link`, optional `moderation_topic_id`, and a `plugins: dict[str, bool] | None` override
- `GroupRegistry` — O(1) lookup by group_id, manages all monitored groups
- `groups.json` — Per-group config file; falls back to `.env` for single-group mode (missing fields default from `GroupConfig.model_fields`)
- `get_group_config_for_update()` — Helper to resolve config for incoming Telegram updates
- Exception-isolated loops — Per-group API calls wrapped in try/except to prevent cross-group failures

### State Machine (Progressive Restriction)
```
1st violation → Warning with threshold info
2nd to (N-1) → Silent increment (no spam)
Nth violation → Restrict + notification
Time threshold → Auto-restrict via scheduler (parallel path)
```

### Database Conventions
- SQLite with **WAL mode + `synchronous=NORMAL`** for write concurrency under a single-process bot
- `session.exec(select(Model).where(...)).first()` syntax
- Atomic updates for violation counts via raw `UPDATE ... SET x = x + 1` (prevents read-modify-write races)
- No Alembic — use `SQLModel.metadata.create_all` + `_migrate_trusted_users` (`ALTER TABLE`) for column adds
- Registers a datetime SQLite adapter to isoformat strings (avoids the Python 3.12+ default-adapter deprecation)
- New tables: `TrustedUser` (5th table) for the /trust admin bypass feature — `group_id` defaults to `0` (global scope); per-group trust is modeled in the schema but not currently exercised anywhere

## Code Style

- **Python 3.11+** with type hints
- **Imports**: stdlib → third-party → local
- **Async/await**: All handlers are async
- **PTB v20+**: Use `ContextTypes.DEFAULT_TYPE`, not legacy Dispatcher
- **Logging**: Use `logfire` via stdlib `logging.getLogger(__name__)`
- **Error handling**: Catch specific exceptions (`TimedOut`), log, return gracefully
- **No inline comments** unless code is complex
- **Docstrings**: Module-level required; function docstrings for public APIs

## Testing

- **Async mode**: `asyncio_mode = auto` — do NOT use `@pytest.mark.asyncio` decorators
- **No conftest.py**: Fixtures defined locally in each test file (intentional isolation)
- **Fixtures**: `mock_update`, `mock_context`, `mock_settings` — copy from existing tests
- **Database tests**: Use `temp_db` fixture with `tempfile.TemporaryDirectory`
- **Mocking**: `AsyncMock` for Telegram API; no real network calls
- **Property-based tests**: `tests/test_properties.py` uses Hypothesis for pure functions (format helpers, URL whitelist, `_format_person`). 200 examples per test by default. New pure functions SHOULD have property tests
- **Coverage**: 99% maintained (~970 tests) — check before committing
- **Test delta tracking**: When a fix changes a function signature, update existing tests AND add a new round-trip test that asserts the actual values, not substring matches

## Anti-Patterns (THIS PROJECT)

| Forbidden | Why |
|-----------|-----|
| `@pytest.mark.asyncio` decorator | `asyncio_mode = auto` handles this |
| Manual `conftest.py` fixtures | Project uses local fixture pattern |
| Raw SQL in handlers | Use `DatabaseService` methods |
| Hardcoded Indonesian text | Use `constants.py` templates |
| `print()` statements | Use `logging.getLogger(__name__)` |
| Empty `except:` blocks | Catch specific exceptions, log with `exc_info=True` |

## Unique Conventions

### Indonesian Localization
- All user-facing messages in `constants.py`
- Time formatting: `format_threshold_display(minutes)` → "3 jam" or "30 menit"
- Duration formatting: `format_hours_display(hours)` → "7 hari" or "12 jam"

### Admin Authorization
```python
admin_ids = context.bot_data.get("admin_ids", [])
if user.id not in admin_ids:
    return  # or send "Admin only" message
```

### URL Whitelisting (Anti-spam)
- Suffix-based hostname matching in `is_url_whitelisted()`
- `WHITELISTED_URL_DOMAINS` — tech/docs domains (github.com, docs.python.org, etc.)
- `WHITELISTED_TELEGRAM_PATHS` — Indonesian tech communities (lowercase)

### Restart Recovery
- Pending captchas persisted to DB, recovered in `post_init()`
- JobQueue timeouts re-scheduled on bot startup

## CI/CD

- **GitHub Actions**: `.github/workflows/python-checks.yml`
- **Matrix**: Python 3.11, 3.12, 3.13, 3.14
- **Steps**: ruff → mypy → pytest (lint job always; test job runs when Python files changed)
- **Mypy config**: Pragmatic, in `pyproject.toml [tool.mypy]`. Disables noisy error codes from PTB / SQLModel / Pydantic v2 (`arg-type`, `attr-defined`, `index`, `union-attr`, `misc`, `return-value`, `call-arg`). New code should remain free of these errors
- **Docker**: Multi-stage build with `uv`, non-root user, 512MB limit

## Where to Look (Plugin System)

| Task | Location |
|------|----------|
| Add a new built-in plugin | `src/bot/plugins/builtin/X.py` (class with `name` + `register(application)`) |
| Register an existing handler as a plugin | Wrap `bot.handlers.X.get_handlers()` in `bot/plugins/builtin/X.py` |
| Add per-group runtime gating | `guard_plugin("X")` decorator in `src/bot/plugins/config.py` |
| Disable a plugin for one group | Set `plugins: {"name": false}` in that group's entry in groups.json (`GroupConfig.plugins`) |
| Set a bot-wide plugin default | `PLUGINS_DEFAULT` env var (JSON object, `Settings.plugins_default`) |
| Exempt a handler from gating entirely | Don't wrap it in `guard_plugin(...)` (this is how admin commands stay ungated) |

## Notes

- Registration order for all 27 built-in plugins lives in `MANIFEST_ORDER` (`plugins/definitions.py`), not scattered across `main.py`
- `duplicate_spam` and `bio_bait_spam` both run at `group=4`; `auto_restrict_job` / `refresh_admin_ids_job` run as JobQueue jobs tagged `group=6` (not a PTB handler group)
- Topic guard runs at `group=-1` to intercept unauthorized messages BEFORE other handlers
- Topic guard handles both messages and edited messages, raises `ApplicationHandlerStop` to block downstream handlers
- JobQueue auto-restriction job runs every 5 minutes (first run after 5 min delay)
- JobQueue admin refresh job runs every 10 minutes (first run after 10 min delay)
- Bot uses `allowed_updates=["message", "edited_message", "callback_query", "chat_member"]`
- Captcha uses both `ChatMemberHandler` (for "Hide Join" groups) and `MessageHandler` fallback
- Multi-group: handlers use `get_group_config_for_update()` instead of `settings.group_id`
- Captcha callback data encodes group_id: `captcha_verify_{group_id}_{user_id}` to avoid ambiguity
- Scheduler iterates all groups with per-group exception isolation
- DM handler scans all groups in registry for user membership and unrestriction
- **Warn command**: A per-group admin can reply with `/warn [reason]` or use `/warn USER_ID [reason]`. The command is deleted before network lookups to protect the admin's identity; non-admins, bots, and self-targets are silently ignored. ID mode verifies membership with `get_chat_member`, reasons are Markdown-escaped, and the warning is sent to `moderation_topic_id` when configured or the main group otherwise. `moderation_topic_id` is distinct from `warning_topic_id`, which is used for bot logging. This command creates no DB record and is not gated by `guard_plugin`
- **Trust feature**: `TrustedUser` table caches user_full_name + admin_full_name at trust time so `/trusted` lists admin info without Telegram API calls. Backfill script at `scripts/backfill_trusted_names.py` for pre-existing rows
- **Local review artifacts**: `reviews/` directory contains output from parallel reviewer subagents. Gitignored; not part of the source tree
- **Captcha DB ordering**: The captcha callback handler calls Telegram `unrestrict_user` BEFORE DB writes (remove_pending_captcha, start_new_user_probation). If unrestrict fails, the pending captcha stays in DB and the user can retry. DB finalization is idempotent — `remove_pending_captcha` returning False means a concurrent callback already finalized

## Policy

- Never mention AI usage, code generation tools, or automated assistance in commit messages, PR descriptions, code comments, or documentation
