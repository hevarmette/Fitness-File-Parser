"""Offline SQL-file generation for the 7 Garmin tables.

``write_sql_statement_to_file`` turns a decoded DataFrame into an ``INSERT``
statement (returned as a string, or appended to a ``*_inserts.sql`` file). It is
the *fallback* path used when the database is unavailable; the live insert path
uses parameter binding (see ``sql_rows.dataframe_to_rows``).

The generated literals go through the single safe value formatter
``sql_rows.format_sql_value``, so missing values render as ``NULL`` and text
apostrophes are doubled — equivalent in effect to a parameterized insert. The
column order for every table comes from ``sql_rows`` so the INSERT column list
stays obviously mapped to ``schema_garmin_data.sql``.
"""

from __future__ import annotations

import os

import pandas as pd

from sql_rows import (
    TABLE_COLUMNS,
    activity_columns,
    format_sql_value,
)

# Columns that must be emitted as quoted string/timestamp literals in the
# offline .sql output, per table. Everything else is rendered bare (numeric).
# Kept next to the column order in sql_rows so the two read together; a column
# not listed here is numeric and unquoted.
_QUOTED_COLUMNS: dict[str, set[str]] = {
    "session": {
        "timestamp",
        "start_time",
        "event",
        "event_type",
        "sport",
        "sub_sport",
        "trigger",
        "pool_length_unit",
    },
    "lap": {"start_time", "intensity"},
    "record": {"timestamp"},
    "file_id": {"type", "manufacturer", "product", "time_created"},
    "length": {"timestamp", "start_time", "swim_stroke"},
    "event": {"timestamp", "event", "event_type", "data"},
    "activity": {
        "timestamp",
        "category",
        "activity_name",
        "description",
        "local_timestamp",
        "type",
        "event",
        "event_type",
    },
}

# INSERT column-list blocks, kept byte-for-byte to match the historical output
# (and the exact-output regression tests). Each is the text between the table's
# parentheses in the generated statement. Laid out to mirror
# schema_garmin_data.sql so a reader can line them up against the schema.
_INSERT_COLUMN_BLOCKS: dict[str, str] = {
    "session": (
        "\n                activity_id, timestamp, start_time, start_position_lat, "
        "\n                start_position_long, total_elapsed_time, total_timer_time, "
        "\n                total_distance, total_strokes, nec_lat, nec_long, swc_lat, "
        "\n                swc_long, message_index, total_calories, total_fat_calories, "
        "\n                enhanced_avg_speed, avg_speed, enhanced_max_speed, max_speed, "
        "\n                avg_power, max_power, total_ascent, total_descent, "
        "\n                first_lap_index, num_laps, event, event_type, sport, "
        "\n                sub_sport, avg_heart_rate, max_heart_rate, avg_cadence, "
        "\n                max_cadence, total_training_effect, event_group, trigger, "
        "\n                pool_length, pool_length_unit\n            "
    ),
    "lap": (
        "\n                activity_id, number, start_time, total_distance, "
        "\n                total_timer_time, total_ascent, total_descent, "
        "\n                avg_vertical_oscillation, avg_stance_time, avg_vertical_ratio, "
        "\n                avg_stance_time_balance, avg_step_length, intensity, "
        "\n                avg_running_cadence, max_heart_rate, avg_heart_rate,"
        "\n                avg_power, max_power, normalized_power\n            "
    ),
    "record": (
        "\n                activity_id, latitude, longitude, lap, altitude, "
        "\n                timestamp, heart_rate, cadence, fractional_cadence, "
        "\n                enhanced_speed, distance\n            "
    ),
    "file_id": (
        "\n                activity_id, type, manufacturer, product, "
        "\n                serial_number, time_created, number\n            "
    ),
    "length": (
        "\n                activity_id, timestamp, start_time,  "
        "\n                total_timer_time, total_strokes, avg_speed, swim_stroke\n            "
    ),
    "event": (
        "\n                activity_id, timestamp, event, event_type, "
        "data, event_group\n            "
    ),
}


def _render_rows(df: pd.DataFrame, columns: list[str], quoted: set[str]) -> list[str]:
    """Render each DataFrame row as a ``(v1, v2, ...)`` literal tuple.

    Values go through :func:`sql_rows.format_sql_value`, so missing data becomes
    ``NULL`` and quoted (text/timestamp) columns get doubled-apostrophe escaping.
    Columns absent from ``df`` render as ``NULL`` — matching the historical
    "missing column → NULL" behavior.

    Args:
        df: The DataFrame to render.
        columns: Ordered column names (from ``sql_rows``).
        quoted: The subset of ``columns`` that must be quoted string literals.

    Returns:
        list[str]: One ``(...)`` literal per row, in ``columns`` order.
    """
    # reindex makes any missing column present-but-NaN, which format_sql_value
    # collapses to NULL; this keeps the emitted column order explicit.
    ordered = df.reindex(columns=columns)
    rendered: list[str] = []
    for row in ordered.itertuples(index=False, name=None):
        cells = [format_sql_value(value, quote=col in quoted) for col, value in zip(columns, row)]
        rendered.append("(" + ", ".join(cells) + ")")
    return rendered


def write_sql_statement_to_file(
    df: pd.DataFrame,
    tabl: str,
    log_file_path: str | None = None,
    return_sql: bool = False,
) -> str | None:
    """Generate an ``INSERT`` statement for ``tabl`` from ``df``.

    Missing values (``NaN``/``NaT``/absent columns) render as SQL ``NULL`` and
    text values are apostrophe-escaped via the shared safe value formatter, so
    the output is equivalent in effect to a parameterized insert.

    Args:
        df: The decoded DataFrame for the table.
        tabl: Target table name (one of the 7 Garmin tables).
        log_file_path: Destination file when writing; defaults to
            ``<repo>/<tabl>_inserts.sql``. Unused when ``return_sql`` is True.
        return_sql: When True, return the SQL string instead of writing a file.

    Returns:
        str | None: The SQL string when ``return_sql`` is True; otherwise
        ``None`` (the statement is appended to ``log_file_path``). Returns
        ``None`` for an empty DataFrame or an unknown table.
    """
    if df.empty:
        return None

    sql = ""

    # --- Activity Table (dynamic activity_id + tz-naive local_timestamp) ---
    if tabl == "activity":
        # Remove timezone from local_timestamp if present so it maps to the
        # schema's `timestamp without time zone` column.
        if "local_timestamp" in df.columns and df["local_timestamp"].dtype.name.startswith(
            "datetime64[ns,"
        ):
            df["local_timestamp"] = df["local_timestamp"].dt.tz_localize(None)

        # Include activity_id only when the first row carries a real id; we
        # assume the batch is homogeneous. Otherwise the DB auto-increments.
        include_id = False
        if "activity_id" in df.columns:
            first_val = df["activity_id"].iloc[0]
            if pd.notna(first_val):
                include_id = True

        cols_ordered = activity_columns(include_id)
        rows = _render_rows(df, cols_ordered, _QUOTED_COLUMNS["activity"])

        if rows:
            bulk_values = ",\n".join(rows)
            cols_str = ", ".join(cols_ordered)
            sql = f"""
            INSERT INTO activity (
                {cols_str}
            )
            VALUES
            {bulk_values}
            ON CONFLICT (activity_id) DO NOTHING;
            """

    # --- Length Table (cast dtypes before rendering, as historically) ---
    elif tabl == "length":
        desired_dtypes = {
            "activity_id": "int64",
            "timestamp": "datetime64[ns, UTC]",
            "start_time": "datetime64[ns, UTC]",
            "total_timer_time": "float64",
            "total_strokes": "float64",
            "avg_speed": "float64",
            "swim_stroke": "object",
        }
        existing_dtypes = {col: dtype for col, dtype in desired_dtypes.items() if col in df.columns}
        if existing_dtypes:
            df = df.astype(existing_dtypes)

        cols_ordered = TABLE_COLUMNS["length"]
        rows = _render_rows(df, cols_ordered, _QUOTED_COLUMNS["length"])
        if rows:
            bulk_values = ",\n".join(rows)
            sql = f"""
            INSERT INTO length({_INSERT_COLUMN_BLOCKS["length"]})
            VALUES 
            {bulk_values};
            """

    # --- Remaining fixed-column tables ---
    elif tabl in ("session", "lap", "record", "file_id", "event"):
        cols_ordered = TABLE_COLUMNS[tabl]
        rows = _render_rows(df, cols_ordered, _QUOTED_COLUMNS[tabl])
        if rows:
            bulk_values = ",\n".join(rows)
            sql = f"""
            INSERT INTO {tabl}({_INSERT_COLUMN_BLOCKS[tabl]})
            VALUES 
            {bulk_values};
            """

    else:
        print(
            f"Warning: No specific SQL generation logic defined for table '{tabl}'. "
            "No statements written."
        )
        return None

    # ---------------------------------------------------------
    # OUTPUT: RETURN OR APPEND TO FILE
    # ---------------------------------------------------------
    if return_sql:
        return sql

    if log_file_path is None:
        log_file_path = os.path.join(os.path.dirname(__file__), f"{tabl}_inserts.sql")

    print(f"Writing SQL file: {log_file_path}")
    with open(log_file_path, "a") as log_file:
        log_file.write("\n\n")
        log_file.write(sql + "\n")
    return None


# Re-exported for callers that build parameterized inserts on the same order.
__all__ = ["TABLE_COLUMNS", "format_sql_value", "write_sql_statement_to_file"]
