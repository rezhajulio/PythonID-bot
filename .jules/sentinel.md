## 2024-05-27 - Information Leakage in Error Messages
**Vulnerability:** Exception details (`{e}`) were being directly exposed to end-users in Telegram bot replies when API requests or internal operations failed.
**Learning:** This is a classic information leakage vulnerability. While seemingly harmless, exposing raw exception strings can reveal underlying library versions, database table names, or internal path structures to malicious actors.
**Prevention:** Always use generic, user-friendly error messages (e.g., "Terjadi kesalahan internal") for the client/user, and use a robust logging mechanism (e.g., `logger.error(..., exc_info=True)`) to capture the full stack trace and exception details for internal debugging.
