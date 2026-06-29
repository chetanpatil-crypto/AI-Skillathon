"""Built-in Iceberg table metadata health checks."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import snowflake.connector


class Severity(str, Enum):
    OK = "OK"
    WARN = "WARN"
    ERROR = "ERROR"


@dataclass
class CheckResult:
    check_name: str
    severity: Severity
    message: str
    details: dict[str, Any] = field(default_factory=dict)


def run_metadata_checks(
    conn: snowflake.connector.SnowflakeConnection,
    database: str,
    schema: str,
    table: str,
) -> list[CheckResult]:
    """Run all built-in metadata checks and return an ordered list of results.

    Stops after the first ERROR so downstream checks don't run against a
    non-existent or inaccessible table.
    """
    results: list[CheckResult] = []

    # Double-quoted form for DDL statements (DESCRIBE TABLE, INFORMATION_SCHEMA).
    fqn_ddl = f'"{database}"."{schema}"."{table}"'
    # Plain dot-separated form for Snowflake SYSTEM$ / table function string args.
    fqn_str = f"{database}.{schema}.{table}"

    results.append(_check_table_exists(conn, database, schema, table))
    if results[-1].severity == Severity.ERROR:
        return results

    results.extend(_check_table_info(conn, fqn_str))
    results.extend(_check_snapshot_info(conn, fqn_str))
    results.extend(_check_column_metadata(conn, fqn_ddl))

    return results


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_table_exists(
    conn: snowflake.connector.SnowflakeConnection,
    database: str,
    schema: str,
    table: str,
) -> CheckResult:
    """Confirm the table exists in INFORMATION_SCHEMA and is an Iceberg type.

    Returns ERROR if the table is absent or the query fails, WARN if the
    TABLE_TYPE does not contain 'ICEBERG' (e.g. a plain VIEW was passed),
    OK otherwise.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT TABLE_NAME, TABLE_TYPE
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_CATALOG = %s
              AND TABLE_SCHEMA  = %s
              AND TABLE_NAME    = %s
            """,
            (database.upper(), schema.upper(), table.upper()),
        )
        row = cur.fetchone()
    except Exception as exc:
        return CheckResult(
            "table_exists",
            Severity.ERROR,
            f"Could not query INFORMATION_SCHEMA.TABLES: {exc}",
        )
    finally:
        cur.close()

    if row is None:
        return CheckResult(
            "table_exists",
            Severity.ERROR,
            f"Table {database}.{schema}.{table} not found in INFORMATION_SCHEMA.",
        )

    table_type = row[1] or "UNKNOWN"
    if "ICEBERG" not in table_type.upper() and table_type.upper() != "BASE TABLE":
        return CheckResult(
            "table_exists",
            Severity.WARN,
            f"Table found but type is '{table_type}' — expected an Iceberg table.",
            {"table_type": table_type},
        )

    return CheckResult(
        "table_exists",
        Severity.OK,
        f"Table exists (type: {table_type}).",
        {"table_type": table_type},
    )


def _check_table_info(
    conn: snowflake.connector.SnowflakeConnection,
    fqn_str: str,
) -> list[CheckResult]:
    """Call SYSTEM$GET_ICEBERG_TABLE_INFORMATION and validate the JSON payload.

    Returns WARN if the function is inaccessible (e.g. privilege issue),
    ERROR if the result is NULL or unparseable, OK with the parsed blob
    otherwise. Sub-checks on metadata-location and snapshot ID are appended.
    """
    results: list[CheckResult] = []
    cur = conn.cursor()

    try:
        cur.execute("SELECT SYSTEM$GET_ICEBERG_TABLE_INFORMATION(%s)", (fqn_str,))
        raw = cur.fetchone()
    except Exception as exc:
        results.append(CheckResult(
            "iceberg_table_information",
            Severity.WARN,
            f"Could not retrieve Iceberg table information: {exc}",
        ))
        return results
    finally:
        cur.close()

    if raw is None or raw[0] is None:
        results.append(CheckResult(
            "iceberg_table_information",
            Severity.ERROR,
            "SYSTEM$GET_ICEBERG_TABLE_INFORMATION returned NULL — "
            "metadata may be corrupt or inaccessible.",
        ))
        return results

    try:
        info: dict[str, Any] = json.loads(raw[0])
    except json.JSONDecodeError:
        results.append(CheckResult(
            "iceberg_table_information",
            Severity.ERROR,
            "Could not parse Iceberg table information JSON.",
            {"raw": str(raw[0])[:500]},
        ))
        return results

    results.append(CheckResult(
        "iceberg_table_information",
        Severity.OK,
        "SYSTEM$GET_ICEBERG_TABLE_INFORMATION returned valid JSON.",
        info,
    ))
    results.extend(_validate_info_fields(info))
    return results


def _validate_info_fields(info: dict[str, Any]) -> list[CheckResult]:
    """Inspect parsed Iceberg table info for required fields.

    Checks for 'metadataLocation'/'metadata-location' (ERROR if absent)
    and 'currentSnapshotId'/'current-snapshot-id' (WARN if absent — the
    table may be empty but the metadata file still exists).
    """
    results: list[CheckResult] = []

    metadata_location = info.get("metadataLocation") or info.get("metadata-location")
    if not metadata_location:
        results.append(CheckResult(
            "metadata_location",
            Severity.ERROR,
            "metadata-location is missing from Iceberg table information.",
        ))
    else:
        results.append(CheckResult(
            "metadata_location",
            Severity.OK,
            f"metadata-location present: {metadata_location}",
            {"metadata_location": metadata_location},
        ))

    snapshot_id = info.get("currentSnapshotId") or info.get("current-snapshot-id")
    if snapshot_id is None:
        results.append(CheckResult(
            "current_snapshot",
            Severity.WARN,
            "No current snapshot found — table may be empty or never written to.",
        ))
    else:
        results.append(CheckResult(
            "current_snapshot",
            Severity.OK,
            f"Current snapshot ID: {snapshot_id}",
            {"snapshot_id": snapshot_id},
        ))

    return results


def _check_snapshot_info(
    conn: snowflake.connector.SnowflakeConnection,
    fqn_str: str,
) -> list[CheckResult]:
    """Query ICEBERG_SNAPSHOT_INFORMATION for snapshot count and recency.

    Returns WARN if the function is unavailable, if the table has no
    snapshots, or if the snapshot count exceeds 100 (a signal that
    EXPIRE SNAPSHOTS should be run). Returns OK with aggregate stats
    otherwise.
    """
    results: list[CheckResult] = []
    cur = conn.cursor()
    safe_ref = fqn_str.replace("'", "''")

    try:
        cur.execute(
            f"""
            SELECT
                COUNT(*)          AS snapshot_count,
                MAX(COMMITTED_AT) AS latest_snapshot,
                MIN(COMMITTED_AT) AS oldest_snapshot,
                SUM(ADDED_RECORDS)   AS total_added,
                SUM(DELETED_RECORDS) AS total_deleted
            FROM TABLE(INFORMATION_SCHEMA.ICEBERG_SNAPSHOT_INFORMATION(
                TABLE_NAME => '{safe_ref}'
            ))
            """
        )
        row = cur.fetchone()
    except Exception as exc:
        results.append(CheckResult(
            "snapshot_history",
            Severity.WARN,
            f"Could not query ICEBERG_SNAPSHOT_INFORMATION: {exc}",
        ))
        return results
    finally:
        cur.close()

    if row is None:
        results.append(CheckResult(
            "snapshot_history",
            Severity.WARN,
            "ICEBERG_SNAPSHOT_INFORMATION returned no rows.",
        ))
        return results

    snapshot_count, latest, oldest, added, deleted = row
    snapshot_count = snapshot_count or 0

    if snapshot_count == 0:
        results.append(CheckResult(
            "snapshot_history",
            Severity.WARN,
            "No snapshots found — table has never been written to.",
            {"snapshot_count": 0},
        ))
        return results

    severity = Severity.OK
    msg = f"{snapshot_count} snapshot(s) found. Latest: {latest}, Oldest: {oldest}."

    if snapshot_count > 100:
        severity = Severity.WARN
        msg += (
            f" High snapshot count ({snapshot_count}) — "
            "consider running ALTER ICEBERG TABLE … EXPIRE SNAPSHOTS."
        )

    results.append(CheckResult(
        "snapshot_history",
        severity,
        msg,
        {
            "snapshot_count": snapshot_count,
            "latest_snapshot": str(latest),
            "oldest_snapshot": str(oldest),
            "total_added_records": added,
            "total_deleted_records": deleted,
        },
    ))
    return results


def _check_column_metadata(
    conn: snowflake.connector.SnowflakeConnection,
    fqn_ddl: str,
) -> list[CheckResult]:
    """Run DESCRIBE TABLE to verify the schema is readable and non-empty.

    Returns ERROR if the command fails (permission issue or table gone),
    WARN if the table has zero columns, OK with the column list otherwise.
    """
    cur = conn.cursor()
    try:
        cur.execute(f"DESCRIBE TABLE {fqn_ddl}")  # noqa: S608
        columns = cur.fetchall()
    except Exception as exc:
        return [CheckResult(
            "column_metadata",
            Severity.ERROR,
            f"DESCRIBE TABLE failed: {exc}",
        )]
    finally:
        cur.close()

    if not columns:
        return [CheckResult(
            "column_metadata",
            Severity.WARN,
            "Table has no columns — schema may be undefined.",
        )]

    return [CheckResult(
        "column_metadata",
        Severity.OK,
        f"{len(columns)} column(s) defined.",
        {"columns": [col[0] for col in columns]},
    )]
