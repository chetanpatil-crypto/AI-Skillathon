"""Render health check results to the terminal and/or a file."""
from __future__ import annotations

import json
import textwrap
from typing import Sequence

from rich.console import Console

from .checks.metadata import CheckResult, Severity

_SEP = "-" * 39

_ICON = {
    Severity.OK:    ("[green]✔[/green]", "OK"),
    Severity.WARN:  ("[yellow]⚠[/yellow]", "WARNING"),
    Severity.ERROR: ("[red]✖[/red]", "ERROR"),
}

_RECOMMENDATIONS: list[tuple[str, Severity, str]] = [
    ("table_exists",              Severity.ERROR, "Verify table name, database context, and REFERENCES privilege"),
    ("iceberg_table_information", Severity.ERROR, "Check external volume connectivity and IAM/storage integration permissions"),
    ("metadata_location",         Severity.ERROR, "Rebuild Iceberg metadata pointers: ALTER ICEBERG TABLE ... REFRESH"),
    ("current_snapshot",          Severity.WARN,  "Validate table initialization -- no current snapshot found"),
    ("snapshot_history",          Severity.WARN,  "Run snapshot cleanup: ALTER ICEBERG TABLE ... EXECUTE EXPIRE_SNAPSHOTS"),
    ("snapshot_history",          Severity.ERROR,  "Table has never been written to -- load data and re-check"),
    ("column_metadata",           Severity.ERROR, "Verify external volume permissions (DESCRIBE TABLE failed)"),
]

console = Console(legacy_windows=False)


def _health_score(ok: int, warn: int, total: int) -> int:
    if total == 0:
        return 0
    return round((ok + warn * 0.5) / total * 100)


def _status_label(error: int, warn: int) -> tuple[str, str]:
    if error == 0 and warn == 0:
        return "HEALTHY", "green"
    if error == 0:
        return "DEGRADED", "yellow"
    return "UNHEALTHY", "red"


def _build_recommendations(results: Sequence[CheckResult]) -> list[str]:
    sev = {r.check_name: r.severity for r in results}
    seen: set[str] = set()
    recs: list[str] = []
    for check_name, trigger_sev, text in _RECOMMENDATIONS:
        if sev.get(check_name) == trigger_sev and text not in seen:
            recs.append(text)
            seen.add(text)
    return recs


def _ai_insight(results: Sequence[CheckResult]) -> str:
    """Return a plain-language diagnostic paragraph matched to the check result pattern."""
    sev    = {r.check_name: r.severity for r in results}
    errors = [r.check_name for r in results if r.severity == Severity.ERROR]
    warns  = [r.check_name for r in results if r.severity == Severity.WARN]

    # All clear
    if not errors and not warns:
        return (
            "All health signals are nominal. The metadata chain is intact, the snapshot "
            "history is healthy, and the column schema is fully readable. "
            "No action is required at this time."
        )

    # Metadata location lost — root cause, cascade pattern
    if "metadata_location" in errors:
        cascade = [c for c in ("current_snapshot", "snapshot_history") if c in warns or c in errors]
        cascade_note = (
            f" The {' and '.join(cascade)} signal(s) are downstream symptoms of the same root "
            "cause and will resolve once the metadata pointer is restored."
            if cascade else ""
        )
        return (
            "This table shows signs of metadata fragmentation, commonly seen after "
            "failed streaming ingestion, an aborted compaction job, or a storage lifecycle "
            "policy that deleted the metadata file." + cascade_note + " "
            "Prioritize ALTER ICEBERG TABLE ... REFRESH before investigating any other signals."
        )

    # External volume / IAM unreachable
    if "iceberg_table_information" in errors:
        return (
            "Snowflake cannot reach the Iceberg metadata in external storage. "
            "This pattern is typical of a revoked IAM policy, an expired SAS token, or a "
            "misconfigured external volume after a cloud credential rotation. "
            "Validate the storage integration with DESCRIBE EXTERNAL VOLUME before "
            "attempting any table-level fixes."
        )

    # Table not found
    if "table_exists" in errors:
        return (
            "The table was not found under the provided fully-qualified name. "
            "Confirm the database and schema context, check whether the table was recently "
            "dropped, and verify that the running role has REFERENCES privilege on "
            "INFORMATION_SCHEMA. A privilege gap here causes table_exists to ERROR "
            "even when the table physically exists."
        )

    # Column schema unreadable
    if "column_metadata" in errors:
        return (
            "DESCRIBE TABLE failed, which almost always indicates a broken link between "
            "the table definition and its external volume. This can happen after a storage "
            "integration is modified or a bucket policy is tightened. "
            "The table structure is likely intact -- restore the external volume permissions "
            "and re-check before considering a metadata rebuild."
        )

    # Snapshot bloat (no other errors)
    if "snapshot_history" in warns and not errors:
        snap_result = next((r for r in results if r.check_name == "snapshot_history"), None)
        count = (
            snap_result.details.get("snapshot_count", "many")
            if snap_result and snap_result.details else "many"
        )
        return (
            f"With {count} unexpired snapshots, metadata scan overhead is accumulating. "
            "This pattern is typical of a pipeline that lacks a scheduled EXPIRE SNAPSHOTS "
            "maintenance task. Pruning to a 7-day retention window will reclaim external "
            "storage and measurably improve query planning speed at this snapshot volume."
        )

    # Table never loaded
    if "current_snapshot" in warns and not errors:
        return (
            "The table exists and its schema is readable, but no data has been committed yet. "
            "This is expected for a newly created Iceberg table awaiting its first ingestion run. "
            "Trigger the initial load job, then re-run the health check to confirm "
            "snapshot registration and metadata pointer creation."
        )

    # Multiple errors — systemic failure
    if len(errors) >= 2:
        listed = ", ".join(errors)
        return (
            f"Multiple critical checks failed ({listed}). "
            "This cascade pattern points to a systemic storage or permission failure rather "
            "than an isolated table issue — a single root cause (external volume misconfiguration, "
            "IAM policy change, or storage outage) can trigger all of these simultaneously. "
            "Validate the external volume and storage integration before addressing individual checks."
        )

    # Generic fallback
    return (
        "One or more health signals require attention. "
        "Apply the recommendations above in the listed order, then re-run the health check "
        "to confirm each signal resolves before moving to the next."
    )


def _render(
    out: Console,
    table_fqn: str,
    results: Sequence[CheckResult],
    show_details: bool,
) -> None:
    ok    = sum(1 for r in results if r.severity == Severity.OK)
    warn  = sum(1 for r in results if r.severity == Severity.WARN)
    error = sum(1 for r in results if r.severity == Severity.ERROR)
    total = len(results)

    score                = _health_score(ok, warn, total)
    status, status_color = _status_label(error, warn)

    # ── Header box ──────────────────────────────────────────────────────────
    title = "ICEBERG TABLE HEALTH CHECK REPORT"
    width = len(title) + 4
    out.print()
    out.print(f"[bold]┌{'─' * (width - 2)}┐[/bold]")
    out.print(f"[bold]│ {title} │[/bold]")
    out.print(f"[bold]└{'─' * (width - 2)}┘[/bold]")

    # ── Table identifier ────────────────────────────────────────────────────
    out.print(f"\n[bold]TABLE:[/bold] [cyan]{table_fqn}[/cyan]\n")

    # ── Checks ──────────────────────────────────────────────────────────────
    out.print("[bold]CHECKS:[/bold]")
    out.print(_SEP)

    for r in results:
        icon_markup, status_text = _ICON[r.severity]
        out.print(f"{icon_markup} [bold]{r.check_name:<30}[/bold] {status_text}")
        if show_details and r.details:
            detail_str = json.dumps(r.details, indent=2, default=str)
            for line in detail_str.splitlines():
                out.print(f"   [dim]{line}[/dim]")

    out.print(_SEP)

    # ── Score and status ────────────────────────────────────────────────────
    out.print(f"\n[bold]HEALTH SCORE:[/bold] {score} / 100")
    out.print(f"[bold]STATUS:[/bold] [{status_color}]{status}[/{status_color}]")

    # ── Recommendations ─────────────────────────────────────────────────────
    recs = _build_recommendations(results)
    if recs:
        out.print("\n[bold]RECOMMENDATIONS:[/bold]")
        for i, rec in enumerate(recs, 1):
            out.print(f"  {i}. {rec}")

    # ── AI Insight ──────────────────────────────────────────────────────────
    insight = _ai_insight(results)
    wrapped = textwrap.fill(insight, width=70)
    out.print(f"\n[bold cyan]AI INSIGHT:[/bold cyan]")
    for line in wrapped.splitlines():
        out.print(f"  [italic]{line}[/italic]")

    out.print()


def print_report(
    table_fqn: str,
    results: Sequence[CheckResult],
    show_details: bool = False,
    output_file: str | None = None,
    fmt: str = "text",
) -> int:
    """Render the health report. Returns 0 if healthy/degraded, 1 if any ERROR."""
    has_error = any(r.severity == Severity.ERROR for r in results)

    if fmt == "json":
        ok    = sum(1 for r in results if r.severity == Severity.OK)
        warn  = sum(1 for r in results if r.severity == Severity.WARN)
        error = sum(1 for r in results if r.severity == Severity.ERROR)
        status, _ = _status_label(error, warn)
        payload = {
            "table": table_fqn,
            "status": status,
            "health_score": _health_score(ok, warn, len(results)),
            "checks": [
                {
                    "name": r.check_name,
                    "severity": r.severity.value,
                    "message": r.message,
                    "details": r.details,
                }
                for r in results
            ],
            "recommendations": _build_recommendations(results),
            "ai_insight": _ai_insight(results),
        }
        output = json.dumps(payload, indent=2, default=str)
        console.print(output)
        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(output)
            console.print(f"[dim]Report saved to {output_file}[/dim]")
        return 1 if has_error else 0

    # Text mode — render to terminal
    _render(console, table_fqn, results, show_details)

    # Optionally save plain-text copy
    if output_file:
        recording = Console(record=True, width=120, legacy_windows=False)
        _render(recording, table_fqn, results, show_details)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(recording.export_text())
        console.print(f"[dim]Report saved to {output_file}[/dim]")

    return 1 if has_error else 0
