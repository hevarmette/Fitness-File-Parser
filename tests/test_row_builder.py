"""Unit tests for the shared row-builder in :mod:`sql_rows`.

These cover :func:`sql_rows.dataframe_to_rows` for all 7 Garmin tables plus the
dynamic ``activity`` column order and the safe value formatter. The key
invariants are:

* Values come out in the exact column order the INSERT uses.
* ``NaN`` / ``NaT`` / absent columns all normalize to ``None`` (SQL ``NULL``).
* Non-missing text passes through unchanged (the DB driver binds it safely;
  no manual escaping happens in the row-builder).
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from sql_rows import (
    ACTIVITY_COLUMNS_NO_ID,
    TABLE_COLUMNS,
    activity_columns,
    dataframe_to_rows,
    format_sql_value,
    strip_local_timestamp_tz,
)
from watch_files_to_sql import write_sql_statement_to_file


def test_table_columns_covers_six_fixed_tables() -> None:
    """The fixed-column tables are all present with activity_id first."""
    assert set(TABLE_COLUMNS) == {"session", "lap", "record", "file_id", "length", "event"}
    for cols in TABLE_COLUMNS.values():
        assert cols[0] == "activity_id"


def test_activity_columns_toggle_id() -> None:
    """activity column order includes activity_id only when requested."""
    assert activity_columns(include_id=False) == ACTIVITY_COLUMNS_NO_ID
    assert activity_columns(include_id=True) == ["activity_id", *ACTIVITY_COLUMNS_NO_ID]


def test_record_rows_fixed_order() -> None:
    """record: values emerge in the column order regardless of input order."""
    df = pd.DataFrame(
        [
            {
                "distance": 5.0,  # deliberately out of order
                "activity_id": 42,
                "latitude": 51.5,
                "longitude": -0.12,
                "lap": 1,
                "altitude": 10.0,
                "timestamp": "2025-01-01T00:00:01",
                "heart_rate": 120,
                "cadence": 80,
                "fractional_cadence": 0.5,
                "enhanced_speed": 3.2,
            }
        ]
    )
    rows = dataframe_to_rows(df, TABLE_COLUMNS["record"])
    assert rows == [(42, 51.5, -0.12, 1, 10.0, "2025-01-01T00:00:01", 120, 80, 0.5, 3.2, 5.0)]


def test_lap_rows_nan_becomes_none() -> None:
    """lap: NaN power → None; apostrophe text is passed through verbatim."""
    df = pd.DataFrame(
        [
            {
                "activity_id": 42,
                "number": 1,
                "start_time": "2025-01-01T00:00:00",
                "total_distance": 100.0,
                "intensity": "O'Brien",
                "avg_power": np.nan,
                "max_power": 250,
            }
        ]
    )
    (row,) = dataframe_to_rows(df, TABLE_COLUMNS["lap"])
    columns = TABLE_COLUMNS["lap"]
    by_name = dict(zip(columns, row))
    assert by_name["intensity"] == "O'Brien"  # not escaped — binding does that
    assert by_name["avg_power"] is None  # NaN → None
    assert by_name["max_power"] == 250
    # Absent columns (e.g. total_ascent) come through as None.
    assert by_name["total_ascent"] is None


def test_session_missing_columns_become_none() -> None:
    """session: absent columns and NaN both normalize to None."""
    df = pd.DataFrame(
        [
            {
                "activity_id": 42,
                "timestamp": "2025-01-01T00:10:00",
                "start_time": "2025-01-01T00:00:00",
                "start_position_lat": 51.5,
                "start_position_long": -0.12,
                "total_elapsed_time": 600.0,
                "total_timer_time": 590.0,
                "total_distance": 2000.0,
                "total_strokes": np.nan,
                "sport": "running",
                "sub_sport": "generic",
                "event": "session",
                "event_type": "stop",
                "trigger": "activity_end",
            }
        ]
    )
    (row,) = dataframe_to_rows(df, TABLE_COLUMNS["session"])
    by_name = dict(zip(TABLE_COLUMNS["session"], row))
    assert by_name["total_strokes"] is None  # NaN
    assert by_name["avg_power"] is None  # absent column
    assert by_name["sport"] == "running"
    assert by_name["trigger"] == "activity_end"


def test_file_id_rows() -> None:
    """file_id: NaN number → None, text values pass through."""
    df = pd.DataFrame(
        [
            {
                "activity_id": 42,
                "type": "activity",
                "manufacturer": "garmin",
                "product": "Forerunner O'Neil",
                "serial_number": 123,
                "time_created": "2025-01-01T00:00:00",
                "number": np.nan,
            }
        ]
    )
    (row,) = dataframe_to_rows(df, TABLE_COLUMNS["file_id"])
    assert row == (42, "activity", "garmin", "Forerunner O'Neil", 123, "2025-01-01T00:00:00", None)


def test_length_rows_with_nat() -> None:
    """length: NaT timestamp → None; tz-aware timestamps pass through as objects."""
    df = pd.DataFrame(
        [
            {
                "activity_id": 42,
                "timestamp": pd.NaT,
                "start_time": pd.Timestamp("2025-01-01T00:00:00", tz="UTC"),
                "total_timer_time": 30.0,
                "total_strokes": 18.0,
                "avg_speed": 1.5,
                "swim_stroke": "freestyle",
            }
        ]
    )
    (row,) = dataframe_to_rows(df, TABLE_COLUMNS["length"])
    by_name = dict(zip(TABLE_COLUMNS["length"], row))
    assert by_name["timestamp"] is None  # NaT → None
    assert by_name["swim_stroke"] == "freestyle"
    assert by_name["total_strokes"] == 18.0


def test_event_rows() -> None:
    """event: NaN event_group → None; apostrophe data passed through."""
    df = pd.DataFrame(
        [
            {
                "activity_id": 42,
                "timestamp": "2025-01-01T00:00:00",
                "event": "timer",
                "event_type": "start",
                "data": "O'Brien",
                "event_group": np.nan,
            }
        ]
    )
    (row,) = dataframe_to_rows(df, TABLE_COLUMNS["event"])
    assert row == (42, "2025-01-01T00:00:00", "timer", "start", "O'Brien", None)


def test_activity_rows_dynamic_id() -> None:
    """activity: row shape follows activity_columns(include_id)."""
    df = pd.DataFrame(
        [
            {
                "activity_id": 42,
                "timestamp": "2025-01-01T00:00:00",
                "total_timer_time": 600.0,
                "num_sessions": 1,
                "type": "manual",
                "event": "activity",
                "event_type": "stop",
                "activity_name": "O'Brien Park Run",
                "description": np.nan,
            }
        ]
    )
    cols = activity_columns(include_id=True)
    (row,) = dataframe_to_rows(df, cols)
    by_name = dict(zip(cols, row))
    assert by_name["activity_id"] == 42
    assert by_name["activity_name"] == "O'Brien Park Run"
    assert by_name["description"] is None  # NaN → None
    assert by_name["adjusted_distance"] is None  # absent column


def test_multiple_rows_preserve_order() -> None:
    """dataframe_to_rows returns one tuple per input row, in row order."""
    df = pd.DataFrame(
        [
            {"activity_id": 1, "latitude": 1.0, "longitude": 2.0},
            {"activity_id": 2, "latitude": 3.0, "longitude": 4.0},
        ]
    )
    rows = dataframe_to_rows(df, TABLE_COLUMNS["record"])
    assert len(rows) == 2
    assert rows[0][0] == 1
    assert rows[1][0] == 2


def test_format_sql_value_null_and_escaping() -> None:
    """The safe formatter: NULL for missing, doubled apostrophes when quoted."""
    assert format_sql_value(np.nan) == "NULL"
    assert format_sql_value(pd.NaT) == "NULL"
    assert format_sql_value(None) == "NULL"
    assert format_sql_value(250) == "250"
    assert format_sql_value("O'Brien", quote=True) == "'O''Brien'"
    assert format_sql_value("plain", quote=True) == "'plain'"


def test_fallback_formatter_matches_row_builder_effect() -> None:
    """The offline .sql fallback is equivalent in effect to the row-builder.

    For every cell the row-builder normalizes to ``None``, the fallback
    formatter must emit ``NULL``; for text it must emit the safely-escaped
    literal of the same value. This proves Task 10's "equivalent in effect"
    contract: same columns, same NULLs, same escaped values.
    """
    df = pd.DataFrame(
        [
            {
                "activity_id": 42,
                "timestamp": "2025-01-01T00:00:00",
                "event": "timer",
                "event_type": "start",
                "data": "O'Brien",  # apostrophe
                "event_group": np.nan,  # NaN → NULL
            }
        ]
    )
    columns = TABLE_COLUMNS["event"]
    # Text columns the offline writer quotes for the event table.
    quoted = {"timestamp", "event", "event_type", "data"}

    (row,) = dataframe_to_rows(df, columns)
    for col, value in zip(columns, row):
        literal = format_sql_value(value, quote=col in quoted)
        if value is None:
            assert literal == "NULL"  # missing → NULL, both paths
        elif col in quoted:
            # Quoted literal is the safely-escaped form of the bound value.
            assert literal == "'" + str(value).replace("'", "''") + "'"
        else:
            assert literal == str(value)


def test_strip_local_timestamp_tz_object_dtype_aware() -> None:
    """Object-dtype tz-aware local_timestamp is reduced to a naive wall clock.

    Regression for the timestamp bug: fitdecode yields ``local_timestamp`` as
    the local wall clock labeled UTC (06:11:36+00:00 for a 06:11 local
    activity). For some single-row / mixed / NaT activities the column arrives
    as ``object`` dtype, which the old too-narrow ``datetime64[ns, tz]`` guard
    skipped — letting a tz-aware value reach the naive column and shift the
    hour. The strip must keep the naive wall clock 06:11:36 regardless of dtype.
    """
    aware = datetime(2025, 7, 30, 6, 11, 36, tzinfo=timezone.utc)
    df = pd.DataFrame([{"activity_id": 1, "local_timestamp": aware}])
    # Force the object-dtype path that the narrow guard used to miss.
    df["local_timestamp"] = df["local_timestamp"].astype(object)
    assert df["local_timestamp"].dtype == object

    stripped = strip_local_timestamp_tz(df)

    result = stripped["local_timestamp"].iloc[0]
    # tz dropped, wall clock preserved (not shifted).
    assert result == pd.Timestamp("2025-07-30 06:11:36")
    assert result.tzinfo is None
    # Caller's DataFrame is not mutated (still object-dtype, still tz-aware).
    assert df["local_timestamp"].iloc[0] == aware


def test_strip_local_timestamp_tz_datetime64_aware_unchanged_value() -> None:
    """The already-working datetime64[ns, UTC] case yields the same naive value."""
    df = pd.DataFrame(
        [{"activity_id": 1, "local_timestamp": pd.Timestamp("2025-07-30 06:11:36", tz="UTC")}]
    )
    assert str(df["local_timestamp"].dtype) == "datetime64[ns, UTC]"

    stripped = strip_local_timestamp_tz(df)

    result = stripped["local_timestamp"].iloc[0]
    assert result == pd.Timestamp("2025-07-30 06:11:36")
    assert result.tzinfo is None


def test_strip_local_timestamp_tz_naive_is_noop() -> None:
    """An already tz-naive local_timestamp is left untouched (same object)."""
    df = pd.DataFrame([{"activity_id": 1, "local_timestamp": pd.Timestamp("2025-07-30 06:11:36")}])
    stripped = strip_local_timestamp_tz(df)
    # No change needed → the helper returns the same DataFrame object.
    assert stripped is df
    assert stripped["local_timestamp"].iloc[0] == pd.Timestamp("2025-07-30 06:11:36")


def test_strip_local_timestamp_tz_missing_column_is_noop() -> None:
    """A DataFrame without local_timestamp is returned unchanged."""
    df = pd.DataFrame([{"activity_id": 1, "timestamp": "2025-07-30T06:11:36+00:00"}])
    assert strip_local_timestamp_tz(df) is df


def test_offline_writer_object_dtype_local_timestamp_is_naive() -> None:
    """Offline .sql writer renders an object-dtype tz-aware local_timestamp naive.

    Proves Task 10's fallback path also drops the tz: the emitted literal is the
    naive wall clock ``2025-07-30 06:11:36`` (no ``+00:00`` offset), matching
    what the parameterized path binds into the naive schema column.
    """
    aware = datetime(2025, 7, 30, 6, 11, 36, tzinfo=timezone.utc)
    df = pd.DataFrame(
        [
            {
                "activity_id": 42,
                "timestamp": "2025-07-30T06:11:36",
                "num_sessions": 1,
                "type": "manual",
                "local_timestamp": aware,
            }
        ]
    )
    df["local_timestamp"] = df["local_timestamp"].astype(object)
    assert df["local_timestamp"].dtype == object

    sql = write_sql_statement_to_file(df, "activity", return_sql=True)
    assert sql is not None
    # local_timestamp renders as the naive wall clock literal, no tz offset.
    assert "'2025-07-30 06:11:36'" in sql
    # No tz-aware local_timestamp literal leaked through.
    assert "'2025-07-30 06:11:36+00:00'" not in sql
