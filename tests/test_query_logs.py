"""Tests for the Logfire query CLI tool."""

from unittest.mock import MagicMock, patch

import pytest

from scripts.query_logs import (
    build_query,
    format_text,
    get_config,
    main,
    parse_args,
    query_logfire,
)

class TestGetConfig:
    """get_config reads from environment variables."""

    def test_returns_token_and_url(self):
        """Returns token and URL from env."""
        with patch.dict("os.environ", {"LOGFIRE_READ_TOKEN": "test_token"}):
            url, token = get_config()
            assert token == "test_token"
            assert "logfire" in url

    def test_custom_url(self):
        """Custom URL overrides default."""
        with patch.dict("os.environ", {"LOGFIRE_READ_TOKEN": "tok", "LOGFIRE_API_URL": "http://custom"}):
            url, token = get_config()
            assert url == "http://custom"

    def test_missing_token_exits(self):
        """Exits with error when LOGFIRE_READ_TOKEN not set."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(SystemExit):
                get_config()

class TestBuildQuery:
    """build_query generates correct SQL from commands."""

    def test_errors_query(self):
        """Errors command generates exception filter."""
        args = parse_args(["--minutes", "60", "--limit", "25", "errors"])
        sql = build_query("errors", args)
        assert "is_exception = true" in sql
        assert "60" in sql
        assert "LIMIT 25" in sql

    def test_warnings_query(self):
        """Warnings command generates level filter."""
        args = parse_args(["warnings"])
        sql = build_query("warnings", args)
        assert "level = 'warn'" in sql

    def test_slow_query_with_threshold(self):
        """Slow command includes duration threshold."""
        args = parse_args(["slow", "--threshold", "3000"])
        sql = build_query("slow", args)
        assert "duration > 3000" in sql

    def test_user_query(self):
        """User command filters by user_id."""
        args = parse_args(["user", "--user-id", "12345"])
        sql = build_query("user", args)
        assert "'12345'" in sql
        assert "user_id" in sql

    def test_group_query(self):
        """Group command filters by group_id."""
        args = parse_args(["group", "--group-id", "-100123"])
        sql = build_query("group", args)
        assert "'-100123'" in sql
        assert "group_id" in sql

    def test_sql_query_passthrough(self):
        """SQL command passes query through."""
        args = parse_args(["sql", "SELECT * FROM records LIMIT 10"])
        sql = build_query("sql", args)
        assert sql == "SELECT * FROM records LIMIT 10"

    def test_sql_query_adds_limit_if_missing(self):
        """SQL command adds LIMIT if not in query."""
        args = parse_args(["sql", "SELECT * FROM records"])
        sql = build_query("sql", args)
        assert "LIMIT 50" in sql

    def test_sql_query_preserves_existing_limit(self):
        """SQL command keeps existing LIMIT."""
        args = parse_args(["sql", "SELECT * FROM records LIMIT 10"])
        sql = build_query("sql", args)
        assert "LIMIT 10" in sql
        assert sql.count("LIMIT") == 1

class TestFormatText:
    """format_text produces readable output."""

    def test_empty_records(self):
        """Empty records returns 'No records found'."""
        assert format_text([]) == "No records found."

    def test_single_error_record(self):
        """Error record shows ERROR prefix and exception."""
        records = [
            {
                "start_timestamp": "2026-06-11T14:32:01Z",
                "duration": 523,
                "message": "Failed to restrict user",
                "trace_id": "abc123def456",
                "is_exception": True,
                "exception_message": "BadRequest: User not found",
            }
        ]
        output = format_text(records)
        assert "[2026-06-11T14:32:01]" in output
        assert "ERROR" in output
        assert "(523ms)" in output
        assert "trace:abc123d" in output
        assert "Failed to restrict user" in output
        assert "BadRequest: User not found" in output

    def test_warning_record(self):
        """Warning record shows WARN prefix."""
        records = [{"level": "warn", "message": "Slow response"}]
        output = format_text(records)
        assert "WARN" in output

    def test_multiple_records(self):
        """Multiple records are separated by blank lines."""
        records = [{"message": "a"}, {"message": "b"}]
        output = format_text(records)
        assert "a" in output
        assert "b" in output

class TestQueryLogfire:
    """query_logfire makes API calls."""

    @patch("scripts.query_logs.requests.post")
    def test_successful_query(self, mock_post):
        """Returns data from successful API response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"message": "test"}]
        mock_post.return_value = mock_resp

        result = query_logfire("http://api", "token", "SELECT 1")
        assert result == [{"message": "test"}]

    @patch("scripts.query_logs.requests.post")
    def test_wrapped_response(self, mock_post):
        """Handles response with 'data' wrapper."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"message": "test"}]}
        mock_post.return_value = mock_resp

        result = query_logfire("http://api", "token", "SELECT 1")
        assert result == [{"message": "test"}]

    @patch("scripts.query_logs.requests.post")
    def test_api_error_exits(self, mock_post):
        """Exits on non-200 status."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        mock_post.return_value = mock_resp

        with pytest.raises(SystemExit):
            query_logfire("http://api", "bad_token", "SELECT 1")

    @patch("scripts.query_logs.requests.post")
    def test_network_error_exits(self, mock_post):
        """Exits on network error."""
        import requests as req
        mock_post.side_effect = req.ConnectionError("timeout")

        with pytest.raises(SystemExit):
            query_logfire("http://api", "token", "SELECT 1")

class TestParseArgs:
    """parse_args handles CLI arguments."""

    def test_errors_default(self):
        """Errors command with defaults."""
        args = parse_args(["errors"])
        assert args.command == "errors"
        assert args.minutes == 30
        assert args.limit == 50

    def test_custom_minutes_and_limit(self):
        """Custom minutes and limit before subcommand."""
        args = parse_args(["--minutes", "120", "--limit", "100", "errors"])
        assert args.minutes == 120
        assert args.limit == 100

    def test_json_flag(self):
        """--json flag sets json_output."""
        args = parse_args(["--json", "errors"])
        assert args.json_output is True

    def test_slow_threshold(self):
        """Slow command accepts threshold."""
        args = parse_args(["slow", "--threshold", "3000"])
        assert args.threshold == 3000

    def test_user_requires_id(self):
        """User command requires --user-id."""
        with pytest.raises(SystemExit):
            parse_args(["user"])

    def test_group_requires_id(self):
        """Group command requires --group-id."""
        with pytest.raises(SystemExit):
            parse_args(["group"])

    def test_sql_requires_query(self):
        """SQL command requires query argument."""
        with pytest.raises(SystemExit):
            parse_args(["sql"])

    def test_command_required(self):
        """Command is required."""
        with pytest.raises(SystemExit):
            parse_args([])

    def test_user_id_rejects_non_int(self):
        """--user-id rejects non-numeric input (SQL injection prevention)."""
        with pytest.raises(SystemExit):
            parse_args(["user", "--user-id", "abc"])

    def test_group_id_rejects_non_int(self):
        """--group-id rejects non-numeric input (SQL injection prevention)."""
        with pytest.raises(SystemExit):
            parse_args(["group", "--group-id", "abc"])

    def test_threshold_rejects_non_int(self):
        """--threshold rejects non-numeric input."""
        with pytest.raises(SystemExit):
            parse_args(["slow", "--threshold", "abc"])

class TestMainIntegration:
    """main() orchestrates query flow."""

    @patch("scripts.query_logs.query_logfire")
    @patch("scripts.query_logs.get_config", return_value=("http://api", "token"))
    def test_main_text_output(self, mock_config, mock_query, capsys):
        """main() prints formatted text."""
        mock_query.return_value = [{"message": "test error", "is_exception": True}]
        main(["errors"])
        output = capsys.readouterr().out
        assert "ERROR" in output
        assert "test error" in output

    @patch("scripts.query_logs.query_logfire")
    @patch("scripts.query_logs.get_config", return_value=("http://api", "token"))
    def test_main_json_output(self, mock_config, mock_query, capsys):
        """main() --json prints JSON."""
        mock_query.return_value = [{"message": "test"}]
        main(["--json", "errors"])
        output = capsys.readouterr().out
        data = __import__("json").loads(output)
        assert data == [{"message": "test"}]
