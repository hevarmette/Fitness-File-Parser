"""Round-trip DB tests for the parameterized insert path (:mod:`db_insert`).

Marked ``@pytest.mark.db`` so the whole module auto-skips when ``DB_UI_LOCAL``
is unset (see ``conftest.pytest_collection_modifyitems``). When a database is
configured, each test builds an isolated throwaway schema, inserts through the
real ``db_insert`` functions, reads the rows back, and drops the schema.

The point is to prove:

* ``NaN``/``NaT``/absent columns land as SQL ``NULL``.
* Apostrophe / SQL-like text inserts verbatim via parameter binding (no
  injection, no early string termination).
* ``activity`` returns its generated ``activity_id`` and honors
  ``ON CONFLICT (activity_id) DO NOTHING``.
* The ``record`` table's ``COPY`` path stores the same values an INSERT would.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import numpy as np
import pandas as pd
import psycopg
import pytest

from db_insert import insert_activity, insert_table

pytestmark = pytest.mark.db


def _fetchone(cur: psycopg.Cursor) -> tuple:
    """Fetch exactly one row, asserting it exists (keeps mypy happy in tests)."""
    row = cur.fetchone()
    assert row is not None
    return row


# Minimal subset of schema_garmin_data.sql needed for the round-trip tests,
# created inside a throwaway schema so no real data is touched.
_SCHEMA_DDL = """
CREATE TABLE activity (
    activity_id bigserial NOT NULL,
    "timestamp" timestamp with time zone,
    adjusted_distance real,
    adjusted_duration real,
    workout_feel smallint,
    effort smallint,
    category char(15),
    activity_name text,
    description text,
    total_timer_time real,
    local_timestamp timestamp without time zone,
    num_sessions integer,
    type character varying(50),
    event character varying(50),
    event_type character varying(50),
    event_group smallint,
    PRIMARY KEY (activity_id)
);
CREATE TABLE record (
    record_id bigserial NOT NULL,
    activity_id bigint NOT NULL,
    latitude double precision,
    longitude double precision,
    lap smallint,
    altitude real,
    "timestamp" timestamp with time zone,
    heart_rate smallint,
    cadence smallint,
    fractional_cadence DECIMAL(1,1),
    enhanced_speed real,
    distance real,
    PRIMARY KEY (record_id)
);
CREATE TABLE event (
    event_id serial NOT NULL,
    activity_id bigint NOT NULL,
    "timestamp" timestamp with time zone,
    event character varying(50),
    event_type character varying(50),
    data character varying(50),
    event_group smallint,
    PRIMARY KEY (event_id)
);
"""


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    """Yield a connection scoped to a fresh throwaway schema, then drop it."""
    database_url = os.environ["DB_UI_LOCAL"]
    schema = f"fitparser_test_{uuid.uuid4().hex[:8]}"
    connection = psycopg.connect(database_url)
    try:
        with connection.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET search_path TO "{schema}"')
            cur.execute(_SCHEMA_DDL)
        connection.commit()
        # Keep search_path pointed at the throwaway schema for the test body.
        with connection.cursor() as cur:
            cur.execute(f'SET search_path TO "{schema}"')
        connection.commit()
        yield connection
    finally:
        connection.rollback()
        with connection.cursor() as cur:
            cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        connection.commit()
        connection.close()


def test_activity_returns_id_and_conflict_no_dup(conn: psycopg.Connection) -> None:
    """activity insert returns the id; a second insert of the same id is a no-op."""
    df = pd.DataFrame(
        [
            {
                "activity_id": 5001,
                "timestamp": "2025-01-01T00:00:00+00:00",
                "total_timer_time": 600.0,
                "num_sessions": 1,
                "type": "manual",
                "event": "activity",
                "event_type": "stop",
                "activity_name": "O'Brien Park Run",  # apostrophe must survive
                "description": np.nan,  # NaN → NULL
            }
        ]
    )
    new_id = insert_activity(df, conn)
    assert new_id == 5001

    # Re-inserting the same activity_id hits ON CONFLICT DO NOTHING → None.
    dup_id = insert_activity(df, conn)
    assert dup_id is None

    with conn.cursor() as cur:
        cur.execute("SELECT activity_name, description FROM activity WHERE activity_id = 5001")
        name, description = _fetchone(cur)
        cur.execute("SELECT COUNT(*) FROM activity WHERE activity_id = 5001")
        (count,) = _fetchone(cur)

    assert name == "O'Brien Park Run"  # apostrophe stored verbatim
    assert description is None  # NaN became NULL
    assert count == 1  # conflict did not duplicate


def test_event_executemany_null_and_apostrophe(conn: psycopg.Connection) -> None:
    """event insert via executemany: NaN → NULL, SQL-like text bound safely."""
    # A parent activity is required for FK-free schema here, but our test event
    # table has no FK constraint, so we can insert directly.
    df = pd.DataFrame(
        [
            {
                "activity_id": 42,
                "timestamp": "2025-01-01T00:00:00+00:00",
                "event": "timer",
                "event_type": "start",
                "data": "'); DROP TABLE event;--",  # injection attempt
                "event_group": np.nan,
            },
            {
                "activity_id": 42,
                "timestamp": "2025-01-01T00:01:00+00:00",
                "event": "timer",
                "event_type": "stop",
                "data": "O'Brien",
                "event_group": 3,
            },
        ]
    )
    assert insert_table(df, "event", conn) is True

    with conn.cursor() as cur:
        cur.execute("SELECT data, event_group FROM event ORDER BY event_id")
        rows = cur.fetchall()

    assert rows[0] == ("'); DROP TABLE event;--", None)  # bound as data, not executed
    assert rows[1] == ("O'Brien", 3)
    # Table still exists (injection did not run).
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM event")
        (count,) = _fetchone(cur)
    assert count == 2


def test_record_copy_path(conn: psycopg.Connection) -> None:
    """record insert uses COPY and stores the same values an INSERT would."""
    df = pd.DataFrame(
        [
            {
                "activity_id": 42,
                "latitude": 51.5,
                "longitude": -0.12,
                "lap": 1,
                "altitude": 10.0,
                "timestamp": pd.Timestamp("2025-01-01T00:00:01", tz="UTC"),
                "heart_rate": 120,
                "cadence": 80,
                "fractional_cadence": 0.5,
                "enhanced_speed": 3.2,
                "distance": 5.0,
            },
            {
                "activity_id": 42,
                "latitude": np.nan,  # NaN → NULL
                "longitude": np.nan,
                "lap": 1,
                "altitude": 11.0,
                "timestamp": pd.Timestamp("2025-01-01T00:00:02", tz="UTC"),
                "heart_rate": 121,
                "cadence": 81,
                "fractional_cadence": 0.5,
                "enhanced_speed": 3.3,
                "distance": 6.0,
            },
        ]
    )
    assert insert_table(df, "record", conn) is True

    with conn.cursor() as cur:
        cur.execute("SELECT latitude, distance FROM record ORDER BY record_id")
        rows = cur.fetchall()

    assert rows[0][0] == 51.5
    assert rows[1][0] is None  # NaN became NULL via COPY
    assert rows[1][1] == 6.0
