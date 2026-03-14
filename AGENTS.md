# AGENTS.md - PythonID Telegram Bot

## Overview

Indonesian Telegram bot for multi-group profile enforcement (photo + username), captcha verification, and anti-spam protection. Built with python-telegram-bot v20+, SQLModel, Pydantic, and Logfire.

## Commands

```bash
# Install dependencies
uv sync

# Run tests (100% coverage maintained)
uv run pytest

# Run single test file
uv run pytest tests/test_check.py

# Run single test function
uv run pytest tests/test_check.py::TestHandleCheckCommand::test_check_command_non_admin

# Run with coverage
uv run pytest --cov=bot --cov-report=term-missing

# Run linter
uv run ruff check .

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
│   ├── constants.py      # Indonesian templates + URL whitelists (528 lines)
│   ├── group_config.py   # Multi-group config (GroupConfig, GroupRegistry)
│   ├── handlers/         # Telegram update handlers
│   │   ├── captcha.py    # New member verification flow
│   │   ├── verify.py     # Admin /verify, /unverify commands
│   │   ├── check.py      # Admin /check command + forwarded message handling
│   │   ├── anti_spam.py  # Anti-spam (contact cards, inline keyboards, probation)
│   │   ├── message.py    # Profile compliance monitoring
│   │   ├── dm.py         # DM unrestriction flow
│   │   └── topic_guard.py # Warning topic protection (group=-1)
│   ├── services/
│   │   ├── user_checker.py      # Profile validation (photo + username)
│   │   ├── scheduler.py         # JobQueue auto-restriction (every 5 min)
│   │   ├── telegram_utils.py    # Shared API helpers
│   │   ├── bot_info.py          # Bot metadata cache (singleton)
│   │   └── captcha_recovery.py  # Restart recovery for pending captchas
│   └── database/
│       ├── models.py     # SQLModel schemas (4 tables)
│       └── service.py    # DatabaseService singleton (645 lines)
├── tests/                # pytest-asyncio (19 files, 99.9% coverage)
└── data/bot.db           # SQLite (auto-created, WAL mode)
```

## Where to Look

| Task | Location | Notes |
|------|----------|-------|
| Add new handler | `main.py` | Register with appropriate group (-1, 0, 1-5) |
| Modify messages | `constants.py` | All Indonesian templates centralized |
| Add DB table | `database/models.py` → `database/service.py` | Add model, then service methods |
| Change config | `config.py` | Pydantic BaseSettings with env vars |
| Add URL whitelist | `constants.py` → `WHITELISTED_URL_DOMAINS` | Suffix-based matching |
| Add Telegram whitelist | `constants.py` → `WHITELISTED_TELEGRAM_PATHS` | Lowercase, exact path match |
| Multi-group config | `group_config.py` | GroupConfig model, GroupRegistry, groups.json loading |

## Code Map (Key Files)

| File | Lines | Role |
|------|-------|------|
| `group_config.py` | 250 | Multi-group config, registry, JSON loading, .env fallback |
| `database/service.py` | 671 | **Complexity hotspot** - handles warnings, captcha, probation state |
| `constants.py` | 530 | Templates + massive whitelists (Indonesian tech community) |
| `handlers/captcha.py` | 375 | New member join → restrict → verify → unrestrict lifecycle |
| `handlers/verify.py` | 358 | Admin verification commands + inline button callbacks |
| `handlers/anti_spam.py` | 420 | Anti-spam: contact cards, inline keyboards, probation enforcement |
| `main.py` | 315 | Entry point, logging, handler registration, JobQueue setup |

## Architecture Patterns

### Handler Priority Groups
```python
# main.py - Order matters!
group=-1  # topic_guard: Runs FIRST
group=0   # Commands, DM, captcha
group=1   # inline_keyboard_spam: Catches inline keyboard URL spam
group=2   # contact_spam: Blocks contact card sharing
group=3   # new_user_spam: Probation enforcement (links/forwards)
group=4   # duplicate_spam: Repeated message detection
group=5   # message_handler: Runs LAST, profile compliance check
```

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
- Fetched at startup in `post_init()` and stored in `bot_data["group_admin_ids"]` (per-group) and `bot_data["admin_ids"]` (union)
- Refreshed every 10 minutes via `refresh_admin_ids` JobQueue job
- On refresh failure for a group, falls back to existing cached data (not empty list)
- Spam handlers use cached admin IDs; topic_guard uses live `get_chat_member` API call

### Multi-Group Support
- `GroupConfig` — Pydantic model for per-group settings (warning thresholds, captcha, probation)
- `GroupRegistry` — O(1) lookup by group_id, manages all monitored groups
- `groups.json` — Per-group config file; falls back to `.env` for single-group mode
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
- SQLite with **WAL mode** for concurrency
- `session.exec(select(Model).where(...)).first()` syntax
- Atomic updates for violation counts (prevents race conditions)
- No Alembic — use `SQLModel.metadata.create_all`

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
- **Coverage**: 99.9% maintained (534 tests) — check before committing

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
- **Steps**: Ruff lint → pytest
- **Docker**: Multi-stage build with `uv`, non-root user, 512MB limit

## Notes

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
