"""Parameterized PostgreSQL insert path for the 7 Garmin tables.

Every insert here binds values through ``psycopg`` placeholders — no
string-interpolated SQL — so ``NaN``/``NaT``/missing become SQL ``NULL`` and
text (apostrophes, SQL-like content) is always safe.

Two strategies, chosen by table size:

* ``record`` (the large per-point table) uses ``cursor.copy()`` (binary
  ``COPY ... FROM STDIN``), which is markedly faster for many rows.
* Every other table uses ``cursor.executemany``.

The ``activity`` table keeps its historical semantics:
``ON CONFLICT (activity_id) DO NOTHING`` and, when inserting a new activity,
``RETURNING activity_id`` so the caller gets the generated primary key.

Column order comes from :mod:`sql_rows`, the single source of truth, so the
bound column list stays obviously mapped to ``schema_garmin_data.sql``.
"""

from __future__ import annotations

import pandas as pd
import psycopg

from sql_rows import (
    TABLE_COLUMNS,
    activity_columns,
    build_activity_insert_sql,
    build_insert_sql,
    copy_columns_sql,
    dataframe_to_rows,
)


def insert_activity(df: pd.DataFrame, conn: psycopg.Connection) -> int | None:
    """Insert a single ``activity`` row and return its ``activity_id``.

    Mirrors the historical dynamic-id behavior: ``activity_id`` is only bound
    when the DataFrame carries a real id (otherwise PostgreSQL auto-increments
    the ``bigserial``). Applies ``ON CONFLICT (activity_id) DO NOTHING`` and
    ``RETURNING activity_id``.

    Args:
        df: The (single-row) activity DataFrame.
        conn: An open psycopg connection.

    Returns:
        int | None: The new/existing ``activity_id`` on success, or ``None`` when
        the DataFrame is empty, a conflict suppressed the insert, or the insert
        failed (rolled back).
    """
    if df.empty:
        return None

    # activity_id is bound only when the first row supplies a real value; the
    # writer assumes the batch is homogeneous.
    include_id = "activity_id" in df.columns and pd.notna(df["activity_id"].iloc[0])
    columns = activity_columns(include_id)
    rows = dataframe_to_rows(df, columns)

    sql = build_activity_insert_sql(columns, returning=True)
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, rows[0])
            result = cursor.fetchone()
        conn.commit()
        if result:
            return int(result[0])
        # ON CONFLICT DO NOTHING → no row returned.
        print("[DB INFO] activity insert skipped (conflict or no id returned).")
        return None
    except psycopg.Error as e:
        print(f"[DB ERROR] Failed inserting into activity: {e}")
        conn.rollback()
        return None


def insert_table(df: pd.DataFrame, table: str, conn: psycopg.Connection) -> bool:
    """Insert all rows of ``df`` into ``table`` using parameter binding.

    Uses ``cursor.copy()`` for the large ``record`` table and
    ``cursor.executemany`` for the others. Missing values are normalized to
    ``None`` by the shared row-builder so the driver emits ``NULL``.

    Args:
        df: The DataFrame to insert (child table; ``activity`` uses
            :func:`insert_activity`).
        table: Target table name.
        conn: An open psycopg connection.

    Returns:
        bool: ``True`` on success (including an empty DataFrame, which is a
        no-op), ``False`` if the insert failed and was rolled back.
    """
    if df.empty:
        return True

    if table not in TABLE_COLUMNS:
        raise ValueError(f"No column order defined for table {table!r}")

    columns = TABLE_COLUMNS[table]
    rows = dataframe_to_rows(df, columns)

    try:
        with conn.cursor() as cursor:
            if table == "record":
                # Binary COPY is much faster for the high-row-count record table.
                with cursor.copy(copy_columns_sql(table, columns)) as copy:
                    for row in rows:
                        copy.write_row(row)
            else:
                cursor.executemany(build_insert_sql(table, columns), rows)
        conn.commit()
        return True
    except psycopg.Error as e:
        print(f"[DB ERROR] Failed inserting into {table}: {e}")
        conn.rollback()
        return False
