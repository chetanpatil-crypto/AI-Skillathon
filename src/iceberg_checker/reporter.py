"""Render health check results to the terminal and/or a file."""
from __future__ import annotations

import json
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

    score               = _health_score(ok, warn, total)
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
