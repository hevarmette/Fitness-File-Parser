# parse_fit_watch.py
# New pipeline: Watch-only FIT files (no JSON)
# Uses newer SQL writer: write_sql_statement_to_file()
# TODO: CHECK FOR NANS being sent back to the database!

from os import listdir
from os.path import isfile, join
from datetime import datetime

import pandas as pd

from helpers import (
    extract_date_from_filename_watch,
    extract_date_from_filename_connect,
    get_dataframes,
)
from watch_files_to_sql import write_sql_statement_to_file
import requests
import time

import toml
import psycopg2
from psycopg2.extras import execute_values

config = toml.load("secrets.toml")
db_config = config["postgresql"]
conn = psycopg2.connect(**db_config)


def reverse_geocode(lat, lon):
    """
    Reverse geocode using OSM Nominatim.
    Returns (city, county)
    """

    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "lat": lat,
        "lon": lon,
        "format": "json",
        "zoom": 10,
        "addressdetails": 1,
    }

    try:
        # OSM fair use policy — 1 request per second minimum
        time.sleep(1)

        response = requests.get(
            url, params=params, headers={"User-Agent": "fit-parser"}
        )
        data = response.json()

        addr = data.get("address", {})
        city = addr.get("city") or addr.get("town") or addr.get("village")
        county = addr.get("county")

        return city, county

    except Exception as e:
        print("Reverse geocode failed:", e)
        return None, None


def build_default_activity_name(session_df, activity_df):
    """
    Generates default activity name:
    - "{City} {Sport}"
    - Or "{County} {Sport}"
    - Sport replaced with 'Multisport' if activity_df.num_sessions > 1
    """

    # ---------- Activity Type ----------
    # Default to 1 (safe fallback)
    num_sessions = 1

    if "num_sessions" in activity_df.columns:
        num_sessions = activity_df.iloc[0]["num_sessions"]

    if num_sessions > 1:
        sport_name = "Multisport"
    else:
        sport_name = session_df.get("sport", ["Unknown"])[0].title()

    # ---------- Location ----------
    lat = session_df.get("start_position_lat", [None])[0]
    lon = session_df.get("start_position_long", [None])[0]

    if lat is None or lon is None:
        print("Unknown Location")
        return f"{sport_name}"

    city, county = reverse_geocode(lat, lon)

    if city:
        location = city
    elif county:
        location = county
    else:
        print("Unknown Location")
        return f"{sport_name}"

    return f"{location} {sport_name}"


def db_insert_dataframe(df, table, conn, return_id=False):
    """
    Inserts a dataframe into Postgres.
    - Uses parameterized INSERT
    - If return_id=True, returns the SERIAL id from the INSERT
    - On failure, returns None and caller should fall back to file output
    """
    if df.empty:
        return None

    # This shouldn't be necessary, but is a fail safe to ensure inserts as sent as NULLs and no errors sending NaNs
    df = df.where(pd.notna(df), None)

    cursor = conn.cursor()

    cols = list(df.columns)
    col_names = ", ".join(cols)
    placeholders = ", ".join(["%s"] * len(cols))
    values = df.values.tolist()

    try:
        if return_id:
            # only valid when inserting a single row
            sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) RETURNING activity_id;"
            cursor.execute(sql, values[0])
            new_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            return new_id

        else:
            sql = f"INSERT INTO {table} ({col_names}) VALUES %s"
            execute_values(cursor, sql, values)
            conn.commit()
            cursor.close()
            return True
        print(f"Inserted row(s) for {table}")

    except Exception as e:
        print(f"[DB ERROR] Failed inserting into {table}: {e}")
        cursor.close()
        return None  # fallback will be triggered by caller


def apply_activity_id_to_dfs(activity_id, dfs):
    for df in dfs:
        df["activity_id"] = activity_id


def insert_or_fallback(df, table):
    if not df.empty:
        ok = db_insert_dataframe(df, table, conn)
        if ok is None:
            print(f"Falling back to SQL file for {table}...")
            write_sql_statement_to_file(df, table)
    else:
        print(f"Skipped {table} because it was empty")


# ----------------------------------------
# MAIN LOGIC FOR WATCH FILES
# ----------------------------------------

if __name__ == "__main__":

    dir = "example activities/run/track/"
    file_extension = ".fit"

    after_date = datetime(2025, 8, 1).date()
    today = datetime.now().date()

    files = [
        f for f in listdir(dir) if isfile(join(dir, f)) and f.endswith(file_extension)
    ]

    filtered_files = [
        f for f in files if after_date < extract_date_from_filename_watch(f) <= today
    ]

    for file in filtered_files:
        fname = dir + file

        # IMPORTANT: placeholder activity_id (you requested TODO notes preserved)
        lap_df, record_df, file_id_df, activity_df, session_df, length_df = (
            get_dataframes(fname)
        )

        # the following only works with one activity per activity_df and therefore one activity in session_df
        activity_df.loc[0, "adjusted_distance"] = session_df["total_distance"].sum()
        activity_df.loc[0, "adjusted_duration"] = session_df["total_timer_time"].sum()
        activity_df.loc[0, "activity_name"] = build_default_activity_name(
            session_df, activity_df
        )

        # ---------------------------
        # Insert ACTIVITY first
        # ---------------------------
        print("Inserting activity...")

        new_activity_id = db_insert_dataframe(
            activity_df, "activity", conn, return_id=True
        )
        new_activity_id = None
        if new_activity_id is None:
            # ------------------------------------------
            # DB FAILED → FALLBACK FOR *ALL* TABLES
            # ------------------------------------------
            print("Activity insert failed. Falling back to SQL files for all tables...")

            # use 0 or pre-existing ID for file writer
            fallback_id = 0
            activity_df["activity_id"] = fallback_id

            # ensure other tables also use 0
            apply_activity_id_to_dfs(
                fallback_id,
                [file_id_df, lap_df, record_df, session_df, length_df],
            )

            # write all tables to SQL files
            write_sql_statement_to_file(activity_df, "activity")
            write_sql_statement_to_file(file_id_df, "file_id")
            write_sql_statement_to_file(lap_df, "lap")
            write_sql_statement_to_file(record_df, "record")
            write_sql_statement_to_file(session_df, "session")
            write_sql_statement_to_file(length_df, "length")

            print("Skipped DB inserts for this file due to activity failure.\n")

        else:
            # ---------------------------
            # Apply activity_id
            # ---------------------------
            apply_activity_id_to_dfs(
                new_activity_id,
                [file_id_df, lap_df, record_df, session_df, length_df],
            )

            # ---------------------------
            # Insert OTHER tables
            # ---------------------------
            insert_or_fallback(file_id_df, "file_id")
            insert_or_fallback(lap_df, "lap")
            insert_or_fallback(record_df, "record")
            insert_or_fallback(session_df, "session")
            insert_or_fallback(length_df, "length")

        # NOTE: session parser is using float definitions right now
