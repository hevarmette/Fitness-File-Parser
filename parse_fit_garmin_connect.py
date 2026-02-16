# FIX: timestamp col in acitivty with no dates and local timestamp column in future.
# parse_fit_garmin_connect.py
# This file handles Garmin Connect files (summary JSON + FIT)
import os
import toml
import pandas as pd
from os import listdir
from os.path import isfile, join
from datetime import datetime
import math

from helpers import (
    extract_date_from_filename_connect,
    get_user_activity_details,
    get_json_info,
    get_dataframes,
)

from watch_files_to_sql import write_sql_statement_to_file

pd.set_option("display.max_columns", None)


def load_dataframe_to_postgres(df, tabl, _conn):
    """Load data to postgres"""
    if df.empty:
        print(f"[SKIP] {tabl}: dataframe is empty.")
        return True

    # Convert all column names into SQL-compatible string
    columns = list(df.columns)
    col_names = ", ".join(columns)

    # Convert to list and replace NaN floats with None. Other methods of replacing NaN were not working. class float type nan
    rows = df.values.tolist()
    rows = [
        [None if isinstance(val, float) and math.isnan(val) else val for val in row]
        for row in rows
    ]

    cursor = _conn.cursor()
    try:
        # Bulk insert template
        insert_sql = f"INSERT INTO {tabl} ({col_names}) VALUES %s"
        execute_values(cursor, insert_sql, rows)
        _conn.commit()
        cursor.close()
        print(f"[OK] Inserted {len(rows)} rows into {tabl}")
        return True

    except Exception as e:
        _conn.rollback()
        cursor.close()
        print(f"[ERROR] Inserting into {tabl}: {e}")
        # print(df.head(20))
        return False


def insert_or_fallback(df, table, just_write_sql_file, _conn):
    if just_write_sql_file:
        write_sql_statement_to_file(df, table)
    else:
        if not df.empty:
            ok = load_dataframe_to_postgres(df, table, _conn)
            if not ok:
                print(f"Falling back to SQL file for {table}...")
                write_sql_statement_to_file(df, table)
        else:
            print(f"Skipped {table} because it was empty")


# ------------------------------------
# GARMIN CONNECT MAIN LOGIC
# ------------------------------------

if __name__ == "__main__":

    only_write_file = True
    if not only_write_file:
        import psycopg2
        from psycopg2.extras import execute_values

        config = toml.load("secrets.toml")
        db_config = config["postgresql"]
        conn = psycopg2.connect(**db_config)
    else:
        conn = None

    dir = "/home/heath/Documents/Garmin/"
    file_extension = ".fit"

    after_date = datetime(2026, 2, 3).date()
    today = datetime.now().date()

    files = [
        f for f in listdir(dir) if isfile(join(dir, f)) and f.endswith(file_extension)
    ]

    filtered_files = [
        f
        for f in files
        if after_date < extract_date_from_filename_connect(f)  # <= today
    ]

    errors = []

    for file in filtered_files:
        fname = dir + file
        json_file = fname.replace(file_extension, "_summary.json")

        activity_id = get_user_activity_details(fname)

        try:
            # this will only fail if activity_df fails
            lap_df, record_df, file_id_df, activity_df, session_df, length_df = (
                get_dataframes(fname, activity_id)
            )
        except Exception as e:
            print(f"[ERROR] Skipping file {activity_id}. Reason: {e}")
            log_file_path = os.path.join(os.path.dirname(__file__), "errors.txt")
            with open(log_file_path, "a") as log_file:
                log_file.write(f"\n{activity_id} - SKIPPED FILE: {e}")
            continue  # move to next file

        json_info_df = pd.DataFrame(get_json_info(json_file), index=[0])
        activity_df_fixed = pd.concat([activity_df, json_info_df], axis=1)

        print(f"Loading activity {activity_id} . . .")
        insert_or_fallback(activity_df_fixed, "activity", only_write_file, conn)
        insert_or_fallback(file_id_df, "file_id", only_write_file, conn)
        insert_or_fallback(lap_df, "lap", only_write_file, conn)
        insert_or_fallback(record_df, "record", only_write_file, conn)
        insert_or_fallback(session_df, "session", only_write_file, conn)
        insert_or_fallback(length_df, "length", only_write_file, conn)
    print("Done")
