#!/usr/bin/env python3
"""Query Pydantic Logfire logs via SQL API.

Usage:
    python scripts/query_logs.py errors --minutes 30
    python scripts/query_logs.py warnings --limit 20
    python scripts/query_logs.py slow --threshold 5000
    python scripts/query_logs.py user --user-id 12345
    python scripts/query_logs.py group --group-id -1001234567
    python scripts/query_logs.py sql "SELECT * FROM records LIMIT 10"

Note: Global flags (--json, --limit, --minutes) must appear BEFORE the subcommand:
    python scripts/query_logs.py --minutes 60 --limit 100 errors
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import requests

DEFAULT_API_URL = "https://logfire-us.pydantic.dev/v2/query"
DEFAULT_LIMIT = 50
DEFAULT_MINUTES = 30

QUERY_TEMPLATES: dict[str, str] = {
    "errors": """\
SELECT start_timestamp, duration, message, trace_id, is_exception,
       exception_message, attributes
FROM records
WHERE is_exception = true
  AND start_timestamp > NOW() - INTERVAL '{minutes}' MINUTE
ORDER BY start_timestamp DESC
LIMIT {limit}""",
    "warnings": """\
SELECT start_timestamp, duration, message, trace_id, level, attributes
FROM records
WHERE level = 'warn'
  AND start_timestamp > NOW() - INTERVAL '{minutes}' MINUTE
ORDER BY start_timestamp DESC
LIMIT {limit}""",
    "slow": """\
SELECT start_timestamp, duration, message, trace_id, attributes
FROM records
WHERE duration > {threshold}
  AND start_timestamp > NOW() - INTERVAL '{minutes}' MINUTE
ORDER BY duration DESC
LIMIT {limit}""",
    "user": """\
SELECT start_timestamp, duration, message, trace_id, level, attributes
FROM records
WHERE attributes->>'user_id' = '{user_id}'
  AND start_timestamp > NOW() - INTERVAL '{minutes}' MINUTE
ORDER BY start_timestamp DESC
LIMIT {limit}""",
    "group": """\
SELECT start_timestamp, duration, message, trace_id, level, attributes
FROM records
WHERE attributes->>'group_id' = '{group_id}'
  AND start_timestamp > NOW() - INTERVAL '{minutes}' MINUTE
ORDER BY start_timestamp DESC
LIMIT {limit}""",
}

def get_config() -> tuple[str, str]:
    """Read config from environment variables.

    Returns:
        Tuple of (api_url, read_token).

    Raises:
        SystemExit: If LOGFIRE_READ_TOKEN is not set.
    """
    token = os.environ.get("LOGFIRE_READ_TOKEN")
    if not token:
        print(
            "Error: LOGFIRE_READ_TOKEN not set.\n"
            "Create a read token at https://logfire.pydantic.dev → Project Settings → Read Tokens\n"
            "Then set: export LOGFIRE_READ_TOKEN=your_token_here",
            file=sys.stderr,
        )
        sys.exit(1)

    api_url = os.environ.get("LOGFIRE_API_URL", DEFAULT_API_URL)
    return api_url, token

def query_logfire(api_url: str, token: str, sql: str) -> list[dict]:
    """Execute a SQL query against Logfire API.

    Args:
        api_url: Logfire query endpoint URL.
        token: Read token for authentication.
        sql: SQL query to execute.

    Returns:
        List of record dicts.

    Raises:
        SystemExit: On API error.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {"sql": sql, "format": "json"}

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
    except requests.RequestException as e:
        print(f"Network error: {e}", file=sys.stderr)
        sys.exit(1)

    if response.status_code != 200:
        print(f"API error {response.status_code}: {response.text}", file=sys.stderr)
        sys.exit(1)

    data = response.json()
    if isinstance(data, dict) and "data" in data:
        return data["data"]
    if isinstance(data, list):
        return data
    return []

def format_text(records: list[dict]) -> str:
    """Format records as human-readable text.

    Args:
        records: List of record dicts from API.

    Returns:
        Formatted text string.
    """
    if not records:
        return "No records found."

    lines: list[str] = []
    for r in records:
        ts = r.get("start_timestamp", "unknown")
        if isinstance(ts, str) and len(ts) > 19:
            ts = ts[:19]
        duration = r.get("duration", "")
        if duration and isinstance(duration, (int, float)):
            duration = f"{duration:.0f}ms"
        level = r.get("level", "")
        trace_id = r.get("trace_id", "")
        message = r.get("message", "")
        is_exception = r.get("is_exception", False)
        exception_message = r.get("exception_message", "")

        prefix = "ERROR" if is_exception else (level.upper() if level else "INFO")
        duration_str = f" ({duration})" if duration else ""
        trace_str = f" trace:{trace_id[:8]}" if trace_id else ""

        lines.append(f"[{ts}] {prefix}{duration_str}{trace_str}")
        if message:
            lines.append(f"  {message}")
        if exception_message:
            lines.append(f"  Exception: {exception_message}")
        lines.append("")

    return "\n".join(lines).rstrip()

def build_query(command: str, args: argparse.Namespace) -> str:
    """Build SQL query from command and arguments.

    Args:
        command: Query command name (errors, warnings, slow, user, group, sql).
        args: Parsed CLI arguments.

    Returns:
        SQL query string.
    """
    if command == "sql":
        sql = args.query
        if "limit" not in sql.lower():
            sql = f"{sql.rstrip(';')} LIMIT {args.limit}"
        return sql

    template = QUERY_TEMPLATES[command]
    params: dict[str, int | str] = {
        "minutes": args.minutes,
        "limit": args.limit,
    }

    if command == "slow":
        params["threshold"] = args.threshold
    elif command == "user":
        params["user_id"] = args.user_id
    elif command == "group":
        params["group_id"] = args.group_id

    return template.format(**params)

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Parsed namespace.
    """
    parser = argparse.ArgumentParser(
        description="Query Pydantic Logfire logs via SQL API",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON instead of text",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Max results (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--minutes",
        type=int,
        default=DEFAULT_MINUTES,
        help=f"Time window in minutes (default: {DEFAULT_MINUTES})",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("errors", help="Error/exception logs")
    subparsers.add_parser("warnings", help="Warning-level logs")

    slow_parser = subparsers.add_parser("slow", help="Slow spans")
    slow_parser.add_argument(
        "--threshold",
        type=int,
        default=5000,
        help="Duration threshold in ms (default: 5000)",
    )

    user_parser = subparsers.add_parser("user", help="Activity by user ID")
    user_parser.add_argument("--user-id", required=True, type=int, help="Telegram user ID")

    group_parser = subparsers.add_parser("group", help="Activity by group ID")
    group_parser.add_argument("--group-id", required=True, type=int, help="Telegram group ID")

    sql_parser = subparsers.add_parser("sql", help="Free-form SQL query")
    sql_parser.add_argument("query", help="SQL query to execute")

    return parser.parse_args(argv)

def main(argv: list[str] | None = None) -> None:
    """Main entry point.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).
    """
    args = parse_args(argv)
    api_url, token = get_config()
    sql = build_query(args.command, args)
    records = query_logfire(api_url, token, sql)

    if args.json_output:
        print(json.dumps(records, indent=2, default=str))
    else:
        print(format_text(records))

if __name__ == "__main__":
    main()
