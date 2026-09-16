# parse_fit_garmin_connect.py
from __future__ import annotations

# This file handles Garmin Connect files (summary JSON + FIT)
import os
from datetime import datetime, timezone
from os import listdir
from os.path import isfile, join
from zoneinfo import ZoneInfo

import pandas as pd
import psycopg
from dotenv import load_dotenv

from db_insert import insert_activity, insert_table
from helpers import (
    extract_date_from_filename_connect,
    extract_date_from_filename_watch,
    get_after_date,
    get_conn,
    get_dataframes,
    get_json_info,
    get_user_activity_details,
)
from watch_files_to_sql import write_sql_statement_to_file

# pd.set_option("display.max_columns", None)


def load_dataframe_to_postgres(df: pd.DataFrame, table: str, _conn: psycopg.Connection) -> bool:
    """
    Sends a decoded DataFrame directly to PostgreSQL using parameterized inserts.

    Values are bound via psycopg placeholders (executemany, or COPY for the
    large ``record`` table), so NaN/NaT become SQL NULL and text is safe from
    apostrophes / SQL-like content. The ``activity`` table keeps its
    ``ON CONFLICT (activity_id) DO NOTHING`` behavior.

    Args:
        df (pd.DataFrame): data of table to upload
        table (str): table name of table for insertion
        _conn (psycopg.Connection): postgres connection

    Returns:
        bool: True on success (or empty DataFrame), False on failure.
    """
    if df.empty:
        print(f"[SKIP] {table}: dataframe is empty.")
        return True

    # Garmin Connect files carry their own activity_id (from the filename), so
    # the activity row is inserted with that id; a conflict is a no-op success.
    if table == "activity":
        insert_activity(df, _conn)
        return True

    return insert_table(df, table, _conn)


def insert_or_fallback(
    df: pd.DataFrame, table: str, just_write_sql_file: bool, _conn: psycopg.Connection | None
) -> None:
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
    ONLY_WRITE_FILE = False
    if not ONLY_WRITE_FILE:
        conn = get_conn()
        after_date = get_after_date(conn)
    else:
        conn = None
        after_date = datetime(2021, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
    print(after_date)
    # Directory to read .fit and .json_summary files from
    load_dotenv()
    # FIT_DIR needs to be in .env file
    raw_dir = os.getenv("FIT_DIR")
    dir = os.path.expandvars(raw_dir)
    file_extension = ".fit"

    # Optional to only insert files between a certain date
    today = datetime.now(ZoneInfo("America/Chicago"))  # .date()

    files = [f for f in listdir(dir) if isfile(join(dir, f)) and f.endswith(file_extension)]

    filtered_files = []
    # f
    for f in files:
        try:
            file_date = extract_date_from_filename_connect(f)
        except ValueError:
            file_date = extract_date_from_filename_watch(f)
        if after_date < file_date <= today:
            filtered_files.append(f)

    errors = []

    # this can be changed to the files list to insert every activity
    for file in filtered_files:
        fname = dir + file
        json_file = fname.replace(file_extension, "_summary.json")

        activity_id = get_user_activity_details(fname)

        try:
            # this will only fail if activity_df fails
            (
                lap_df,
                record_df,
                file_id_df,
                activity_df,
                session_df,
                length_df,
                event_df,
            ) = get_dataframes(fname, activity_id)

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
        insert_or_fallback(event_df, "event", ONLY_WRITE_FILE, conn)
    print("Done")
