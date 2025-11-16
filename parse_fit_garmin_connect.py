# parse_fit_garmin_connect.py
# This file handles Garmin Connect files (summary JSON + FIT)
# Uses old SQL writer + live database loader

import os
import toml
import pandas as pd
from os import listdir
from os.path import isfile, join
from datetime import datetime

from helpers import (
    extract_date_from_filename_connect,
    get_user_activity_details,
    get_json_info,
    get_dataframes,
)

# ------------------------------------
# DB LOADING LOGIC (OLD)
# ------------------------------------

import psycopg2

config = toml.load("secrets.toml")
db_config = config["postgresql"]
conn = psycopg2.connect(**db_config)


def load_dataframe_to_postgres(df, tabl):
    """Old DB insert loader: writes row-by-row into Postgres. This wasn't working in the old version parse fit nixos, and I don't plan on copying it over here, but just in case, I will leave this where it was."""
    if df.empty:
        return

    df = df.fillna(0).infer_objects(copy=False)
    cursor = conn.cursor()

    conn.commit()
    cursor.close()


# ------------------------------------
# OLD SQL WRITER (NO _watch SUFFIX)
# ------------------------------------


def write_sql_statement_to_file(df, tabl, log_file_path=None):
    """Takes a dataframe and it's source FIT file type,
    if dataframe is not empty then it is filled up with 0 for NaN values,
    dataframe is checked against the general schema per FIT file type - proper data types are assigned to the columns,
    through the iterations rows are sent to postgres DB with the use of INSERT INTO statement

    Parameters:
    -----------
    df : pandas.DataFrame
        The dataframe to be loaded into PostgreSQL
    tabl : str
        The name of the table to load data into
    log_file_path : str, optional
        Path to log file where SQL insert statements will be written
    """
    # If log file path is not provided, create a default path in the same directory
    if log_file_path is None:
        log_file_path = os.path.join(os.path.dirname(__file__), f"{tabl}_inserts.sql")

    print(f"writing file to {log_file_path} . . .")
    # Open log file in write mode
    with open(log_file_path, "a") as log_file:
        log_file.write("\n\n")
        if not df.empty:
            # df = df.fillna(0).infer_objects(copy=False)

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
                # df = df.astype({'activity_id': 'int64','timestamp': 'datetime64[ns, UTC]', 'adjusted_distance': 'float64', 'adjusted_duration': 'float64', 'workout_feel': 'int64', 'effort': 'int64', 'category': 'object', 'activity_name': 'object', 'description': 'object',
                #                 'total_timer_time': 'float64', 'local_timestamp': 'datetime64[ns]', 'num_sessions': 'int64', 'type': 'object', 'event': 'object', 'event_type': 'object', 'event_group': 'object'})
                for col in desired_dtypes.keys():
                    if col not in df.columns:
                        df[col] = None
                if "description" in df.columns:
                    # Only replace quotes where description is not null; keep NaN/None as-is
                    df.loc[df["description"].notna(), "description"] = (
                        df.loc[df["description"].notna(), "description"]
                        .astype(str)
                        .str.replace("'", "''", regex=False)
                    )
                for index, row in df.iterrows():
                    # Prepare SQL insert statement with proper escaping
                    sql = f"""INSERT INTO activity(activity_id, timestamp, adjusted_distance, adjusted_duration, workout_feel, effort, category, activity_name, description, total_timer_time, local_timestamp, num_sessions, type, event, event_type, event_group)
                    VALUES ({row['activity_id']}, '{row['timestamp']}', {row['adjusted_distance']}, {row['adjusted_duration']}, {row['workout_feel']}, {row['effort']}, '{row['category']}', '{row['activity_name']}', '{row['description']}', {row['total_timer_time']}, '{row['local_timestamp']}', {row['num_sessions']}, '{row['type']}', '{row['event']}', '{row['event_type']}', '{row['event_group']}')
                    ON CONFLICT (activity_id) DO NOTHING;"""

                    # Write to log file
                    log_file.write(sql + "\n")

                    # Execute in database
                    # cursor.execute("""insert into activity(activity_id, timestamp, adjusted_distance, adjusted_duration, workout_feel, effort, category, activity_name, description, total_timer_time, local_timestamp, num_sessions, type, event, event_type, event_group)
                    # values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", [row['activity_id'], row['timestamp'], row['adjusted_distance'], row['adjusted_duration'], row['workout_feel'], row['effort'], row['category'], row['activity_name'], row['description'], row['total_timer_time'], row['local_timestamp'], row['num_sessions'], row['type'], row['event'], row['event_type'], row['event_group']])

            elif tabl == "file_id":
                df.rename(columns={"product": "product_name"}, inplace=True)
                df = df.astype(
                    {
                        "activity_id": "int64",
                        "serial_number": "int64",
                        "time_created": "datetime64[ns, UTC]",
                        "manufacturer": "object",
                        "product_name": "object",
                        "number": "float64",
                        "type": "object",
                    }
                )
                for index, row in df.iterrows():
                    # Prepare SQL insert statement with proper escaping
                    sql = f"""INSERT INTO file_id(activity_id, serial_number, time_created, manufacturer, product, number, type)
                    VALUES ({row['activity_id']}, {row['serial_number']}, '{row['time_created']}', '{row['manufacturer']}', '{row['product_name']}', {row['number']}, '{row['type']}');"""

                    # Write to log file
                    log_file.write(sql + "\n")

                    # Execute in database
                    # cursor.execute("""insert into file_id(activity_id, serial_number, time_created, manufacturer, product, number, type)
                    # values (%s, %s, %s, %s, %s, %s, %s)""", [row['activity_id'], row['serial_number'], row['time_created'], row['manufacturer'], row['product_name'], row['number'], row['type']])

            elif tabl == "lap":
                available_dtypes = {
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

                # Filter to only include columns that exist in the DataFrame
                existing_dtypes = {
                    col: dtype
                    for col, dtype in available_dtypes.items()
                    if col in df.columns
                }
                df = df.astype(existing_dtypes)
                if "intensity" not in df.columns:
                    df["intensity"] = None  # or some default value like 'unknown'
                for index, row in df.iterrows():
                    # Prepare SQL insert statement with proper escaping
                    sql = f"""INSERT INTO lap(
                        activity_id, number, start_time, total_distance, total_timer_time,
                        total_ascent, total_descent, avg_vertical_oscillation, avg_stance_time,
                        avg_vertical_ratio, avg_stance_time_balance, avg_step_length, intensity,
                        avg_running_cadence, max_heart_rate, avg_heart_rate
                    ) VALUES (
                        {row['activity_id']}, {row['number']}, '{row['start_time']}', {row['total_distance']},
                        {row['total_timer_time']}, {row['total_ascent']}, {row['total_descent']},
                        {row['avg_vertical_oscillation']}, {row['avg_stance_time']}, {row['avg_vertical_ratio']},
                        {row['avg_stance_time_balance']}, {row['avg_step_length']}, '{row['intensity']}',
                        {row['avg_running_cadence']}, {row['max_heart_rate']}, {row['avg_heart_rate']}
                    );"""

                    # Write to log file
                    log_file.write(sql + "\n")

                    # Execute in database
                    # cursor.execute("""
                    #     INSERT INTO lap(
                    #         activity_id, number, start_time, total_distance, total_timer_time,
                    #         total_ascent, total_descent, avg_vertical_oscillation, avg_stance_time,
                    #         avg_vertical_ratio, avg_stance_time_balance, avg_step_length, intensity,
                    #         avg_running_cadence, max_heart_rate, avg_heart_rate
                    #     ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    #     """,
                    #     [
                    #         row['activity_id'], row['number'], row['start_time'], row['total_distance'],
                    #         row['total_timer_time'], row['total_ascent'], row['total_descent'],
                    #         row['avg_vertical_oscillation'], row['avg_stance_time'], row['avg_vertical_ratio'],
                    #         row['avg_stance_time_balance'], row['avg_step_length'], row['intensity'],
                    #         row['avg_running_cadence'], row['max_heart_rate'], row['avg_heart_rate'],
                    #     ]
                    # )

            elif tabl == "record":
                df = df.astype(
                    {
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
                )
                for index, row in df.iterrows():
                    # Prepare SQL insert statement
                    sql = f"""INSERT INTO record(activity_id, latitude, longitude, lap, altitude, timestamp, heart_rate, cadence, fractional_cadence, enhanced_speed, distance)
                    VALUES ({row['activity_id']}, {row['latitude']}, {row['longitude']}, {row['lap']}, {row['altitude']}, '{row['timestamp']}', {row['heart_rate']}, {row['cadence']}, {row['fractional_cadence']}, {row['enhanced_speed']}, {row['distance']});"""

                    # Write to log file
                    log_file.write(sql + "\n")

                    # Execute in database
                    # cursor.execute("""insert into record(activity_id, latitude, longitude, lap, altitude, timestamp, heart_rate, cadence, fractional_cadence, enhanced_speed, distance)
                    # values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", [row['activity_id'], row['latitude'], row['longitude'], row['lap'], row['altitude'], row['timestamp'], row['heart_rate'], row['cadence'], row['fractional_cadence'], row['enhanced_speed'], row['distance']])

            elif tabl == "session":
                df = df.astype(
                    {
                        "activity_id": "int64",
                        "timestamp": "datetime64[ns, UTC]",
                        "start_time": "datetime64[ns, UTC]",
                        "start_position_lat": "int64",
                        "start_position_long": "int64",
                        "total_elapsed_time": "float64",
                        "total_timer_time": "float64",
                        "total_distance": "float64",
                        "total_strokes": "float64",
                        "nec_lat": "int64",
                        "nec_long": "int64",
                        "swc_lat": "int64",
                        "swc_long": "int64",
                        "message_index": "int64",
                        "total_calories": "int64",
                        "total_fat_calories": "float64",
                        "enhanced_avg_speed": "float64",
                        "avg_speed": "float64",
                        "enhanced_max_speed": "float64",
                        "max_speed": "float64",
                        "avg_power": "float64",
                        "max_power": "float64",
                        "total_ascent": "int64",
                        "total_descent": "int64",
                        "first_lap_index": "int64",
                        "num_laps": "int64",
                        "event": "object",
                        "event_type": "object",
                        "sport": "object",
                        "sub_sport": "object",
                        "avg_heart_rate": "int64",
                        "max_heart_rate": "int64",
                        "avg_cadence": "int64",
                        "max_cadence": "int64",
                        "total_training_effect": "float64",
                        "event_group": "float64",
                        "trigger": "object",
                        "pool_length": "int64",
                        "pool_length_unit": "object",
                    }
                )
                for index, row in df.iterrows():
                    # Prepare SQL insert statement with proper escaping
                    sql = f"""INSERT INTO session(activity_id, timestamp, start_time, start_position_lat, 
                    start_position_long, total_elapsed_time, total_timer_time, total_distance, total_strokes, nec_lat, 
                    nec_long, swc_lat, swc_long, message_index, total_calories, total_fat_calories, enhanced_avg_speed,
                    avg_speed, enhanced_max_speed, max_speed, avg_power, max_power, total_ascent, total_descent, first_lap_index,
                    num_laps, event, event_type, sport, sub_sport, avg_heart_rate, max_heart_rate, avg_cadence, max_cadence, 
                    total_training_effect, event_group, trigger, pool_length, pool_length_unit) 
                    VALUES ({row['activity_id']}, '{row['timestamp']}', '{row['start_time']}', {row['start_position_lat']}, {row['start_position_long']}, 
                    {row['total_elapsed_time']}, {row['total_timer_time']}, {row['total_distance']}, {row['total_strokes']}, {row['nec_lat']}, 
                    {row['nec_long']}, {row['swc_lat']}, {row['swc_long']}, {row['message_index']}, {row['total_calories']}, {row['total_fat_calories']}, {row['enhanced_avg_speed']},
                    {row['avg_speed']}, {row['enhanced_max_speed']}, {row['max_speed']}, {row['avg_power']}, {row['max_power']}, {row['total_ascent']}, {row['total_descent']}, {row['first_lap_index']},
                    {row['num_laps']}, '{row['event']}', '{row['event_type']}', '{row['sport']}', '{row['sub_sport']}', {row['avg_heart_rate']}, {row['max_heart_rate']}, {row['avg_cadence']}, {row['max_cadence']}, 
                    {row['total_training_effect']}, {row['event_group']}, '{row['trigger']}', {row['pool_length']}, '{row['pool_length_unit']}');"""

                    # Write to log file
                    log_file.write(sql + "\n")

                    # Execute in database
                #     cursor.execute("""insert into session(activity_id, timestamp, start_time, start_position_lat,
                #  start_position_long, total_elapsed_time, total_timer_time, total_distance, total_strokes, nec_lat,
                #  nec_long, swc_lat, swc_long, message_index, total_calories, total_fat_calories, enhanced_avg_speed,
                #  avg_speed, enhanced_max_speed, max_speed, avg_power, max_power, total_ascent, total_descent, first_lap_index,
                #  num_laps, event, event_type, sport, sub_sport, avg_heart_rate, max_heart_rate, avg_cadence, max_cadence,
                #  total_training_effect, event_group, trigger, pool_length, pool_length_unit) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                #  %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, %s, %s)""",\
                # [row['activity_id'], row['timestamp'], row['start_time'], row['start_position_lat'], row['start_position_long'], \
                #  row['total_elapsed_time'], row['total_timer_time'], row['total_distance'], row['total_strokes'], row['nec_lat'], \
                #  row['nec_long'], row['swc_lat'], row['swc_long'], row['message_index'], row['total_calories'], row['total_fat_calories'], \
                #  row['enhanced_avg_speed'], row['avg_speed'], row['enhanced_max_speed'], row['max_speed'], row['avg_power'], \
                #  row['max_power'], row['total_ascent'], row['total_descent'], row['first_lap_index'], row['num_laps'], row['event'], \
                #  row['event_type'], row['sport'], row['sub_sport'], row['avg_heart_rate'], row['max_heart_rate'], row['avg_cadence'], \
                #  row['max_cadence'], row['total_training_effect'], row['event_group'], row['trigger'], row['pool_length'], row['pool_length_unit']])

        elif tabl == "length":
            df = df.astype(
                {
                    "activity_id": "int64",
                    "timestamp": "datetime64[ns, UTC]",
                    "start_time": "datetime64[ns, UTC]",
                    "message_index": "int64",
                    "total_timer_time": "float64",
                    "total_strokes": "int64",
                    "avg_speed": "float64",
                    "swim_stroke": "object",
                    "length_type": "object",
                }
            )
            for index, row in df.iterrows():
                # Prepare SQL insert statement with proper escaping
                sql = f"""INSERT INTO length(activity_id, timestamp, start_time, message_index, total_timer_time, total_strokes, avg_speed, swim_stroke, length_type) 
                VALUES ({row['activity_id']}, '{row['timestamp']}', '{row['start_time']}', {row['message_index']}, {row['total_timer_time']}, {row['total_strokes']}, {row['avg_speed']}, '{row['swim_stroke']}', '{row['length_type']}');"""

                # Write to log file
                log_file.write(sql + "\n")

                # Execute in database
                # cursor.execute("""insert into length(activity_id, timestamp, start_time, message_index, total_timer_time, total_strokes, avg_speed, swim_stroke, length_type) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)""", \
                # [row['activity_id'], row['timestamp'], row['start_time'], row['message_index'], row['total_timer_time'], row['total_strokes'], row['avg_speed'], row['swim_stroke'], row['length_type']])


# ------------------------------------
# GARMIN CONNECT MAIN LOGIC
# ------------------------------------

if __name__ == "__main__":

    dir = "example activities/Activity/"
    file_extension = ".fit"

    after_date = datetime(2025, 8, 2).date()
    today = datetime.now().date()

    files = [
        f for f in listdir(dir) if isfile(join(dir, f)) and f.endswith(file_extension)
    ]

    filtered_files = [
        f for f in files if after_date < extract_date_from_filename_connect(f) <= today
    ]

    errors = []

    for file in filtered_files:
        try:
            fname = dir + file
            json_file = fname.replace(file_extension, "_summary.json")

            activity_id = get_user_activity_details(fname)

            lap_df, record_df, file_id_df, activity_df, session_df, length_df = (
                get_dataframes(fname, activity_id)
            )

            json_info_df = pd.DataFrame(get_json_info(json_file), index=[0])
            activity_df_fixed = pd.concat([activity_df, json_info_df], axis=1)

            # Old SQL style
            # load_dataframe_to_postgres(activity_df_fixed, "activity")
            # load_dataframe_to_postgres(file_id_df, "file_id")
            # load_dataframe_to_postgres(lap_df, "lap")
            # load_dataframe_to_postgres(record_df, "record")
            # load_dataframe_to_postgres(session_df, "session")
            # load_dataframe_to_postgres(length_df, "length")

            # write to files here
            write_sql_statement_to_file(activity_df_fixed, "activity")

        except Exception as e:
            print("ERROR:", e)
            errors.append(file)

    print("Finished. Errors:", errors)
