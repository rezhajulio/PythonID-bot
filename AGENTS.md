# AGENTS.md - PythonID Telegram Bot

## Overview

Indonesian Telegram bot for group profile enforcement (photo + username), captcha verification, and anti-spam protection. Built with python-telegram-bot v20+, SQLModel, Pydantic, and Logfire.

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
│   ├── handlers/         # Telegram update handlers
│   │   ├── captcha.py    # New member verification flow
│   │   ├── verify.py     # Admin /verify, /unverify commands
│   │   ├── check.py      # Admin /check command + forwarded message handling
│   │   ├── anti_spam.py  # Probation enforcement (links/forwards)
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
├── tests/                # pytest-asyncio (18 files, 100% coverage)
└── data/bot.db           # SQLite (auto-created, WAL mode)
```

## Where to Look

| Task | Location | Notes |
|------|----------|-------|
| Add new handler | `main.py` | Register with appropriate group (-1, 0, 1) |
| Modify messages | `constants.py` | All Indonesian templates centralized |
| Add DB table | `database/models.py` → `database/service.py` | Add model, then service methods |
| Change config | `config.py` | Pydantic BaseSettings with env vars |
| Add URL whitelist | `constants.py` → `WHITELISTED_URL_DOMAINS` | Suffix-based matching |
| Add Telegram whitelist | `constants.py` → `WHITELISTED_TELEGRAM_PATHS` | Lowercase, exact path match |

## Code Map (Key Files)

| File | Lines | Role |
|------|-------|------|
| `database/service.py` | 645 | **Complexity hotspot** - handles warnings, captcha, probation state |
| `constants.py` | 528 | Templates + massive whitelists (Indonesian tech community) |
| `handlers/captcha.py` | 365 | New member join → restrict → verify → unrestrict lifecycle |
| `handlers/verify.py` | 344 | Admin verification commands + inline button callbacks |
| `handlers/anti_spam.py` | 327 | Probation enforcement with URL whitelisting |
| `main.py` | 293 | Entry point, logging, handler registration, JobQueue setup |

## Architecture Patterns

### Handler Priority Groups
```python
# main.py - Order matters!
group=-1  # topic_guard: Runs FIRST, deletes unauthorized warning topic msgs
group=0   # Commands, DM, anti_spam: Default priority
group=1   # message_handler: Runs LAST, profile compliance check
```

### Singletons
- `get_settings()` — Pydantic settings, `@lru_cache`
- `get_database()` — DatabaseService, lazy init
- `BotInfoCache` — Class-level cache for bot username/ID

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
- **Coverage**: 100% maintained — check before committing

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
- JobQueue auto-restriction job runs every 5 minutes (first run after 5 min delay)
- Bot uses `allowed_updates=["message", "callback_query", "chat_member"]`
- Captcha uses both `ChatMemberHandler` (for "Hide Join" groups) and `MessageHandler` fallback
