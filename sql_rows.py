"""Shared row-building utilities for the FIT-parser database insert path.

This module is the single, readable source of truth for **which columns land in
which table and in what order**. The per-table column lists here are laid out to
mirror ``schema_garmin_data.sql`` so a FIT-literate reader can line the INSERT
column list up against the table definition at a glance.

Two consumers build on this structure:

* Parameterized DB inserts (``psycopg`` ``executemany`` / ``cursor.copy()``)
  use :func:`dataframe_to_rows` to turn a DataFrame into a list of value tuples
  with ``NaN``/``NaT``/missing → ``None`` (which the driver emits as SQL
  ``NULL``). Text is bound as a parameter, so apostrophes and SQL-like content
  are always safe — no manual escaping.
* The offline ``.sql`` file fallback uses :func:`format_sql_value` (built on the
  same row-builder) so its output stays equivalent in effect to a parameterized
  insert: the same columns, the same ``NULL`` handling, and the same doubled
  single-quote escaping for text.

Nothing here decodes FIT frames; it only shapes already-decoded DataFrames for
insertion. Decoder logic lives in ``helpers.get_dataframes`` and is untouched.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# PER-TABLE COLUMN ORDER (source of truth, mirrors schema_garmin_data.sql)
# ---------------------------------------------------------------------------
#
# Each entry is the exact, ordered list of columns written for that table's
# INSERT. Keep these aligned with the ``CREATE TABLE`` column order in
# schema_garmin_data.sql and with the INSERT column lists in
# ``watch_files_to_sql.py`` — they must stay obviously in sync.
#
# ``activity`` is intentionally *not* here: its column list is dynamic because
# ``activity_id`` is only included when the DataFrame carries a real id (so the
# database can otherwise auto-increment ``bigserial``). Its order is built with
# :func:`activity_columns` instead.

TABLE_COLUMNS: dict[str, list[str]] = {
    "session": [
        "activity_id",
        "timestamp",
        "start_time",
        "start_position_lat",
        "start_position_long",
        "total_elapsed_time",
        "total_timer_time",
        "total_distance",
        "total_strokes",
        "nec_lat",
        "nec_long",
        "swc_lat",
        "swc_long",
        "message_index",
        "total_calories",
        "total_fat_calories",
        "enhanced_avg_speed",
        "avg_speed",
        "enhanced_max_speed",
        "max_speed",
        "avg_power",
        "max_power",
        "total_ascent",
        "total_descent",
        "first_lap_index",
        "num_laps",
        "event",
        "event_type",
        "sport",
        "sub_sport",
        "avg_heart_rate",
        "max_heart_rate",
        "avg_cadence",
        "max_cadence",
        "total_training_effect",
        "event_group",
        "trigger",
        "pool_length",
        "pool_length_unit",
    ],
    "lap": [
        "activity_id",
        "number",
        "start_time",
        "total_distance",
        "total_timer_time",
        "total_ascent",
        "total_descent",
        "avg_vertical_oscillation",
        "avg_stance_time",
        "avg_vertical_ratio",
        "avg_stance_time_balance",
        "avg_step_length",
        "intensity",
        "avg_running_cadence",
        "max_heart_rate",
        "avg_heart_rate",
        "avg_power",
        "max_power",
        "normalized_power",
    ],
    "record": [
        "activity_id",
        "latitude",
        "longitude",
        "lap",
        "altitude",
        "timestamp",
        "heart_rate",
        "cadence",
        "fractional_cadence",
        "enhanced_speed",
        "distance",
    ],
    "file_id": [
        "activity_id",
        "type",
        "manufacturer",
        "product",
        "serial_number",
        "time_created",
        "number",
    ],
    "length": [
        "activity_id",
        "timestamp",
        "start_time",
        "total_timer_time",
        "total_strokes",
        "avg_speed",
        "swim_stroke",
    ],
    "event": [
        "activity_id",
        "timestamp",
        "event",
        "event_type",
        "data",
        "event_group",
    ],
}

# Full activity column order *excluding* the optional leading activity_id.
# schema_garmin_data.sql order; activity_id is prepended by activity_columns()
# only when the DataFrame supplies a real id.
ACTIVITY_COLUMNS_NO_ID: list[str] = [
    "timestamp",
    "adjusted_distance",
    "adjusted_duration",
    "workout_feel",
    "effort",
    "category",
    "activity_name",
    "description",
    "total_timer_time",
    "local_timestamp",
    "num_sessions",
    "type",
    "event",
    "event_type",
    "event_group",
]


def activity_columns(include_id: bool) -> list[str]:
    """Return the ordered ``activity`` column list.

    Args:
        include_id: When ``True`` the returned list is prefixed with
            ``activity_id``; when ``False`` the id is omitted so PostgreSQL can
            auto-increment the ``bigserial`` primary key.

    Returns:
        list[str]: The ordered column names for an ``activity`` INSERT.
    """
    if include_id:
        return ["activity_id", *ACTIVITY_COLUMNS_NO_ID]
    return list(ACTIVITY_COLUMNS_NO_ID)


def _to_none_if_missing(value: Any) -> Any:
    """Normalize a single cell so missing data becomes ``None``.

    ``NaN`` (missing float) and ``NaT`` (missing datetime) both map to ``None``
    so the database driver emits SQL ``NULL``. Non-missing values pass through
    unchanged; the driver is responsible for their type adaptation.

    Args:
        value: A single DataFrame cell value.

    Returns:
        Any: ``None`` when the value is missing, otherwise the value itself.
    """
    # pd.isna also flags NaT; guard against array-valued cells (never expected
    # in these flat tables) by only collapsing scalar-truthy results.
    result = pd.isna(value)
    if isinstance(result, bool) and result:
        return None
    return value


def dataframe_to_rows(df: pd.DataFrame, columns: list[str]) -> list[tuple[Any, ...]]:
    """Convert a DataFrame into value tuples in a fixed column order.

    Columns absent from ``df`` are treated as entirely missing (all ``None``),
    matching the historical behavior where a missing column rendered as ``NULL``.
    Present-but-``NaN``/``NaT`` cells also become ``None``.

    The output is ready to hand to ``psycopg``'s ``executemany`` /
    ``cursor.copy()`` with a matching ``%s`` placeholder list, so text values
    (including apostrophes and SQL-like content) are bound safely rather than
    string-escaped.

    Args:
        df: The decoded DataFrame to convert.
        columns: The exact, ordered column names to emit per row.

    Returns:
        list[tuple[Any, ...]]: One tuple per DataFrame row, each in ``columns``
        order with missing values normalized to ``None``.
    """
    # Reindex to the requested order; missing columns arrive as NaN, which the
    # normalization below turns into None. This keeps the column order explicit
    # and identical to the INSERT column list.
    ordered = df.reindex(columns=columns)

    rows: list[tuple[Any, ...]] = []
    for record in ordered.itertuples(index=False, name=None):
        rows.append(tuple(_to_none_if_missing(cell) for cell in record))
    return rows


def build_insert_sql(table: str, columns: list[str]) -> str:
    """Build a parameterized ``INSERT`` statement for ``table``.

    Produces ``INSERT INTO <table> (c1, c2, ...) VALUES (%s, %s, ...)`` with one
    ``%s`` placeholder per column, so values are bound by the driver rather than
    interpolated. Safe against apostrophes / SQL-like text by construction.

    Args:
        table: Target table name.
        columns: Ordered column names; the placeholder count matches.

    Returns:
        str: A parameterized INSERT statement (no trailing clauses).
    """
    cols_str = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    return f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders})"


def build_activity_insert_sql(columns: list[str], returning: bool = False) -> str:
    """Build the parameterized ``activity`` INSERT with its conflict clause.

    Preserves the historical behavior: ``ON CONFLICT (activity_id) DO NOTHING``
    and, when requested, ``RETURNING activity_id`` so the caller can fetch the
    generated primary key.

    Args:
        columns: Ordered ``activity`` column names (see :func:`activity_columns`).
        returning: When True, append ``RETURNING activity_id``.

    Returns:
        str: The parameterized ``activity`` INSERT statement.
    """
    sql = f"{build_insert_sql('activity', columns)} ON CONFLICT (activity_id) DO NOTHING"
    if returning:
        sql += " RETURNING activity_id"
    return sql


def copy_columns_sql(table: str, columns: list[str]) -> str:
    """Build the ``COPY ... FROM STDIN`` statement used by ``cursor.copy()``.

    Used for the large ``record`` table where binary COPY is markedly faster
    than row-by-row INSERTs. psycopg still binds each value (no string
    interpolation), so text remains safe.

    Args:
        table: Target table name.
        columns: Ordered column names to copy into.

    Returns:
        str: A ``COPY <table> (cols) FROM STDIN`` statement.
    """
    cols_str = ", ".join(columns)
    return f"COPY {table} ({cols_str}) FROM STDIN"


def format_sql_value(value: Any, quote: bool = False) -> str:
    """Render a single value as a literal for the offline ``.sql`` fallback.

    This is the *one* safe value formatter used by the file fallback. It mirrors
    parameter binding in effect:

    * Missing values (``None``/``NaN``/``NaT``) become ``NULL``.
    * When ``quote`` is set, apostrophes are doubled (``O'Brien`` → ``'O''Brien'``)
      so a text literal cannot be terminated early or inject SQL.

    Args:
        value: The cell value to render.
        quote: Whether the value is text/timestamp and must be quoted.

    Returns:
        str: A SQL literal fragment (``NULL``, a quoted string, or a bare number).
    """
    if _to_none_if_missing(value) is None:
        return "NULL"
    if quote:
        # Escape single quotes by doubling them so the literal stays balanced.
        safe = str(value).replace("'", "''")
        return f"'{safe}'"
    return str(value)
