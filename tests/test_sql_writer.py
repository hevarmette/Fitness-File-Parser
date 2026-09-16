"""Exact-output tests for :func:`watch_files_to_sql.write_sql_statement_to_file`.

Each of the 7 tables is exercised with a small, known DataFrame and the full
generated SQL string is asserted verbatim. Coverage explicitly includes:

* ``NaN`` / ``NaT`` values rendering as SQL ``NULL``.
* Single-quote (apostrophe) escaping — a value like ``O'Brien`` must become
  ``'O''Brien'`` so the string literal is not terminated early.
* The ``activity`` table's ``ON CONFLICT (activity_id) DO NOTHING`` clause.

The writer mutates the input DataFrame for the ``activity`` and ``length``
tables (it adds missing columns / casts dtypes), so every test passes a fresh
DataFrame constructed inside the test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from watch_files_to_sql import write_sql_statement_to_file

# Expected outputs are asserted verbatim (whitespace included) because the
# production insert path consumes these strings directly.

EXPECTED_LAP = """
            INSERT INTO lap(
                activity_id, number, start_time, total_distance, 
                total_timer_time, total_ascent, total_descent, 
                avg_vertical_oscillation, avg_stance_time, avg_vertical_ratio, 
                avg_stance_time_balance, avg_step_length, intensity, 
                avg_running_cadence, max_heart_rate, avg_heart_rate,
                avg_power, max_power, normalized_power
            )
            VALUES 
            (42, 1, '2025-01-01T00:00:00', 100.0, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'O''Brien', NULL, NULL, NULL, NULL, 250, NULL);
            """  # noqa: W291, W293  (trailing whitespace is part of the generated SQL)

EXPECTED_RECORD = """
            INSERT INTO record(
                activity_id, latitude, longitude, lap, altitude, 
                timestamp, heart_rate, cadence, fractional_cadence, 
                enhanced_speed, distance
            )
            VALUES 
            (42, 51.5, -0.12, 1, 10.0, '2025-01-01T00:00:01', 120, 80, 0.5, 3.2, 5.0);
            """  # noqa: W291, W293

EXPECTED_FILE_ID = """
            INSERT INTO file_id(
                activity_id, type, manufacturer, product, 
                serial_number, time_created, number
            )
            VALUES 
            (42, 'activity', 'garmin', 'Forerunner O''Neil', 123, '2025-01-01T00:00:00', NULL);
            """  # noqa: W291, W293

EXPECTED_SESSION = """
            INSERT INTO session(
                activity_id, timestamp, start_time, start_position_lat, 
                start_position_long, total_elapsed_time, total_timer_time, 
                total_distance, total_strokes, nec_lat, nec_long, swc_lat, 
                swc_long, message_index, total_calories, total_fat_calories, 
                enhanced_avg_speed, avg_speed, enhanced_max_speed, max_speed, 
                avg_power, max_power, total_ascent, total_descent, 
                first_lap_index, num_laps, event, event_type, sport, 
                sub_sport, avg_heart_rate, max_heart_rate, avg_cadence, 
                max_cadence, total_training_effect, event_group, trigger, 
                pool_length, pool_length_unit
            )
            VALUES 
            (42, '2025-01-01T00:10:00', '2025-01-01T00:00:00', 51.5, -0.12, 600.0, 590.0, 2000.0, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'session', 'stop', 'running', 'generic', NULL, NULL, NULL, NULL, NULL, NULL, 'activity_end', NULL, NULL);
            """  # noqa: W291, W293

EXPECTED_LENGTH = """
            INSERT INTO length(
                activity_id, timestamp, start_time,  
                total_timer_time, total_strokes, avg_speed, swim_stroke
            )
            VALUES 
            (42, '2025-01-01 00:00:30+00:00', '2025-01-01 00:00:00+00:00', 30.0, 18.0, 1.5, 'freestyle');
            """  # noqa: W291, W293

EXPECTED_EVENT = """
            INSERT INTO event(
                activity_id, timestamp, event, event_type, data, event_group
            )
            VALUES 
            (42, '2025-01-01T00:00:00', 'timer', 'start', 'O''Brien', NULL);
            """  # noqa: W291, W293

EXPECTED_ACTIVITY = """
            INSERT INTO activity (
                activity_id, timestamp, adjusted_distance, adjusted_duration, workout_feel, effort, category, activity_name, description, total_timer_time, local_timestamp, num_sessions, type, event, event_type, event_group
            )
            VALUES
            (42, '2025-01-01T00:00:00', NULL, NULL, NULL, NULL, NULL, 'O''Brien Park Run', NULL, 600.0, NULL, 1, 'manual', 'activity', 'stop', NULL)
            ON CONFLICT (activity_id) DO NOTHING;
            """  # noqa: W291, W293


def test_lap_sql_null_and_apostrophe() -> None:
    """Lap SQL: NaN power → NULL, apostrophe in intensity → doubled quote."""
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
    assert write_sql_statement_to_file(df, "lap", return_sql=True) == EXPECTED_LAP


def test_record_sql() -> None:
    """Record SQL: numeric columns rendered without quotes, timestamp quoted."""
    df = pd.DataFrame(
        [
            {
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
                "distance": 5.0,
            }
        ]
    )
    assert write_sql_statement_to_file(df, "record", return_sql=True) == EXPECTED_RECORD


def test_file_id_sql_null_and_apostrophe() -> None:
    """file_id SQL: apostrophe in product escaped, NaN number → NULL."""
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
    assert write_sql_statement_to_file(df, "file_id", return_sql=True) == EXPECTED_FILE_ID


def test_session_sql_missing_columns_become_null() -> None:
    """session SQL: absent columns and NaN both render as NULL."""
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
    assert write_sql_statement_to_file(df, "session", return_sql=True) == EXPECTED_SESSION


def test_length_sql_tz_aware_timestamps() -> None:
    """length SQL: tz-aware timestamps stringified; casts do not corrupt output."""
    df = pd.DataFrame(
        [
            {
                "activity_id": 42,
                "timestamp": pd.Timestamp("2025-01-01T00:00:30", tz="UTC"),
                "start_time": pd.Timestamp("2025-01-01T00:00:00", tz="UTC"),
                "total_timer_time": 30.0,
                "total_strokes": 18.0,
                "avg_speed": 1.5,
                "swim_stroke": "freestyle",
            }
        ]
    )
    assert write_sql_statement_to_file(df, "length", return_sql=True) == EXPECTED_LENGTH


def test_event_sql_apostrophe_and_null() -> None:
    """event SQL: apostrophe in data escaped, NaN event_group → NULL."""
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
    assert write_sql_statement_to_file(df, "event", return_sql=True) == EXPECTED_EVENT


def test_activity_sql_conflict_clause_and_apostrophe() -> None:
    """activity SQL: includes ON CONFLICT clause; name apostrophe escaped."""
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
    assert write_sql_statement_to_file(df, "activity", return_sql=True) == EXPECTED_ACTIVITY


def test_empty_dataframe_returns_none() -> None:
    """An empty DataFrame yields no SQL (None) for every table type."""
    for table in ("lap", "record", "file_id", "session", "length", "event", "activity"):
        assert write_sql_statement_to_file(pd.DataFrame(), table, return_sql=True) is None
