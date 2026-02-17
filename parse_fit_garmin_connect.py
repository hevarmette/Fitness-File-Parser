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

# pd.set_option("display.max_columns", None)


def load_dataframe_to_postgres(df, tabl, _conn):
    """
    This will send decoded files directly to postgresql. I don't like this option as much because
    postgres will send back NaN and NaT if missing, which other db engines may not support. If
    you don't want to use postgres anyway.

    :param df pd.DataFrame: data of table to upload
    :param tabl string: table name of table for insertion
    :param _conn connection: postgres connection
    """
    if df.empty:
        print(f"[SKIP] {tabl}: dataframe is empty.")
        return True

    # Convert all column names into SQL-compatible string
    columns = list(df.columns)
    col_names = ", ".join(columns)

    # Generate placeholders for psycopg (e.g., "%s, %s, %s")
    placeholders = ", ".join(["%s"] * len(columns))

    # Convert to list and replace NaN floats with None.
    rows = df.values.tolist()
    rows = [
        [None if isinstance(val, float) and math.isnan(val) else val for val in row]
        for row in rows
    ]

    try:
        with _conn.cursor() as cursor:
            insert_sql = f"INSERT INTO {tabl} ({col_names}) VALUES ({placeholders})"

            cursor.executemany(insert_sql, rows)

            _conn.commit()
            print(f"[OK] Inserted {len(rows)} rows into {tabl}")
            return True

    except Exception as e:
        _conn.rollback()
        print(f"[ERROR] Inserting into {tabl}: {e}")
        # print(df.head(20))
        return False


def insert_or_fallback(df, table, just_write_sql_file, _conn):
    """
    Directly inserts data to database or it will simply write a file to local if anything fails
    are if the flag is to only write the file

    :param df pd.DataFrame: data to write
    :param table string: table name to write to
    :param just_write_sql_file bool: flag to only write the file
    :param _conn connection: postgres connection
    """
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
    # Flag to only write sql, does not require connection to a database. Otherwise connect to db.
    ONLY_WRITE_FILE = True
    if not ONLY_WRITE_FILE:
        import psycopg

        config = toml.load("secrets.toml")
        db_config = config["postgresql"]
        conn = psycopg.connect(**db_config)
    else:
        conn = None

    # Directory to read .fit and .json_summary files from
    dir = "/home/heath/Documents/Garmin/"
    file_extension = ".fit"

    # Optional to only insert files between a certain date
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

    # this can be changed to the files list to insert every activity
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
            # if getting an activity fails, then we skip the rest of the information,
            # because activity is the main table with the primary key, activity_id
            # we want to save errors to a log file and continue with other activities
            print(f"[ERROR] Skipping file {activity_id}. Reason: {e}")
            log_file_path = os.path.join(os.path.dirname(__file__), "errors.txt")
            with open(log_file_path, "a") as log_file:
                log_file.write(f"\n{activity_id} - SKIPPED FILE: {e}")
            continue  # move to next file

        # Gets metadata from json file. Such as activity name, description, and adjusted metrics
        json_info_df = pd.DataFrame(get_json_info(json_file), index=[0])
        activity_df_fixed = pd.concat([activity_df, json_info_df], axis=1)

        # save to db or write to file
        print(f"Loading activity {activity_id} . . .")
        insert_or_fallback(activity_df_fixed, "activity", ONLY_WRITE_FILE, conn)
        insert_or_fallback(file_id_df, "file_id", ONLY_WRITE_FILE, conn)
        insert_or_fallback(lap_df, "lap", ONLY_WRITE_FILE, conn)
        insert_or_fallback(record_df, "record", ONLY_WRITE_FILE, conn)
        insert_or_fallback(session_df, "session", ONLY_WRITE_FILE, conn)
        insert_or_fallback(length_df, "length", ONLY_WRITE_FILE, conn)
    print("Done")
