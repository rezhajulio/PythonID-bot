# AGENTS.md - PythonID Telegram Bot

## Commands

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run a single test file
uv run pytest tests/test_check.py

# Run a single test function
uv run pytest tests/test_check.py::TestHandleCheckCommand::test_check_command_non_admin

# Run tests with coverage
uv run pytest --cov=bot --cov-report=term-missing

# Run the bot
uv run pythonid-bot
```

## Architecture

- **src/bot/**: Main application package
  - **main.py**: Entry point with JobQueue integration — register new handlers here
  - **config.py**: Pydantic settings (`get_settings()` cached via `lru_cache`)
  - **constants.py**: Centralized message templates and utilities
  - **handlers/**: Telegram update handlers (message.py, dm.py, captcha.py, verify.py, anti_spam.py, topic_guard.py, check.py)
  - **services/**: Business logic (user_checker.py, scheduler.py, bot_info.py, telegram_utils.py, captcha_recovery.py)
  - **database/**: SQLModel schemas (models.py) and SQLite operations (service.py) — use `get_database()` singleton
- **tests/**: pytest-asyncio tests with mocked telegram API
- **data/bot.db**: SQLite database (auto-created via `SQLModel.metadata.create_all`)

## Code Style

- **Python 3.11+** with type hints; imports grouped: stdlib → third-party → local
- **Async/await**: All handlers are async functions
- **PTB v20+**: Use `ContextTypes.DEFAULT_TYPE` for context type hints, not legacy `Dispatcher`/`Updater`
- **SQLModel**: Use `session.exec(select(Model).where(...)).first()` syntax; no Alembic migrations
- **Logging**: Use `logfire` for structured logging, not `print()` or stdlib `logging`
- **Error handling**: Catch specific exceptions (e.g., `TimedOut`), log errors, return gracefully
- **No comments**: Avoid inline comments unless code is complex
- **Docstrings**: Module-level docstrings required, function docstrings for public APIs

## Testing

- **Async mode**: `asyncio_mode = auto` in pyproject.toml — do NOT use `@pytest.mark.asyncio` decorators
- **Fixtures**: Check existing fixtures in test files (`mock_update`, `mock_context`, `mock_settings`)
- **Mocking**: Use `AsyncMock` and `MagicMock` for telegram API; no real network calls
