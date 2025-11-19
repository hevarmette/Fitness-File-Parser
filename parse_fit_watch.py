# parse_fit_watch.py
# New pipeline: Watch-only FIT files (no JSON)
# Uses newer SQL writer: write_sql_statement_to_file_watch()

import os
from os import listdir
from os.path import isfile, join
from datetime import datetime

import pandas as pd

from helpers import (
    extract_date_from_filename_watch,
    get_dataframes,
)

import requests
import time


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
    try:
        num_sessions = int(activity_df.get("num_sessions", [1])[0])
    except:
        num_sessions = 1

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


def write_sql_statement_to_file_watch(df, tabl, log_file_path=None):
    """
    New SQL writer (watch-only).
    Outputs SQL INSERT statements with robust formatting.
    """
    if log_file_path is None:
        log_file_path = os.path.join(os.path.dirname(__file__), f"{tabl}_inserts.sql")

    print(f"Writing SQL file: {log_file_path}")

    def sql_format(value, quote=False):
        if pd.isna(value):
            return "NULL"
        if quote:
            safe = str(value).replace("'", "''")
            return f"'{safe}'"
        return str(value)

    with open(log_file_path, "a") as log_file:
        log_file.write("\n\n")

        if df.empty:
            return

        else:
            if tabl == "activity":
                # must explicitly remove the timezone from local timestamp to send to db (it has no timezone there)
                if df["local_timestamp"].dtype.name.startswith("datetime64[ns,"):
                    df["local_timestamp"] = df["local_timestamp"].dt.tz_localize(None)
                # Define your desired dtype mappings
                desired_dtypes = {
                    "activity_id": "int64",
                    "timestamp": "datetime64[ns, UTC]",
                    "adjusted_distance": "float64",
                    "adjusted_duration": "float64",
                    "workout_feel": "int64",
                    "effort": "int64",
                    "category": "object",
                    "activity_name": "object",
                    "description": "object",
                    "total_timer_time": "float64",
                    "local_timestamp": "datetime64[ns]",
                    "num_sessions": "int64",
                    "type": "object",
                    "event": "object",
                    "event_type": "object",
                    "event_group": "object",
                }

                # Filter to only include columns that exist in the DataFrame
                existing_dtypes = {
                    col: dtype
                    for col, dtype in desired_dtypes.items()
                    if col in df.columns
                }

                # Apply the conversion
                df = df.astype(existing_dtypes)

                for col in desired_dtypes.keys():
                    if col not in df.columns:
                        df[col] = None

                for index, row in df.iterrows():

                    # --- CHANGE ---
                    # Use the new sql_format() helper for every value
                    sql = f"""INSERT INTO activity(activity_id, timestamp, adjusted_distance, adjusted_duration, workout_feel, effort, category, activity_name, description, total_timer_time, local_timestamp, num_sessions, type, event, event_type, event_group)
                    VALUES ({sql_format(row['activity_id'])}, {sql_format(row['timestamp'], quote=True)}, {sql_format(row['adjusted_distance'])}, {sql_format(row['adjusted_duration'])}, {sql_format(row['workout_feel'])}, {sql_format(row['effort'])}, {sql_format(row['category'], quote=True)}, {sql_format(row['activity_name'], quote=True)}, {sql_format(row['description'], quote=True)}, {sql_format(row['total_timer_time'])}, {sql_format(row['local_timestamp'], quote=True)}, {sql_format(row['num_sessions'])}, {sql_format(row['type'], quote=True)}, {sql_format(row['event'], quote=True)}, {sql_format(row['event_type'], quote=True)}, {sql_format(row['event_group'], quote=True)})
                    ON CONFLICT (activity_id) DO NOTHING;"""

                    # Write to log file
                    log_file.write(sql + "\n")

            elif tabl == "session":
                # *** REVIEW/EDIT THIS SCHEMA ***
                desired_dtypes = {
                    "activity_id": "int64",
                    "timestamp": "datetime64[ns, UTC]",
                    "start_time": "datetime64[ns, UTC]",
                    "start_position_lat": "float",
                    "start_position_long": "float",
                    "total_elapsed_time": "float64",
                    "total_timer_time": "float64",
                    "total_distance": "float64",
                    "total_strokes": "float64",
                    "nec_lat": "float",
                    "nec_long": "float",
                    "swc_lat": "float",
                    "swc_long": "float",
                    "message_index": "int64",
                    "total_calories": "float",
                    "total_fat_calories": "float64",
                    "enhanced_avg_speed": "float64",
                    "avg_speed": "float64",
                    "enhanced_max_speed": "float64",
                    "max_speed": "float64",
                    "avg_power": "float64",
                    "max_power": "float64",
                    "total_ascent": "float",
                    "total_descent": "float",
                    "first_lap_index": "float",
                    "num_laps": "float",
                    "event": "object",
                    "event_type": "object",
                    "sport": "object",
                    "sub_sport": "object",
                    "avg_heart_rate": "float",
                    "max_heart_rate": "float",
                    "avg_cadence": "float",
                    "max_cadence": "float",
                    "total_training_effect": "float64",
                    "event_group": "float64",
                    "trigger": "object",
                    "pool_length": "float",
                    "pool_length_unit": "object",
                }

                existing_dtypes = {
                    col: dtype
                    for col, dtype in desired_dtypes.items()
                    if col in df.columns
                }
                if existing_dtypes:
                    df = df.astype(existing_dtypes)

                for col in desired_dtypes.keys():
                    if col not in df.columns:
                        df[col] = None

                values_list = []

                for index, row in df.iterrows():
                    # Create the value group for this specific row
                    row_str = (
                        f"("
                        f"{sql_format(row['activity_id'])}, "
                        f"{sql_format(row['timestamp'], quote=True)}, "
                        f"{sql_format(row['start_time'], quote=True)}, "
                        f"{sql_format(row['start_position_lat'])}, "
                        f"{sql_format(row['start_position_long'])}, "
                        f"{sql_format(row['total_elapsed_time'])}, "
                        f"{sql_format(row['total_timer_time'])}, "
                        f"{sql_format(row['total_distance'])}, "
                        f"{sql_format(row['total_strokes'])}, "
                        f"{sql_format(row['nec_lat'])}, "
                        f"{sql_format(row['nec_long'])}, "
                        f"{sql_format(row['swc_lat'])}, "
                        f"{sql_format(row['swc_long'])}, "
                        f"{sql_format(row['message_index'])}, "
                        f"{sql_format(row['total_calories'])}, "
                        f"{sql_format(row['total_fat_calories'])}, "
                        f"{sql_format(row['enhanced_avg_speed'])}, "
                        f"{sql_format(row['avg_speed'])}, "
                        f"{sql_format(row['enhanced_max_speed'])}, "
                        f"{sql_format(row['max_speed'])}, "
                        f"{sql_format(row['avg_power'])}, "
                        f"{sql_format(row['max_power'])}, "
                        f"{sql_format(row['total_ascent'])}, "
                        f"{sql_format(row['total_descent'])}, "
                        f"{sql_format(row['first_lap_index'])}, "
                        f"{sql_format(row['num_laps'])}, "
                        f"{sql_format(row['event'], quote=True)}, "
                        f"{sql_format(row['event_type'], quote=True)}, "
                        f"{sql_format(row['sport'], quote=True)}, "
                        f"{sql_format(row['sub_sport'], quote=True)}, "
                        f"{sql_format(row['avg_heart_rate'])}, "
                        f"{sql_format(row['max_heart_rate'])}, "
                        f"{sql_format(row['avg_cadence'])}, "
                        f"{sql_format(row['max_cadence'])}, "
                        f"{sql_format(row['total_training_effect'])}, "
                        f"{sql_format(row['event_group'])}, "
                        f"{sql_format(row['trigger'], quote=True)}, "
                        f"{sql_format(row['pool_length'])}, "
                        f"{sql_format(row['pool_length_unit'], quote=True)}"
                        f")"
                    )
                    values_list.append(row_str)

                if values_list:
                    # Join all rows with a comma and newline
                    bulk_values = ",\n".join(values_list)

                    # Construct the final bulk insert statement
                    sql = f"""
                    INSERT INTO public.session(
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
                    {bulk_values};
                    """

                    log_file.write(sql + "\n")

            # --- Lap Table ---
            elif tabl == "lap":
                # *** REVIEW/EDIT THIS SCHEMA ***
                desired_dtypes = {
                    "activity_id": "int64",
                    "number": "int64",
                    "start_time": "datetime64[ns, UTC]",
                    "total_distance": "float64",
                    "total_timer_time": "float64",
                    "total_ascent": "int64",
                    "total_descent": "int64",
                    "avg_vertical_oscillation": "float64",
                    "avg_stance_time": "float64",
                    "avg_vertical_ratio": "float64",
                    "avg_stance_time_balance": "float64",
                    "avg_step_length": "float64",
                    "intensity": "object",
                    "avg_running_cadence": "int64",
                    "max_heart_rate": "int64",
                    "avg_heart_rate": "int64",
                }

                existing_dtypes = {
                    col: dtype
                    for col, dtype in desired_dtypes.items()
                    if col in df.columns
                }
                if existing_dtypes:
                    df = df.astype(existing_dtypes)

                for col in desired_dtypes.keys():
                    if col not in df.columns:
                        df[col] = None

                values_list = []

                for index, row in df.iterrows():
                    # Create the value group for this specific row
                    row_str = (
                        f"("
                        f"{sql_format(row['activity_id'])}, "
                        f"{sql_format(row['number'])}, "
                        f"{sql_format(row['start_time'], quote=True)}, "
                        f"{sql_format(row['total_distance'])}, "
                        f"{sql_format(row['total_timer_time'])}, "
                        f"{sql_format(row['total_ascent'])}, "
                        f"{sql_format(row['total_descent'])}, "
                        f"{sql_format(row['avg_vertical_oscillation'])}, "
                        f"{sql_format(row['avg_stance_time'])}, "
                        f"{sql_format(row['avg_vertical_ratio'])}, "
                        f"{sql_format(row['avg_stance_time_balance'])}, "
                        f"{sql_format(row['avg_step_length'])}, "
                        f"{sql_format(row['intensity'], quote=True)}, "
                        f"{sql_format(row['avg_running_cadence'])}, "
                        f"{sql_format(row['max_heart_rate'])}, "
                        f"{sql_format(row['avg_heart_rate'])}"
                        f")"
                    )
                    values_list.append(row_str)

                if values_list:
                    # Join all rows with a comma and newline
                    bulk_values = ",\n".join(values_list)

                    # Construct the final bulk insert statement
                    sql = f"""
                    INSERT INTO lap(
                        activity_id, number, start_time, total_distance, 
                        total_timer_time, total_ascent, total_descent, 
                        avg_vertical_oscillation, avg_stance_time, avg_vertical_ratio, 
                        avg_stance_time_balance, avg_step_length, intensity, 
                        avg_running_cadence, max_heart_rate, avg_heart_rate
                    )
                    VALUES 
                    {bulk_values};
                    """

                    log_file.write(sql + "\n")

            # --- Record Table ---
            elif tabl == "record":
                # *** REVIEW/EDIT THIS SCHEMA ***
                desired_dtypes = {
                    "activity_id": "int64",
                    "latitude": "float64",
                    "longitude": "float64",
                    "lap": "int64",
                    "altitude": "float64",
                    "timestamp": "datetime64[ns, UTC]",
                    "heart_rate": "int64",
                    "cadence": "int64",
                    "fractional_cadence": "float64",
                    "enhanced_speed": "int64",
                    "distance": "float64",
                }

                existing_dtypes = {
                    col: dtype
                    for col, dtype in desired_dtypes.items()
                    if col in df.columns
                }
                if existing_dtypes:
                    df = df.astype(existing_dtypes)

                for col in desired_dtypes.keys():
                    if col not in df.columns:
                        df[col] = None

                values_list = []

                for index, row in df.iterrows():
                    # Create a tuple of formatted strings using your existing helper function
                    row_values = (
                        f"{sql_format(row['activity_id'])}",
                        f"{sql_format(row['latitude'])}",
                        f"{sql_format(row['longitude'])}",
                        f"{sql_format(row['lap'])}",
                        f"{sql_format(row['altitude'])}",
                        f"{sql_format(row['timestamp'], quote=True)}",
                        f"{sql_format(row['heart_rate'])}",
                        f"{sql_format(row['cadence'])}",
                        f"{sql_format(row['fractional_cadence'])}",
                        f"{sql_format(row['enhanced_speed'])}",
                        f"{sql_format(row['distance'])}",
                    )

                    # Join the row values with commas and wrap in parentheses -> (val1, val2, ...)
                    values_list.append(f"({', '.join(row_values)})")

                # 3. Join all rows with a comma and a newline for readability
                bulk_values = ",\n".join(values_list)

                # 4. Construct the final single statement
                sql = f"""
                INSERT INTO record(
                    activity_id, latitude, longitude, lap, altitude, 
                    timestamp, heart_rate, cadence, fractional_cadence, 
                    enhanced_speed, distance
                )
                VALUES 
                {bulk_values};
                """

                log_file.write(sql + "\n")

            # --- File ID Table ---
            elif tabl == "file_id":
                # *** REVIEW/EDIT THIS SCHEMA ***
                desired_dtypes = {
                    "activity_id": "int64",
                    "type": "object",
                    "manufacturer": "object",
                    "product": "int64",
                    "serial_number": "int64",
                    "time_created": "datetime64[ns, UTC]",
                    "number": "float",  # Changed from int64 to float to handle NaN
                }

                existing_dtypes = {
                    col: dtype
                    for col, dtype in desired_dtypes.items()
                    if col in df.columns
                }

                if existing_dtypes:
                    # Handle potential conversion errors if 'product' is not purely numeric
                    for col, dtype in existing_dtypes.items():
                        try:
                            if dtype == "int64":
                                # Convert to float first to handle NaNs, then to nullable Int64
                                df[col] = (
                                    pd.to_numeric(df[col], errors="coerce")
                                    .astype("float")
                                    .astype("Int64")
                                )
                            else:
                                df = df.astype({col: dtype})
                        except Exception as e:
                            print(
                                f"Error casting column {col} to {dtype}: {e}. Forcing to object."
                            )
                            df = df.astype({col: "object"})  # Fallback

                for col in desired_dtypes.keys():
                    if col not in df.columns:
                        df[col] = None

                values_list = []

                for index, row in df.iterrows():
                    # Create the value group for this specific row
                    row_str = (
                        f"("
                        f"{sql_format(row['activity_id'])}, "
                        f"{sql_format(row['type'], quote=True)}, "
                        f"{sql_format(row['manufacturer'], quote=True)}, "
                        f"{sql_format(row['product'])}, "
                        f"{sql_format(row['serial_number'])}, "
                        f"{sql_format(row['time_created'], quote=True)}, "
                        f"{sql_format(row['number'])}"
                        f")"
                    )
                    values_list.append(row_str)

                if values_list:
                    # Join all rows with a comma and newline
                    bulk_values = ",\n".join(values_list)

                    # Construct the final bulk insert statement
                    sql = f"""
                    INSERT INTO file_id(
                        activity_id, type, manufacturer, product, 
                        serial_number, time_created, number
                    )
                    VALUES 
                    {bulk_values};
                    """

                    log_file.write(sql + "\n")

            # --- Length Table ---
            elif tabl == "length":
                # *** REVIEW/EDIT THIS SCHEMA ***
                desired_dtypes = {
                    "activity_id": "int64",
                    "timestamp": "datetime64[ns, UTC]",
                    "start_time": "datetime64[ns, UTC]",
                    "total_elapsed_time": "float64",
                    "total_timer_time": "float64",
                    "total_strokes": "int64",
                    "avg_speed": "float64",
                    "swim_stroke": "object",
                }

                existing_dtypes = {
                    col: dtype
                    for col, dtype in desired_dtypes.items()
                    if col in df.columns
                }
                if existing_dtypes:
                    # This was the typo in the previous version
                    df = df.astype(existing_dtypes)

                for col in desired_dtypes.keys():
                    if col not in df.columns:
                        df[col] = None

                values_list = []

                for index, row in df.iterrows():
                    # Create the value group for this specific row
                    row_str = (
                        f"("
                        f"{sql_format(row['activity_id'])}, "
                        f"{sql_format(row['timestamp'], quote=True)}, "
                        f"{sql_format(row['start_time'], quote=True)}, "
                        f"{sql_format(row['total_elapsed_time'])}, "
                        f"{sql_format(row['total_timer_time'])}, "
                        f"{sql_format(row['total_strokes'])}, "
                        f"{sql_format(row['avg_speed'])}, "
                        f"{sql_format(row['swim_stroke'], quote=True)}"
                        f")"
                    )
                    values_list.append(row_str)

                if values_list:
                    # Join all rows with a comma and newline
                    bulk_values = ",\n".join(values_list)

                    # Construct the final bulk insert statement
                    sql = f"""
                    INSERT INTO length(
                        activity_id, timestamp, start_time, total_elapsed_time, 
                        total_timer_time, total_strokes, avg_speed, swim_stroke
                    )
                    VALUES 
                    {bulk_values};
                    """

                    log_file.write(sql + "\n")

            # --- Else: Unknown Table ---
            else:
                print(
                    f"Warning: No specific SQL generation logic defined for table '{tabl}'. No statements written."
                )


# ----------------------------------------
# MAIN LOGIC FOR WATCH FILES
# ----------------------------------------

if __name__ == "__main__":

    dir = "example activities/Activity/"
    file_extension = ".fit"

    after_date = datetime(2025, 8, 2).date()
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
            get_dataframes(fname, 1)
        )

        # the following only works with one activity per activity_df and therefore one activity in session_df
        activity_df.loc[0, "adjusted_distance"] = session_df["total_distance"].sum()
        activity_df.loc[0, "adjusted_duration"] = session_df["total_timer_time"].sum()
        activity_df.loc[0, "activity_name"] = build_default_activity_name(
            session_df, activity_df
        )

        # write_sql_statement_to_file_watch(activity_df, "activity")
        # write_sql_statement_to_file_watch(file_id_df, "file_id")
        # write_sql_statement_to_file_watch(lap_df, "lap")
        # write_sql_statement_to_file_watch(record_df, "record")
        write_sql_statement_to_file_watch(session_df, "session")
        # write_sql_statement_to_file_watch(length_df, "length")

        # TODO:
        # activity id needs to be returned from the first insert statement
        # record data lap column looks like total laps + 1 for new watch? gonna have to determine laps based on distances compared to lap def
        # Need to update session definition so lat and long are stored as floats
        # I'm not sure if this will be a problem, but df values are forced as floats to handle nans when in database they are Ints
