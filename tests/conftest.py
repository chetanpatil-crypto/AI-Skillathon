"""Shared pytest fixtures."""
import json
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def make_conn():
    """Factory: build a mock Snowflake connection with canned cursor responses.

    Each call to conn.cursor() returns the same mock cursor, so fetchone
    side_effect drives the sequence across all check functions.
    """
    def _factory(fetchone_sequence=None, fetchall=None):
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value = cur
        if fetchone_sequence is not None:
            cur.fetchone.side_effect = list(fetchone_sequence)
        if fetchall is not None:
            cur.fetchall.return_value = fetchall
        return conn

    return _factory


@pytest.fixture
def healthy_info():
    return json.dumps({
        "metadataLocation": "s3://bucket/path/metadata.json",
        "currentSnapshotId": 1234567890,
    })
