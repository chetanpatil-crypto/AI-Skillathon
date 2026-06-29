from __future__ import annotations

import os

import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

_REQUIRED = {
    "SNOWFLAKE_ACCOUNT": "account identifier (e.g. myorg-myaccount)",
    "SNOWFLAKE_USER": "username",
    "SNOWFLAKE_PASSWORD": "password",
}


def _require_env(key: str, override: str | None) -> str:
    if override:
        return override
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"Missing required credential: {key} ({_REQUIRED.get(key, '')}). "
            f"Set it in .env or pass the corresponding CLI flag."
        )
    return value


def get_connection(
    account: str | None = None,
    user: str | None = None,
    password: str | None = None,
    role: str | None = None,
    warehouse: str | None = None,
    database: str | None = None,
    schema: str | None = None,
    login_timeout: int = 30,
    network_timeout: int = 60,
) -> snowflake.connector.SnowflakeConnection:
    """Return an authenticated Snowflake connection, falling back to env vars.

    Args:
        login_timeout: Seconds to wait for the login handshake (default 30).
        network_timeout: Seconds to wait for query responses (default 60).
    """
    return snowflake.connector.connect(
        account=_require_env("SNOWFLAKE_ACCOUNT", account),
        user=_require_env("SNOWFLAKE_USER", user),
        password=_require_env("SNOWFLAKE_PASSWORD", password),
        role=role or os.getenv("SNOWFLAKE_ROLE"),          # None = use account default role
        warehouse=warehouse or os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=database or os.getenv("SNOWFLAKE_DATABASE"),
        schema=schema or os.getenv("SNOWFLAKE_SCHEMA"),
        login_timeout=login_timeout,
        network_timeout=network_timeout,
        session_parameters={"QUOTED_IDENTIFIERS_IGNORE_CASE": "TRUE"},
    )
