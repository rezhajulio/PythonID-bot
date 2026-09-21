## 2026-09-21 - [Exception Leakage Fixed]
**Vulnerability:** Raw exception strings (`{e}`) were exposed to Telegram users in bot replies (`reply_text` and `edit_message_text`) in `check.py` and `verify.py`.
**Learning:** Returning Python exceptions to end-users can inadvertently leak internal architecture details, filesystem paths, database structures, or other sensitive runtime context.
**Prevention:** Always use generic error messages for end-users (e.g. "An error occurred") and log the raw exception (with `exc_info=True`) to a secure logging backend for developers.
