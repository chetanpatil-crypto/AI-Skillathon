"""CLI entrypoint for the Iceberg table health checker."""
from __future__ import annotations

import re
import sys

import click
from rich.console import Console
from rich.table import Table as RichTable
from rich import box as rbox

from . import __version__
from .checks import run_metadata_checks
from .connection import get_connection
from .reporter import print_report

console = Console()

_IDENTIFIER_RE = re.compile(r'^[A-Za-z0-9_$]+$')


def _validate_identifier(value: str, label: str) -> None:
    """Raise UsageError if value contains characters unsafe for a Snowflake identifier."""
    if not _IDENTIFIER_RE.match(value):
        raise click.UsageError(
            f"Invalid {label} '{value}': Snowflake identifiers may only contain "
            "letters, digits, underscores, and dollar signs."
        )


@click.group(no_args_is_help=True)
@click.version_option(version=__version__, prog_name="iceberg-health")
def main() -> None:
    """Snowflake Iceberg Table Health Checker."""


_DRY_RUN_CHECKS = [
    ("table_exists",              "INFORMATION_SCHEMA.TABLES"),
    ("iceberg_table_information", "SYSTEM$GET_ICEBERG_TABLE_INFORMATION"),
    ("metadata_location",         "metadata-location in table info JSON"),
    ("current_snapshot",          "currentSnapshotId in table info JSON"),
    ("snapshot_history",          "INFORMATION_SCHEMA.ICEBERG_SNAPSHOT_INFORMATION"),
    ("column_metadata",           "DESCRIBE TABLE"),
]


def _print_dry_run(
    database: str,
    schema: str,
    table: str,
    account: str | None,
    fmt: str,
) -> None:
    fqn = f"{database}.{schema}.{table}"
    if fmt == "json":
        import json as _json
        console.print(_json.dumps({
            "mode": "dry-run",
            "table": fqn,
            "account": account or "(from env)",
            "checks": [{"name": n, "source": s} for n, s in _DRY_RUN_CHECKS],
        }, indent=2))
        return

    from rich.panel import Panel
    from rich import box
    console.print()
    console.print(Panel(
        f"[bold]Dry Run - no connection made[/bold]\n"
        f"Table : [cyan]{fqn}[/cyan]\n"
        f"Account: [dim]{account or 'from env'}[/dim]",
        box=box.ROUNDED,
        border_style="dim",
    ))
    tbl = RichTable(box=rbox.SIMPLE, show_header=True, header_style="bold dim", expand=True)
    tbl.add_column("#", width=3, justify="right", style="dim", no_wrap=True)
    tbl.add_column("Check", no_wrap=True)
    tbl.add_column("Snowflake source")
    for i, (name, source) in enumerate(_DRY_RUN_CHECKS, 1):
        tbl.add_row(str(i), name, source)
    console.print(tbl)
    console.print(f"[dim]{len(_DRY_RUN_CHECKS)} checks would run. Remove --dry-run to execute.[/dim]\n")


@main.command("check")
@click.argument("table")
@click.option("--database", "-d", envvar="SNOWFLAKE_DATABASE", help="Snowflake database name.")
@click.option("--schema", "-s", envvar="SNOWFLAKE_SCHEMA", help="Snowflake schema name.")
@click.option("--account", envvar="SNOWFLAKE_ACCOUNT", help="Snowflake account identifier.")
@click.option("--user", "-u", envvar="SNOWFLAKE_USER", help="Snowflake username.")
@click.option("--password", envvar="SNOWFLAKE_PASSWORD", help="Snowflake password.", hide_input=True)
@click.option("--role", envvar="SNOWFLAKE_ROLE", help="Snowflake role.")
@click.option("--warehouse", "-w", envvar="SNOWFLAKE_WAREHOUSE", help="Snowflake warehouse.")
@click.option("--details", is_flag=True, default=False, help="Show raw check details.")
@click.option("--output", "-o", default=None, help="Write report to a file.")
@click.option(
    "--format", "fmt",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--dry-run", "dry_run",
    is_flag=True,
    default=False,
    help="Show which checks would run without connecting to Snowflake.",
)
def check_cmd(
    table: str,
    database: str | None,
    schema: str | None,
    account: str | None,
    user: str | None,
    password: str | None,
    role: str | None,
    warehouse: str | None,
    details: bool,
    output: str | None,
    fmt: str,
    dry_run: bool,
) -> None:
    """Run health checks on an Iceberg TABLE (name only, or db.schema.table)."""
    parts = table.split(".")
    if len(parts) == 3:
        database = database or parts[0]
        schema = schema or parts[1]
        table = parts[2]
    elif len(parts) == 2:
        schema = schema or parts[0]
        table = parts[1]

    if not database:
        raise click.UsageError("Database is required. Use --database or SNOWFLAKE_DATABASE env var.")
    if not schema:
        raise click.UsageError("Schema is required. Use --schema or SNOWFLAKE_SCHEMA env var.")

    _validate_identifier(database, "database")
    _validate_identifier(schema, "schema")
    _validate_identifier(table, "table")

    if dry_run:
        _print_dry_run(database, schema, table, account, fmt)
        return

    console.print(f"[dim]Connecting to Snowflake ({account or 'from env'})...[/dim]")
    try:
        conn = get_connection(
            account=account,
            user=user,
            password=password,
            role=role,
            warehouse=warehouse,
            database=database,
            schema=schema,
        )
    except Exception as exc:
        console.print(f"[red]Connection failed:[/red] {exc}")
        sys.exit(2)

    console.print(f"[dim]Running checks on [cyan]{database}.{schema}.{table}[/cyan]...[/dim]")
    try:
        results = run_metadata_checks(conn, database, schema, table)
    finally:
        conn.close()

    exit_code = print_report(
        f"{database}.{schema}.{table}",
        results,
        show_details=details,
        output_file=output,
        fmt=fmt,
    )
    sys.exit(exit_code)


@main.command("list-tables")
@click.option("--database", "-d", envvar="SNOWFLAKE_DATABASE", required=True, help="Snowflake database.")
@click.option("--schema", "-s", envvar="SNOWFLAKE_SCHEMA", help="Filter by schema (optional).")
@click.option("--account", envvar="SNOWFLAKE_ACCOUNT", help="Snowflake account identifier.")
@click.option("--user", "-u", envvar="SNOWFLAKE_USER", help="Snowflake username.")
@click.option("--password", envvar="SNOWFLAKE_PASSWORD", hide_input=True, help="Snowflake password.")
@click.option("--role", envvar="SNOWFLAKE_ROLE", help="Snowflake role.")
@click.option("--warehouse", "-w", envvar="SNOWFLAKE_WAREHOUSE", help="Snowflake warehouse.")
def list_tables_cmd(
    database: str,
    schema: str | None,
    account: str | None,
    user: str | None,
    password: str | None,
    role: str | None,
    warehouse: str | None,
) -> None:
    """List tables in a database (or schema)."""
    _validate_identifier(database, "database")
    if schema:
        _validate_identifier(schema, "schema")

    console.print("[dim]Connecting...[/dim]")
    try:
        conn = get_connection(
            account=account, user=user, password=password,
            role=role, warehouse=warehouse, database=database, schema=schema,
        )
    except Exception as exc:
        console.print(f"[red]Connection failed:[/red] {exc}")
        sys.exit(2)

    cur = conn.cursor()
    try:
        if schema:
            cur.execute(
                f"""
                SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE, CREATED, LAST_ALTERED
                FROM {database.upper()}.INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = %s
                  AND TABLE_TYPE IN ('EXTERNAL TABLE', 'BASE TABLE')
                ORDER BY TABLE_SCHEMA, TABLE_NAME
                """,
                (schema.upper(),),
            )
        else:
            cur.execute(
                f"""
                SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE, CREATED, LAST_ALTERED
                FROM {database.upper()}.INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE IN ('EXTERNAL TABLE', 'BASE TABLE')
                ORDER BY TABLE_SCHEMA, TABLE_NAME
                """
            )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    if not rows:
        console.print("[yellow]No tables found.[/yellow]")
        return

    tbl = RichTable(box=rbox.SIMPLE, show_header=True, header_style="bold dim")
    tbl.add_column("Database")
    tbl.add_column("Schema")
    tbl.add_column("Table")
    tbl.add_column("Type")
    tbl.add_column("Created")

    for row in rows:
        tbl.add_row(row[0], row[1], row[2], row[3], str(row[4]))

    console.print(tbl)


if __name__ == "__main__":
    main()
