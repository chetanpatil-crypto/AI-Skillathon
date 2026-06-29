"""Unit tests for metadata health checks using mocked Snowflake connections."""
import json
from unittest.mock import MagicMock

import pytest

from iceberg_checker.checks.metadata import (
    CheckResult,
    Severity,
    run_metadata_checks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _by_name(results: list[CheckResult]) -> dict[str, CheckResult]:
    return {r.check_name: r for r in results}


def _healthy_sequence(info_json: str, snapshot_count: int = 5) -> list:
    return [
        ("MY_TABLE", "ICEBERG TABLE"),
        (info_json,),
        (snapshot_count, "2024-06-01", "2024-01-01", 1000, 50),
    ]


# ---------------------------------------------------------------------------
# table_exists
# ---------------------------------------------------------------------------

def test_table_not_found(make_conn):
    conn = make_conn(fetchone_sequence=[None])
    results = run_metadata_checks(conn, "DB", "SCH", "MISSING")
    assert results[0].severity == Severity.ERROR
    assert "not found" in results[0].message or "Could not query" in results[0].message
    assert len(results) == 1  # early exit


def test_table_wrong_type_warns(make_conn):
    conn = make_conn(
        fetchone_sequence=[
            ("MY_TABLE", "VIEW"),
            (json.dumps({"metadataLocation": "s3://x", "currentSnapshotId": 1}),),
            (3, "2024-01-10", "2024-01-01", 100, 5),
        ],
        fetchall=[("col1", "TEXT", None)],
    )
    results = run_metadata_checks(conn, "DB", "SCH", "MY_TABLE")
    assert _by_name(results)["table_exists"].severity == Severity.WARN


def test_table_exists_sql_error(make_conn):
    conn = make_conn(fetchone_sequence=[Exception("permission denied on INFORMATION_SCHEMA")])
    # fetchone raises when called — simulate a SQL error
    cur = MagicMock()
    conn_mock = MagicMock()
    conn_mock.cursor.return_value = cur
    cur.execute.side_effect = Exception("permission denied")
    results = run_metadata_checks(conn_mock, "DB", "SCH", "T")
    assert results[0].severity == Severity.ERROR
    assert len(results) == 1


# ---------------------------------------------------------------------------
# Happy path — all checks OK
# ---------------------------------------------------------------------------

def test_healthy_table(make_conn, healthy_info):
    conn = make_conn(
        fetchone_sequence=_healthy_sequence(healthy_info),
        fetchall=[("id", "NUMBER", None), ("name", "TEXT", None)],
    )
    checks = _by_name(run_metadata_checks(conn, "DB", "SCH", "MY_TABLE"))

    assert checks["table_exists"].severity == Severity.OK
    assert checks["iceberg_table_information"].severity == Severity.OK
    assert checks["metadata_location"].severity == Severity.OK
    assert checks["current_snapshot"].severity == Severity.OK
    assert checks["snapshot_history"].severity == Severity.OK
    assert checks["column_metadata"].severity == Severity.OK


# ---------------------------------------------------------------------------
# iceberg_table_information
# ---------------------------------------------------------------------------

def test_iceberg_info_returns_null(make_conn):
    conn = make_conn(
        fetchone_sequence=[("T", "ICEBERG TABLE"), (None,), (2, "2024-01-05", "2024-01-01", 200, 10)],
        fetchall=[("col1", "TEXT", None)],
    )
    checks = _by_name(run_metadata_checks(conn, "DB", "SCH", "T"))
    assert checks["iceberg_table_information"].severity == Severity.ERROR
    assert "NULL" in checks["iceberg_table_information"].message


def test_iceberg_info_invalid_json(make_conn):
    conn = make_conn(
        fetchone_sequence=[("T", "ICEBERG TABLE"), ("not-valid-json",), (2, "2024-01-05", "2024-01-01", 200, 10)],
        fetchall=[("col1", "TEXT", None)],
    )
    checks = _by_name(run_metadata_checks(conn, "DB", "SCH", "T"))
    assert checks["iceberg_table_information"].severity == Severity.ERROR


def test_iceberg_info_query_exception():
    cur = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.side_effect = [("T", "ICEBERG TABLE"), Exception("permission denied")]
    cur.execute.side_effect = [None, Exception("permission denied")]
    checks = _by_name(run_metadata_checks(conn, "DB", "SCH", "T"))
    assert checks["iceberg_table_information"].severity == Severity.WARN


# ---------------------------------------------------------------------------
# metadata_location
# ---------------------------------------------------------------------------

def test_missing_metadata_location(make_conn):
    conn = make_conn(
        fetchone_sequence=_healthy_sequence(json.dumps({"currentSnapshotId": 99})),
        fetchall=[("col1", "TEXT", None)],
    )
    assert _by_name(run_metadata_checks(conn, "DB", "SCH", "MY_TABLE"))["metadata_location"].severity == Severity.ERROR


# ---------------------------------------------------------------------------
# current_snapshot
# ---------------------------------------------------------------------------

def test_no_current_snapshot_warns(make_conn):
    conn = make_conn(
        fetchone_sequence=_healthy_sequence(json.dumps({"metadataLocation": "s3://bucket/meta.json"})),
        fetchall=[("col1", "TEXT", None)],
    )
    r = _by_name(run_metadata_checks(conn, "DB", "SCH", "MY_TABLE"))["current_snapshot"]
    assert r.severity == Severity.WARN
    assert "empty" in r.message or "never" in r.message


# ---------------------------------------------------------------------------
# snapshot_history
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("count,expected", [(150, Severity.WARN), (5, Severity.OK)])
def test_snapshot_count_severity(make_conn, healthy_info, count, expected):
    conn = make_conn(
        fetchone_sequence=[("T", "ICEBERG TABLE"), (healthy_info,), (count, "2024-01-10", "2023-01-01", 1000, 10)],
        fetchall=[("id", "NUMBER", None)],
    )
    assert _by_name(run_metadata_checks(conn, "DB", "SCH", "T"))["snapshot_history"].severity == expected


def test_zero_snapshots_warns(make_conn, healthy_info):
    conn = make_conn(
        fetchone_sequence=[("T", "ICEBERG TABLE"), (healthy_info,), (0, None, None, 0, 0)],
        fetchall=[("id", "NUMBER", None)],
    )
    assert _by_name(run_metadata_checks(conn, "DB", "SCH", "T"))["snapshot_history"].severity == Severity.WARN


# ---------------------------------------------------------------------------
# column_metadata
# ---------------------------------------------------------------------------

def test_no_columns_warns(make_conn, healthy_info):
    conn = make_conn(fetchone_sequence=_healthy_sequence(healthy_info), fetchall=[])
    assert _by_name(run_metadata_checks(conn, "DB", "SCH", "T"))["column_metadata"].severity == Severity.WARN


def test_column_count_in_ok_message(make_conn, healthy_info):
    cols = [("id", "NUMBER", None), ("ts", "TIMESTAMP", None), ("val", "FLOAT", None)]
    conn = make_conn(fetchone_sequence=_healthy_sequence(healthy_info), fetchall=cols)
    r = _by_name(run_metadata_checks(conn, "DB", "SCH", "T"))["column_metadata"]
    assert r.severity == Severity.OK
    assert "3" in r.message


# ---------------------------------------------------------------------------
# reporter
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("severity,expected_code", [(Severity.OK, 0), (Severity.ERROR, 1)])
def test_print_report_exit_code(severity, expected_code):
    from iceberg_checker.reporter import print_report
    results = [CheckResult("check_a", severity, "msg")]
    assert print_report("DB.SCH.T", results) == expected_code


def test_print_report_json_format():
    from iceberg_checker.reporter import print_report
    results = [CheckResult("check_a", Severity.OK, "looks good", {"key": "val"})]
    code = print_report("DB.SCH.T", results, fmt="json")
    assert code == 0


def test_print_report_warn_does_not_error():
    from iceberg_checker.reporter import print_report
    results = [CheckResult("check_a", Severity.WARN, "watch out")]
    assert print_report("DB.SCH.T", results) == 0
