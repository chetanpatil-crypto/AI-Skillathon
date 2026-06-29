"""Render health check results to the terminal and/or a file."""
from __future__ import annotations

import json
from typing import Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.text import Text

from .checks.metadata import CheckResult, Severity

_SEVERITY_ICON = {
    Severity.OK: "[green]✔[/green]",
    Severity.WARN: "[yellow]⚠[/yellow]",
    Severity.ERROR: "[red]✘[/red]",
}

console = Console()


def _render(
    out: Console,
    table_fqn: str,
    results: Sequence[CheckResult],
    show_details: bool,
) -> None:
    ok = sum(1 for r in results if r.severity == Severity.OK)
    warn = sum(1 for r in results if r.severity == Severity.WARN)
    error = sum(1 for r in results if r.severity == Severity.ERROR)

    overall_color = "green" if error == 0 and warn == 0 else ("yellow" if error == 0 else "red")
    overall_label = "HEALTHY" if error == 0 and warn == 0 else ("DEGRADED" if error == 0 else "UNHEALTHY")

    out.print()
    out.print(
        Panel(
            f"[bold]Snowflake Iceberg Table Health Report[/bold]\n"
            f"Table: [cyan]{table_fqn}[/cyan]\n"
            f"Overall: [{overall_color}]{overall_label}[/{overall_color}]  "
            f"[green]{ok} OK[/green]  [yellow]{warn} WARN[/yellow]  [red]{error} ERROR[/red]",
            box=box.ROUNDED,
            border_style=overall_color,
        )
    )

    tbl = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
    tbl.add_column("Status", width=6, justify="center")
    tbl.add_column("Check", style="bold")
    tbl.add_column("Message")

    for r in results:
        tbl.add_row(_SEVERITY_ICON[r.severity], r.check_name, r.message)
        if show_details and r.details:
            tbl.add_row("", "", Text(json.dumps(r.details, indent=2, default=str), style="dim"))

    out.print(tbl)


def print_report(
    table_fqn: str,
    results: Sequence[CheckResult],
    show_details: bool = False,
    output_file: str | None = None,
    fmt: str = "text",
) -> int:
    """Render the health report. Returns 0 if no errors, 1 if any errors found."""
    has_error = any(r.severity == Severity.ERROR for r in results)

    if fmt == "json":
        payload = {
            "table": table_fqn,
            "status": "UNHEALTHY" if has_error else "HEALTHY",
            "checks": [
                {
                    "name": r.check_name,
                    "severity": r.severity.value,
                    "message": r.message,
                    "details": r.details,
                }
                for r in results
            ],
        }
        output = json.dumps(payload, indent=2, default=str)
        console.print(output)
        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(output)
            console.print(f"[dim]Report saved to {output_file}[/dim]")
        return 1 if has_error else 0

    # Always render to terminal
    _render(console, table_fqn, results, show_details)

    # Additionally save a plain-text copy if requested
    if output_file:
        recording = Console(record=True, width=120)
        _render(recording, table_fqn, results, show_details)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(recording.export_text())
        console.print(f"[dim]Report saved to {output_file}[/dim]")

    return 1 if has_error else 0
