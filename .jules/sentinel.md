## 2025-02-18 - Fix Information Leakage via Exception Detail Exposure in Bot Replies
**Vulnerability:** Telegram bot responses were printing raw Python exception messages (`{e}`) directly to users on failure.
**Learning:** Even though the bot is restricted to admins or specific groups, raw exception messages can expose internal database details, file paths, API errors, or other environment information that shouldn't be accessible to arbitrary users.
**Prevention:** Use generic error messages for the user-facing reply (`await update.message.reply_text('❌ Gagal. Silakan coba lagi.')`) and log the detailed exception with stack traces internally (`logger.error(..., exc_info=True)`).
