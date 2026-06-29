"""CLI integration tests using Click's CliRunner (no real Snowflake connection)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from iceberg_checker.cli import main
from iceberg_checker.checks.metadata import CheckResult, Severity


@patch("iceberg_checker.cli.get_connection")
@patch("iceberg_checker.cli.run_metadata_checks")
def test_check_healthy_table(mock_checks, mock_conn):
    mock_conn.return_value = MagicMock()
    mock_checks.return_value = [
        CheckResult("table_exists", Severity.OK, "Table exists (type: ICEBERG TABLE)."),
        CheckResult("column_metadata", Severity.OK, "3 column(s) defined."),
    ]
    result = CliRunner().invoke(main, [
        "check", "MYDB.MYSCHEMA.MY_TABLE",
        "--account", "acct", "--user", "usr", "--password", "pw",
    ])
    assert result.exit_code == 0
    assert "HEALTHY" in result.output


@patch("iceberg_checker.cli.get_connection")
@patch("iceberg_checker.cli.run_metadata_checks")
def test_check_unhealthy_table(mock_checks, mock_conn):
    mock_conn.return_value = MagicMock()
    mock_checks.return_value = [
        CheckResult("table_exists", Severity.OK, "Table exists."),
        CheckResult("metadata_location", Severity.ERROR, "metadata-location missing."),
    ]
    result = CliRunner().invoke(main, [
        "check", "MYDB.MYSCHEMA.MY_TABLE",
        "--account", "acct", "--user", "usr", "--password", "pw",
    ])
    assert result.exit_code == 1
    assert "UNHEALTHY" in result.output


@patch("iceberg_checker.cli.get_connection")
@patch("iceberg_checker.cli.run_metadata_checks")
def test_check_json_format(mock_checks, mock_conn):
    mock_conn.return_value = MagicMock()
    mock_checks.return_value = [
        CheckResult("table_exists", Severity.OK, "Table exists."),
    ]
    result = CliRunner().invoke(main, [
        "check", "MYDB.MYSCHEMA.MY_TABLE",
        "--account", "acct", "--user", "usr", "--password", "pw",
        "--format", "json",
    ])
    assert result.exit_code == 0
    assert '"status": "HEALTHY"' in result.output
    assert '"checks"' in result.output


def test_check_missing_database_flag():
    result = CliRunner().invoke(main, [
        "check", "MY_TABLE",
        "--account", "acct", "--user", "usr", "--password", "pw",
    ])
    assert result.exit_code != 0
    assert "Database is required" in result.output


def test_check_invalid_identifier():
    # Injection attempt in the table name position of a fully-qualified reference
    result = CliRunner().invoke(main, [
        "check", "MYDB.MYSCHEMA.MY'; DROP TABLE x;--",
        "--account", "acct", "--user", "usr", "--password", "pw",
    ])
    assert result.exit_code != 0
    assert "Invalid" in result.output


def test_version_flag():
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_help_exits_cleanly():
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "check" in result.output
    assert "list-tables" in result.output


@patch("iceberg_checker.cli.get_connection")
def test_connection_failure_exits_2(mock_conn):
    mock_conn.side_effect = EnvironmentError("Missing required credential: SNOWFLAKE_ACCOUNT")
    result = CliRunner().invoke(main, [
        "check", "MYDB.MYSCHEMA.T",
        "--account", "bad", "--user", "u", "--password", "p",
    ])
    assert result.exit_code == 2
    assert "Connection failed" in result.output
