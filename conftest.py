"""Root conftest: stub out snowflake.connector before any module imports it.

This lets the test suite run without the snowflake-connector-python C extension
installed (which requires MSVC on Windows). All actual connector usage in tests
is replaced by MagicMock objects.
"""
import sys
import types
from unittest.mock import MagicMock

# Build a minimal fake snowflake package hierarchy
_snowflake = types.ModuleType("snowflake")
_connector = types.ModuleType("snowflake.connector")

# SnowflakeConnection is used only as a type annotation in function signatures
_connector.SnowflakeConnection = MagicMock
_connector.connect = MagicMock(return_value=MagicMock())

_snowflake.connector = _connector
sys.modules.setdefault("snowflake", _snowflake)
sys.modules.setdefault("snowflake.connector", _connector)
