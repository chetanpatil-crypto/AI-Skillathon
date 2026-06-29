"""Extension protocol for custom health checks.

Any callable matching ``CheckFunction`` can be added to the check pipeline
by passing it to ``run_checks``, enabling teams to layer domain-specific
checks on top of the built-in metadata checks.

Example::

    from iceberg_checker.checks.base import CheckFunction, CheckResult, Severity

    def my_row_count_check(conn, database, schema, table):
        cur = conn.cursor()
        try:
            cur.execute(f'SELECT COUNT(*) FROM "{database}"."{schema}"."{table}"')
            (count,) = cur.fetchone()
        finally:
            cur.close()
        if count == 0:
            return [CheckResult("row_count", Severity.WARN, "Table is empty.")]
        return [CheckResult("row_count", Severity.OK, f"{count:,} rows.")]
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

import snowflake.connector

from .metadata import CheckResult, Severity

__all__ = ["CheckFunction", "CheckResult", "Severity"]


@runtime_checkable
class CheckFunction(Protocol):
    """Protocol satisfied by any function that runs a single health check.

    Parameters match ``run_metadata_checks`` so custom checks slot in without
    any adapter boilerplate.
    """

    def __call__(
        self,
        conn: snowflake.connector.SnowflakeConnection,
        database: str,
        schema: str,
        table: str,
    ) -> list[CheckResult]:
        ...
