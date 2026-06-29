# References

Curated resources used to build and validate the Snowflake Iceberg Table Health Checker skill.

---

## Snowflake Documentation

| Resource | Description |
|---|---|
| [Iceberg Tables Overview](https://docs.snowflake.com/en/user-guide/tables-iceberg) | Official guide to Snowflake-managed and externally managed Iceberg tables |
| [SYSTEM$GET_ICEBERG_TABLE_INFORMATION](https://docs.snowflake.com/en/sql-reference/functions/system_get_iceberg_table_information) | System function used in the `iceberg_table_information` check |
| [ICEBERG_SNAPSHOT_INFORMATION](https://docs.snowflake.com/en/sql-reference/info-schema/iceberg_snapshot_information) | INFORMATION_SCHEMA table function used in the `snapshot_history` check |
| [ALTER ICEBERG TABLE … REFRESH](https://docs.snowflake.com/en/sql-reference/sql/alter-iceberg-table) | SQL command to refresh metadata pointer — primary P0 remediation |
| [ALTER ICEBERG TABLE … EXPIRE SNAPSHOTS](https://docs.snowflake.com/en/sql-reference/sql/alter-iceberg-table-expire-snapshots) | Maintenance command for snapshot pruning |
| [External Volumes](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-external-vol) | Configuring S3/ADLS/GCS external volumes for Iceberg tables |
| [Storage Integrations](https://docs.snowflake.com/en/user-guide/data-load-s3-config-storage-integration) | IAM/SAS setup for Snowflake to access external storage |
| [INFORMATION_SCHEMA.TABLES](https://docs.snowflake.com/en/sql-reference/info-schema/tables) | Used in the `table_exists` check |
| [DESCRIBE TABLE](https://docs.snowflake.com/en/sql-reference/sql/desc-table) | Used in the `column_metadata` check |
| [Iceberg Table Privileges](https://docs.snowflake.com/en/user-guide/security-access-control-privileges#iceberg-table-privileges) | Required privileges for running health checks |

---

## Apache Iceberg Specification

| Resource | Description |
|---|---|
| [Iceberg Table Spec v2](https://iceberg.apache.org/spec/) | Formal spec defining metadata files, snapshot model, and manifest structure |
| [Iceberg Metadata Files](https://iceberg.apache.org/spec/#table-metadata) | How `metadata.json` is structured and what `metadata-location` points to |
| [Iceberg Snapshots](https://iceberg.apache.org/spec/#snapshots) | Snapshot model — currentSnapshotId, snapshot expiry, and history |
| [Iceberg Schema Evolution](https://iceberg.apache.org/docs/latest/evolution/) | How schema changes work and why column metadata checks matter |

---

## Python Libraries

| Library | Version | Purpose |
|---|---|---|
| [snowflake-connector-python](https://pypi.org/project/snowflake-connector-python/) | 4.6.0 | Snowflake connection and query execution |
| [click](https://click.palletsprojects.com/) | 8.4.2 | CLI framework |
| [rich](https://rich.readthedocs.io/) | 15.0.0 | Terminal formatting and table rendering |
| [python-dotenv](https://pypi.org/project/python-dotenv/) | 1.2.2 | `.env` file credential loading |

---

## AI Model Reference

| Resource | Description |
|---|---|
| [claude-sonnet-4-6](https://www.anthropic.com/claude) | Recommended model — balances speed and reasoning depth for diagnostic tasks |
| [Claude Tool Use](https://docs.anthropic.com/en/docs/build-with-claude/tool-use) | How the skill integrates with Claude's tool use for programmatic pipelines |
| [Anthropic Skills Authoring Guide](https://docs.anthropic.com/) | Best practices followed when writing the skill prompt |

---

## Related Tools and Patterns

| Resource | Description |
|---|---|
| [dbt-snowflake](https://docs.getdbt.com/docs/core/connect-data-platform/snowflake-setup) | dbt integration — Iceberg health checks complement dbt source freshness checks |
| [Snowflake Task Scheduling](https://docs.snowflake.com/en/user-guide/tasks-intro) | Used to automate nightly EXPIRE SNAPSHOTS (see Skill.md Example 2) |
| [Iceberg REST Catalog](https://iceberg.apache.org/concepts/catalog/) | Alternative catalog pattern relevant for externally managed Iceberg tables |
| [PEP 561 — py.typed](https://peps.python.org/pep-0561/) | Python typed library marker used in this project |
| [pytest](https://docs.pytest.org/) | Test framework — 26 tests covering all check paths and CLI integration |
