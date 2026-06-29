# Snowflake Iceberg Table Health Checker

> **phData DE India AI Skill-a-thon** — Team: Chetan Gouda B Patil
> Theme: *AI First. Build Once. Reuse Everywhere.*

A reusable AI Skill that diagnoses Snowflake Iceberg table health.
The CLI tool collects health signals; Claude interprets them, explains root causes, and generates ready-to-run remediation SQL.

---

## Quick Start

```bash
# 1. Install
pip install -r requirements.txt
pip install -e . --no-deps

# 2. Configure credentials
cp .env.example .env   # fill in your Snowflake account, user, password

# 3. Run a health check
iceberg-health check MYDB.MYSCHEMA.MY_TABLE

# 4. Get AI-powered diagnosis (paste JSON output into Claude with Skill.md active)
iceberg-health check MYDB.MYSCHEMA.MY_TABLE --format json
```

---

## What It Checks

| Check | Snowflake Source | Flags |
|---|---|---|
| `table_exists` | `INFORMATION_SCHEMA.TABLES` | Table not found or wrong type |
| `iceberg_table_information` | `SYSTEM$GET_ICEBERG_TABLE_INFORMATION` | NULL result or unparseable JSON |
| `metadata_location` | Table info JSON | Missing metadata pointer (P0) |
| `current_snapshot` | Table info JSON | No current snapshot (table never written) |
| `snapshot_history` | `INFORMATION_SCHEMA.ICEBERG_SNAPSHOT_INFORMATION` | 0 snapshots or >100 unexpired |
| `column_metadata` | `DESCRIBE TABLE` | Schema unreadable or empty |

---

## CLI Reference

```bash
# Check a table (text report)
iceberg-health check MYDB.MYSCHEMA.MY_TABLE

# Check with AI-ready JSON output
iceberg-health check MYDB.MYSCHEMA.MY_TABLE --format json

# Preview checks without connecting to Snowflake
iceberg-health check MYDB.MYSCHEMA.MY_TABLE --dry-run

# Show raw check details
iceberg-health check MYDB.MYSCHEMA.MY_TABLE --details

# Save report to file
iceberg-health check MYDB.MYSCHEMA.MY_TABLE --output report.txt

# List tables in a database
iceberg-health list-tables --database MYDB --schema MYSCHEMA
```

---

## AI-Powered Workflow

```
┌─────────────────────────────────────────────────────┐
│  1. Run iceberg-health check TABLE --format json    │
│     → Collects 6 health signals from Snowflake      │
├─────────────────────────────────────────────────────┤
│  2. Paste JSON output into Claude (Skill.md active) │
│     → Claude diagnoses root cause                   │
│     → Claude generates prioritized remediation SQL  │
├─────────────────────────────────────────────────────┤
│  3. Run the generated SQL in Snowflake              │
│     → Re-run health check to verify                 │
└─────────────────────────────────────────────────────┘
```

---

## Example Output

```
╭──────────────────────────────────────────────────────────╮
│ Snowflake Iceberg Table Health Report                    │
│ Table: MYDB.MYSCHEMA.MY_TABLE                            │
│ Overall: HEALTHY  6 OK  0 WARN  0 ERROR                  │
╰──────────────────────────────────────────────────────────╯

  ✔  table_exists               Table exists (type: ICEBERG TABLE).
  ✔  iceberg_table_information  SYSTEM$GET_ICEBERG_TABLE_INFORMATION returned valid JSON.
  ✔  metadata_location          metadata-location present: s3://bucket/path/metadata.json
  ✔  current_snapshot           Current snapshot ID: 8675309
  ✔  snapshot_history           12 snapshot(s) found. Latest: 2024-06-01, Oldest: 2024-01-15.
  ✔  column_metadata            5 column(s) defined.
```

---

## Programmatic Use

```python
from iceberg_checker import get_connection, run_metadata_checks, CheckFunction

# Built-in checks
conn = get_connection()
results = run_metadata_checks(conn, "MYDB", "MYSCHEMA", "MY_TABLE")

# Custom check (implements CheckFunction protocol)
def my_row_count_check(conn, database, schema, table):
    cur = conn.cursor()
    try:
        cur.execute(f'SELECT COUNT(*) FROM "{database}"."{schema}"."{table}"')
        (count,) = cur.fetchone()
    finally:
        cur.close()
    from iceberg_checker import CheckResult, Severity
    severity = Severity.WARN if count == 0 else Severity.OK
    return [CheckResult("row_count", severity, f"{count:,} rows.")]
```

---

## Configuration

| Variable | Required | Description |
|---|---|---|
| `SNOWFLAKE_ACCOUNT` | Yes | Account identifier (e.g. `myorg-myaccount`) |
| `SNOWFLAKE_USER` | Yes | Login username |
| `SNOWFLAKE_PASSWORD` | Yes | Password |
| `SNOWFLAKE_ROLE` | No | Role (defaults to account default) |
| `SNOWFLAKE_WAREHOUSE` | No | Warehouse |
| `SNOWFLAKE_DATABASE` | No | Default database |
| `SNOWFLAKE_SCHEMA` | No | Default schema |

---

## Running Tests

```bash
pip install -e ".[dev]" --no-deps
pytest          # 26 tests — no real Snowflake connection required
```

---

## Submission Files

| File | Purpose |
|---|---|
| [`Skill.md`](Skill.md) | AI skill prompt + full submission details |
| [`References.md`](References.md) | Snowflake, Iceberg, and library references |
| [`src/iceberg_checker/`](src/iceberg_checker/) | Python scripts (CLI tool) |
| [`.github/workflows/ci.yml`](.github/workflows/ci.yml) | CI pipeline (Python 3.9–3.12) |
