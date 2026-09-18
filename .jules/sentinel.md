## 2024-05-24 - Information Leakage in Telegram Error Replies
**Vulnerability:** Raw exception details (`{e}`) were being returned directly to users in Telegram messages on failures (e.g., `reply_text(f"❌ Gagal: {e}")`).
**Learning:** Returning unhandled exception strings can leak sensitive internal details like database structures, stack trace fragments, or file paths to end-users.
**Prevention:** Always use a generic error message for user-facing errors (e.g., "Kesalahan internal") and ensure detailed exceptions are logged internally via `logger.error(..., exc_info=True)`.
