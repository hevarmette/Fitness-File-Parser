"""Some functions for parsing a FIT files mandatory tables (activity, file_id, session, lap and record)
and creating a Pandas DataFrame with the data, bulk upload for dataframes to PostgreSQL DB
GET INFORMATION FROM SUMMARY_JSON AND FIX LAT AND LONG FROM
FROM SUMMARY_JSON: Distance because manually edited distances will not be in .fit file
Duration for same reason
"summaryDTO.distance": "Distance",
"summaryDTO.duration": "Duration",
"summaryDTO.directWorkoutFeel": "Workout Feel",
"summaryDTO.directWorkoutRpe": "Effort",
"eventTypeDTO.typeKey": "Category",
"activityName": "Activity Name",
"description": "Description"
"""

from datetime import datetime, timedelta
from typing import Dict, Union, Optional, Tuple
import os
import pandas as pd
import fitdecode
import json
import toml
from os import listdir
from os.path import isfile, join

# The path to the folder with all FIT files to be processed
dir = r"example activities/Activity/"
# dir = r"/home/heath/Documents/Updated Garmin/"  # LINUX
file_extension = ".fit"
test = True
# Connection details for Postgresql DB.
if not test:
    import psycopg2
    config = toml.load("secrets.toml")
    db_config = config["postgresql"]
    conn = psycopg2.connect(**db_config)

# The names of the columns we will use in our points DataFrame. For the data we will be getting
# from the FIT data, we use the same name as the field names to make it easier to parse the data.
record = [
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
]

# The names of the columns we will use in our laps DataFrame.
lap = [
    "number",
    "start_time",
    "total_distance",
    "total_timer_time",
    "total_ascent",
    "total_descent",
    "avg_heart_rate",
    "max_heart_rate",
    "avg_step_length",
    "avg_stance_time",
    "avg_stance_time_balance",
    "avg_running_cadence",
    "avg_vertical_oscillation",
    "avg_vertical_ratio",
]

# The names of the columns in file_id DataFrame
file_id = ["serial_number", "time_created", "manufacturer", "product", "number", "type"]

# The names of the columns in activity DataFrame
activity = [
    "timestamp",
    "total_timer_time",
    "local_timestamp",
    "num_sessions",
    "type",
    "event",
    "event_type",
    "event_group",
]

# The names of the columns in session DataFrame
session = [
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
]

length = [
    "timestamp",
    "start_time",
    "message_index",
    "total_timer_time",
    "total_strokes",
    "avg_speed",
    "swim_stroke",
    "length_type",
]
# field names in the length frame: {'timestamp', 'total_timer_time', 'total_elapsed_time', 'unknown_26', 'event_group', 'length_type', 'total_strokes', 'start_time', 'unknown_23', 'total_calories', 'event', 'avg_speed', 'unknown_22', 'avg_swimming_cadence', 'swim_stroke', 'message_index', 'event_type'}. check equivalent fields in the set between pre determined workouts. unrelated, but fix training labels on last 3 running workouts. the fields I think are equivalent so far are total_timer_time = total_elapsed_time, get rid of swimming cadence because it is strokes/min which can be figured out from total strokes/length, get rid of event, value is just length, get rid of event_type, all just stop value.


def isNan(num):
    """Checks if a value is Nan. This was created because intensities in a fit file can be Nan for some reason"""
    return num != num


def unique(list1):
    """drops duplicates in a list. this function was created to obtain a list of intensities with no duplicates"""
    unique_list = pd.Series(list1).drop_duplicates().tolist()
    return unique_list


def get_json_info(file):
    """this function reads _summary.json files downloaded from garmin. this has the desired keys, what i want to replace the
    keys with for ease of reading, and returns a dictionary of the information. subkeys follow periods.
    """
    desired_keys = [
        "summaryDTO.distance",
        "summaryDTO.duration",
        "summaryDTO.directWorkoutFeel",
        "summaryDTO.directWorkoutRpe",
        "eventTypeDTO.typeKey",
        "activityName",
        "description",
    ]
    key_mapping = {
        "summaryDTO.distance": "adjusted_distance",
        "summaryDTO.duration": "adjusted_duration",
        "summaryDTO.directWorkoutFeel": "workout_feel",
        "summaryDTO.directWorkoutRpe": "effort",
        "eventTypeDTO.typeKey": "category",
        "activityName": "activity_name",
        "description": "description",
    }
    # try statement to read json file handling for unicode character error cause i got some emojis in descriptions.
    # this function will still throw an error if the file does not exist, i believe.

    try:
        # Read the JSON file
        with open(file, "r", encoding="utf-8") as json_file:
            data = json.load(json_file)

        # Extract the information based on desired keys
        extracted_info = {
            key_mapping[key]: get_nested_value(data, key.split("."))
            for key in desired_keys
        }
        return extracted_info

    except UnicodeDecodeError as e:
        print(f"Error reading file {file}: {e}")
        return None
    except Exception as e:
        print(f"Error processing file {file}: {e}")
        return None


def get_nested_value(data, keys_chain):
    """this function parses subkeys given key chains that are delimited. delimiter can be specified in the keys_chain
    parameter when calling the function"""
    value = data
    for sub_key in keys_chain:
        if isinstance(value, dict) and sub_key in value:
            value = value[sub_key]
        elif isinstance(value, list) and sub_key.isdigit():
            index = int(sub_key)
            if index < len(value):
                value = value[index]
            else:
                value = None
                break
        else:
            value = None
            break
    return value


def get_user_activity_details(file):
    """Extract user_id and activity_id from the FIT file name
    in order to get unique instance for the activity
    """
    filename = os.path.basename(file)
    activity_id = filename.split("_")[1]
    if "." in activity_id:
        activity_id = activity_id.split(".")[0]

    return activity_id


def load_dataframe_to_postgres(df, tabl):
    """Takes a dataframe and it's source FIT file type,
    if dataframe is not empty then it is filled up with 0 for NaN values,
    dataframe is checked against the general schema per FIT file type - proper data types are assigned to the columns,
    through the iterations rows are sent to postgres DB with the use of INSERT INTO statement
    """
    if not df.empty:
        df = df.fillna(0).infer_objects(copy=False)
        cursor = conn.cursor()
        if tabl == "activity":
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
                col: dtype for col, dtype in desired_dtypes.items() if col in df.columns
            }

            # Apply the conversion
            df = df.astype(existing_dtypes)
            # df = df.astype({'activity_id': 'int64','timestamp': 'datetime64[ns, UTC]', 'adjusted_distance': 'float64', 'adjusted_duration': 'float64', 'workout_feel': 'int64', 'effort': 'int64', 'category': 'object', 'activity_name': 'object', 'description': 'object',
            #                 'total_timer_time': 'float64', 'local_timestamp': 'datetime64[ns]', 'num_sessions': 'int64', 'type': 'object', 'event': 'object', 'event_type': 'object', 'event_group': 'object'})
            for col in desired_dtypes.keys():
                if col not in df.columns:
                    df[col] = None
            for index, row in df.iterrows():
                cursor.execute(
                    """insert into activity(activity_id, timestamp, adjusted_distance, adjusted_duration, workout_feel, effort, category, activity_name, description, total_timer_time, local_timestamp, num_sessions, type, event, event_type, event_group)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    [
                        row.activity_id,
                        row.timestamp,
                        row.adjusted_distance,
                        row.adjusted_duration,
                        row.workout_feel,
                        row.effort,
                        row.category,
                        row.activity_name,
                        row.description,
                        row.total_timer_time,
                        row.local_timestamp,
                        row.num_sessions,
                        row.type,
                        row.event,
                        row.event_type,
                        row.event_group,
                    ],
                )

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
                cursor.execute(
                    """insert into file_id(activity_id, serial_number, time_created, manufacturer, product, number, type)
                values (%s, %s, %s, %s, %s, %s, %s)""",
                    [
                        row.activity_id,
                        row.serial_number,
                        row.time_created,
                        row.manufacturer,
                        row.product_name,
                        row.number,
                        row.type,
                    ],
                )

        elif tabl == "lap":
            df = df.astype(
                {
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
            )

            for index, row in df.iterrows():
                cursor.execute(
                    """
                    INSERT INTO lap(
                        activity_id, number, start_time, total_distance, total_timer_time,
                        total_ascent, total_descent, avg_vertical_oscillation, avg_stance_time,
                        avg_vertical_ratio, avg_stance_time_balance, avg_step_length, intensity,
                        avg_running_cadence, max_heart_rate, avg_heart_rate
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        row.activity_id,
                        row.number,
                        row.start_time,
                        row.total_distance,
                        row.total_timer_time,
                        row.total_ascent,
                        row.total_descent,
                        row.avg_vertical_oscillation,
                        row.avg_stance_time,
                        row.avg_vertical_ratio,
                        row.avg_stance_time_balance,
                        row.avg_step_length,
                        row.intensity,
                        row.avg_running_cadence,
                        row.max_heart_rate,
                        row.avg_heart_rate,
                    ],
                )

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
                cursor.execute(
                    """insert into record(activity_id, latitude, longitude, lap, altitude, timestamp, heart_rate, cadence, fractional_cadence, enhanced_speed, distance)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    [
                        row.activity_id,
                        row.latitude,
                        row.longitude,
                        row.lap,
                        row.altitude,
                        row.timestamp,
                        row.heart_rate,
                        row.cadence,
                        row.fractional_cadence,
                        row.enhanced_speed,
                        row.distance,
                    ],
                )

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
                cursor.execute(
                    """insert into session(activity_id, timestamp, start_time, start_position_lat, 
                start_position_long, total_elapsed_time, total_timer_time, total_distance, total_strokes, nec_lat, 
                nec_long, swc_lat, swc_long, message_index, total_calories, total_fat_calories, enhanced_avg_speed,
                avg_speed, enhanced_max_speed, max_speed, avg_power, max_power, total_ascent, total_descent, first_lap_index,
                num_laps, event, event_type, sport, sub_sport, avg_heart_rate, max_heart_rate, avg_cadence, max_cadence, 
                total_training_effect, event_group, trigger, pool_length, pool_length_unit) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, %s, %s)""",
                    [
                        row.activity_id,
                        row.timestamp,
                        row.start_time,
                        row.start_position_lat,
                        row.start_position_long,
                        row.total_elapsed_time,
                        row.total_timer_time,
                        row.total_distance,
                        row.total_strokes,
                        row.nec_lat,
                        row.nec_long,
                        row.swc_lat,
                        row.swc_long,
                        row.message_index,
                        row.total_calories,
                        row.total_fat_calories,
                        row.enhanced_avg_speed,
                        row.avg_speed,
                        row.enhanced_max_speed,
                        row.max_speed,
                        row.avg_power,
                        row.max_power,
                        row.total_ascent,
                        row.total_descent,
                        row.first_lap_index,
                        row.num_laps,
                        row.event,
                        row.event_type,
                        row.sport,
                        row.sub_sport,
                        row.avg_heart_rate,
                        row.max_heart_rate,
                        row.avg_cadence,
                        row.max_cadence,
                        row.total_training_effect,
                        row.event_group,
                        row.trigger,
                        row.pool_length,
                        row.pool_length_unit,
                    ],
                )

        elif tabl == "length":
            # check if these are right: message_index, total_strokes
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
                cursor.execute(
                    """insert into length(activity_id, timestamp, start_time, message_index, total_timer_time, total_strokes, avg_speed, swim_stroke, length_type) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    [
                        row.activity_id,
                        row.timestamp,
                        row.start_time,
                        row.message_index,
                        row.total_timer_time,
                        row.total_strokes,
                        row.avg_speed,
                        row.swim_stroke,
                        row.length_type,
                    ],
                )

        conn.commit()
        cursor.close()

def write_sql_statement_to_file_watch(df, tabl, log_file_path=None):
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
    
    # --- START OF CHANGES ---

    def sql_format(value, quote=False):
        """
        Helper function to format Python values for a SQL statement.
        - Converts None, np.nan, and pd.NaT to NULL.
        - Quotes and escapes strings/datetimes.
        """
        # pd.isna() is a universal check for None, np.nan, and pd.NaT
        if pd.isna(value):
            return "NULL"
        
        if quote:
            # Escape single quotes for SQL
            safe_value = str(value).replace("'", "''")
            return f"'{safe_value}'"
        
        # Return numbers/bools as-is
        return str(value)

    # --- END OF CHANGES ---


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

                for col in desired_dtypes.keys():
                    if col not in df.columns:
                        df[col] = None
                
                # --- CHANGE ---
                # This complex block is no longer needed,
                # as the sql_format function will handle escaping for all
                # string fields, not just 'description'.
                #
                # if "description" in df.columns:
                #     ... (removed old logic) ...
                
                # --- CHANGE ---
                # We standardize all null types (np.nan, pd.NaT) to None
                # This isn't strictly necessary since sql_format uses pd.isna(),
                # but it makes the row data cleaner before formatting.
                # df = df.where(pd.notna(df), None)

                for index, row in df.iterrows():
                    
                    # --- CHANGE ---
                    # Use the new sql_format() helper for every value
                    sql = f"""INSERT INTO activity(activity_id, timestamp, adjusted_distance, adjusted_duration, workout_feel, effort, category, activity_name, description, total_timer_time, local_timestamp, num_sessions, type, event, event_type, event_group)
                    VALUES ({sql_format(row.activity_id)}, {sql_format(row.timestamp, quote=True)}, {sql_format(row.adjusted_distance)}, {sql_format(row.adjusted_duration)}, {sql_format(row.workout_feel)}, {sql_format(row.effort)}, {sql_format(row.category, quote=True)}, {sql_format(row.activity_name, quote=True)}, {sql_format(row.description, quote=True)}, {sql_format(row.total_timer_time)}, {sql_format(row.local_timestamp, quote=True)}, {sql_format(row.num_sessions)}, {sql_format(row.type, quote=True)}, {sql_format(row.event, quote=True)}, {sql_format(row.event_type, quote=True)}, {sql_format(row.event_group, quote=True)})
                    ON CONFLICT (activity_id) DO NOTHING;"""

                    # Write to log file
                    log_file.write(sql + "\n")

            elif tabl == "session":
                    # *** REVIEW/EDIT THIS SCHEMA ***
                    desired_dtypes = {
                        "activity_id": "int64",
                        "timestamp": "datetime64[ns, UTC]",
                        "start_time": "datetime64[ns, UTC]",
                        "total_elapsed_time": "float64",
                        "total_timer_time": "float64",
                        "total_distance": "float64",
                        "event": "object",
                        "event_type": "object",
                        "sport": "object",
                        "sub_sport": "object"
                    }

                    existing_dtypes = { col: dtype for col, dtype in desired_dtypes.items() if col in df.columns }
                    if existing_dtypes:
                        df = df.astype(existing_dtypes)
                    
                    for col in desired_dtypes.keys():
                        if col not in df.columns:
                            df[col] = None

                    for index, row in df.iterrows():
                        # *** REVIEW/EDIT THIS INSERT STATEMENT ***
                        sql = f"""INSERT INTO session(activity_id, timestamp, start_time, total_elapsed_time, total_timer_time, total_distance, event, event_type, sport, sub_sport)
                        VALUES ({sql_format(row.activity_id)}, {sql_format(row.timestamp, quote=True)}, {sql_format(row.start_time, quote=True)}, {sql_format(row.total_elapsed_time)}, {sql_format(row.total_timer_time)}, {sql_format(row.total_distance)}, {sql_format(row.event, quote=True)}, {sql_format(row.event_type, quote=True)}, {sql_format(row.sport, quote=True)}, {sql_format(row.sub_sport, quote=True)})
                        ON CONFLICT (activity_id, timestamp) DO NOTHING;"""  # <-- Ensure conflict keys are correct
                        log_file.write(sql + "\n")

            # --- Lap Table ---
            elif tabl == "lap":
                # *** REVIEW/EDIT THIS SCHEMA ***
                desired_dtypes = {
                    "activity_id": "int64",
                    "timestamp": "datetime64[ns, UTC]",
                    "start_time": "datetime64[ns, UTC]",
                    "total_elapsed_time": "float64",
                    "total_timer_time": "float64",
                    "total_distance": "float64",
                    "avg_speed": "float64",
                    "max_speed": "float64",
                    "total_calories": "int64"
                }

                existing_dtypes = { col: dtype for col, dtype in desired_dtypes.items() if col in df.columns }
                if existing_dtypes:
                    df = df.astype(existing_dtypes)
                
                for col in desired_dtypes.keys():
                    if col not in df.columns:
                        df[col] = None

                for index, row in df.iterrows():
                    # *** REVIEW/EDIT THIS INSERT STATEMENT ***
                    sql = f"""INSERT INTO lap(activity_id, timestamp, start_time, total_elapsed_time, total_timer_time, total_distance, avg_speed, max_speed, total_calories)
                    VALUES ({sql_format(row.activity_id)}, {sql_format(row.timestamp, quote=True)}, {sql_format(row.start_time, quote=True)}, {sql_format(row.total_elapsed_time)}, {sql_format(row.total_timer_time)}, {sql_format(row.total_distance)}, {sql_format(row.avg_speed)}, {sql_format(row.max_speed)}, {sql_format(row.total_calories)})
                    ON CONFLICT (activity_id, timestamp) DO NOTHING;"""  # <-- Ensure conflict keys are correct
                    log_file.write(sql + "\n")

            # --- Record Table ---
            elif tabl == "record":
                # *** REVIEW/EDIT THIS SCHEMA ***
                desired_dtypes = {
                    "activity_id": "int64",
                    "timestamp": "datetime64[ns, UTC]",
                    "position_lat": "float64",
                    "position_long": "float64",
                    "distance": "float64",
                    "altitude": "float64",
                    "speed": "float64",
                    "heart_rate": "int64",
                    "cadence": "int64",
                    "power": "int64"
                }

                existing_dtypes = { col: dtype for col, dtype in desired_dtypes.items() if col in df.columns }
                if existing_dtypes:
                    df = df.astype(existing_dtypes)
                
                for col in desired_dtypes.keys():
                    if col not in df.columns:
                        df[col] = None

                for index, row in df.iterrows():
                    # *** REVIEW/EDIT THIS INSERT STATEMENT ***
                    sql = f"""INSERT INTO record(activity_id, timestamp, position_lat, position_long, distance, altitude, speed, heart_rate, cadence, power)
                    VALUES ({sql_format(row.activity_id)}, {sql_format(row.timestamp, quote=True)}, {sql_format(row.position_lat)}, {sql_format(row.position_long)}, {sql_format(row.distance)}, {sql_format(row.altitude)}, {sql_format(row.speed)}, {sql_format(row.heart_rate)}, {sql_format(row.cadence)}, {sql_format(row.power)})
                    ON CONFLICT (activity_id, timestamp) DO NOTHING;"""  # <-- Ensure conflict keys are correct
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
                    "number": "int64"
                }

                existing_dtypes = { col: dtype for col, dtype in desired_dtypes.items() if col in df.columns }
                if existing_dtypes:
                    df = df.astype(existing_dtypes)
                
                for col in desired_dtypes.keys():
                    if col not in df.columns:
                        df[col] = None

                for index, row in df.iterrows():
                    # *** REVIEW/EDIT THIS INSERT STATEMENT ***
                    sql = f"""INSERT INTO file_id(activity_id, type, manufacturer, product, serial_number, time_created, number)
                    VALUES ({sql_format(row.activity_id)}, {sql_format(row.type, quote=True)}, {sql_format(row.manufacturer, quote=True)}, {sql_format(row.product)}, {sql_format(row.serial_number)}, {sql_format(row.time_created, quote=True)}, {sql_format(row.number)})
                    ON CONFLICT (activity_id) DO NOTHING;"""  # <-- Ensure conflict key is correct
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
                    "swim_stroke": "object"
                }

                existing_dtypes = { col: dtype for col, dtype in desired_dtypes.items() if col in df.columns }
                if existing_dtypes:
                    # This was the typo in the previous version
                    df = df.astype(existing_dtypes) 
                
                for col in desired_dtypes.keys():
                    if col not in df.columns:
                        df[col] = None

                for index, row in df.iterrows():
                    # *** REVIEW/EDIT THIS INSERT STATEMENT ***
                    sql = f"""INSERT INTO length(activity_id, timestamp, start_time, total_elapsed_time, total_timer_time, total_strokes, avg_speed, swim_stroke)
                    VALUES ({sql_format(row.activity_id)}, {sql_format(row.timestamp, quote=True)}, {sql_format(row.start_time, quote=True)}, {sql_format(row.total_elapsed_time)}, {sql_format(row.total_timer_time)}, {sql_format(row.total_strokes)}, {sql_format(row.avg_speed)}, {sql_format(row.swim_stroke, quote=True)})
                    ON CONFLICT (activity_id, timestamp) DO NOTHING;"""  # <-- Ensure conflict keys are correct
                    log_file.write(sql + "\n")

            # --- Else: Unknown Table ---
            else:
                print(f"Warning: No specific SQL generation logic defined for table '{tabl}'. No statements written.")


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
                    VALUES ({row.activity_id}, '{row.timestamp}', {row.adjusted_distance}, {row.adjusted_duration}, {row.workout_feel}, {row.effort}, '{row.category}', '{row.activity_name}', '{row.description}', {row.total_timer_time}, '{row.local_timestamp}', {row.num_sessions}, '{row.type}', '{row.event}', '{row.event_type}', '{row.event_group}')
                    ON CONFLICT (activity_id) DO NOTHING;"""

                    # Write to log file
                    log_file.write(sql + "\n")

                    # Execute in database
                    # cursor.execute("""insert into activity(activity_id, timestamp, adjusted_distance, adjusted_duration, workout_feel, effort, category, activity_name, description, total_timer_time, local_timestamp, num_sessions, type, event, event_type, event_group)
                    # values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", [row.activity_id, row.timestamp, row.adjusted_distance, row.adjusted_duration, row.workout_feel, row.effort, row.category, row.activity_name, row.description, row.total_timer_time, row.local_timestamp, row.num_sessions, row.type, row.event, row.event_type, row.event_group])

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
                    VALUES ({row.activity_id}, {row.serial_number}, '{row.time_created}', '{row.manufacturer}', '{row.product_name}', {row.number}, '{row.type}');"""

                    # Write to log file
                    log_file.write(sql + "\n")

                    # Execute in database
                    # cursor.execute("""insert into file_id(activity_id, serial_number, time_created, manufacturer, product, number, type)
                    # values (%s, %s, %s, %s, %s, %s, %s)""", [row.activity_id, row.serial_number, row.time_created, row.manufacturer, row.product_name, row.number, row.type])

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
                        {row.activity_id}, {row.number}, '{row.start_time}', {row.total_distance},
                        {row.total_timer_time}, {row.total_ascent}, {row.total_descent},
                        {row.avg_vertical_oscillation}, {row.avg_stance_time}, {row.avg_vertical_ratio},
                        {row.avg_stance_time_balance}, {row.avg_step_length}, '{row.intensity}',
                        {row.avg_running_cadence}, {row.max_heart_rate}, {row.avg_heart_rate}
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
                    #         row.activity_id, row.number, row.start_time, row.total_distance,
                    #         row.total_timer_time, row.total_ascent, row.total_descent,
                    #         row.avg_vertical_oscillation, row.avg_stance_time, row.avg_vertical_ratio,
                    #         row.avg_stance_time_balance, row.avg_step_length, row.intensity,
                    #         row.avg_running_cadence, row.max_heart_rate, row.avg_heart_rate,
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
                    VALUES ({row.activity_id}, {row.latitude}, {row.longitude}, {row.lap}, {row.altitude}, '{row.timestamp}', {row.heart_rate}, {row.cadence}, {row.fractional_cadence}, {row.enhanced_speed}, {row.distance});"""

                    # Write to log file
                    log_file.write(sql + "\n")

                    # Execute in database
                    # cursor.execute("""insert into record(activity_id, latitude, longitude, lap, altitude, timestamp, heart_rate, cadence, fractional_cadence, enhanced_speed, distance)
                    # values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", [row.activity_id, row.latitude, row.longitude, row.lap, row.altitude, row.timestamp, row.heart_rate, row.cadence, row.fractional_cadence, row.enhanced_speed, row.distance])

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
                    VALUES ({row.activity_id}, '{row.timestamp}', '{row.start_time}', {row.start_position_lat}, {row.start_position_long}, 
                    {row.total_elapsed_time}, {row.total_timer_time}, {row.total_distance}, {row.total_strokes}, {row.nec_lat}, 
                    {row.nec_long}, {row.swc_lat}, {row.swc_long}, {row.message_index}, {row.total_calories}, {row.total_fat_calories}, {row.enhanced_avg_speed},
                    {row.avg_speed}, {row.enhanced_max_speed}, {row.max_speed}, {row.avg_power}, {row.max_power}, {row.total_ascent}, {row.total_descent}, {row.first_lap_index},
                    {row.num_laps}, '{row.event}', '{row.event_type}', '{row.sport}', '{row.sub_sport}', {row.avg_heart_rate}, {row.max_heart_rate}, {row.avg_cadence}, {row.max_cadence}, 
                    {row.total_training_effect}, {row.event_group}, '{row.trigger}', {row.pool_length}, '{row.pool_length_unit}');"""

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
                # [row.activity_id, row.timestamp, row.start_time, row.start_position_lat, row.start_position_long, \
                #  row.total_elapsed_time, row.total_timer_time, row.total_distance, row.total_strokes, row.nec_lat, \
                #  row.nec_long, row.swc_lat, row.swc_long, row.message_index, row.total_calories, row.total_fat_calories, \
                #  row.enhanced_avg_speed, row.avg_speed, row.enhanced_max_speed, row.max_speed, row.avg_power, \
                #  row.max_power, row.total_ascent, row.total_descent, row.first_lap_index, row.num_laps, row.event, \
                #  row.event_type, row.sport, row.sub_sport, row.avg_heart_rate, row.max_heart_rate, row.avg_cadence, \
                #  row.max_cadence, row.total_training_effect, row.event_group, row.trigger, row.pool_length, row.pool_length_unit])

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
                VALUES ({row.activity_id}, '{row.timestamp}', '{row.start_time}', {row.message_index}, {row.total_timer_time}, {row.total_strokes}, {row.avg_speed}, '{row.swim_stroke}', '{row.length_type}');"""

                # Write to log file
                log_file.write(sql + "\n")

                # Execute in database
                # cursor.execute("""insert into length(activity_id, timestamp, start_time, message_index, total_timer_time, total_strokes, avg_speed, swim_stroke, length_type) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)""", \
                # [row.activity_id, row.timestamp, row.start_time, row.message_index, row.total_timer_time, row.total_strokes, row.avg_speed, row.swim_stroke, row.length_type])


def get_fit_lap_data(
    frame: fitdecode.records.FitDataMessage,
) -> Dict[str, Union[float, datetime, timedelta, int]]:
    """Extract some data from a FIT frame representing a lap and return
    it as a dict.
    """

    data: Dict[str, Union[float, datetime, timedelta, int]] = {}

    for field in lap[1:]:  # Exclude 'number' (lap number) because we don't get that
        # from the data but rather count it ourselves
        if frame.has_field(field):
            data[field] = frame.get_value(field)

    return data


def get_fit_point_data(
    frame: fitdecode.records.FitDataMessage,
) -> Optional[Dict[str, Union[float, int, str, datetime]]]:
    """Extract some data from an FIT frame representing a track point
    and return it as a dict.
    """

    data: Dict[str, Union[float, int, str, datetime]] = {}

    if not (frame.has_field("position_lat") and frame.has_field("position_long")):
        # Frame does not have any latitude or longitude data. We will ignore these frames in order to keep things
        # simple, as we did when parsing the TCX file.
        return None
    else:
        data["latitude"] = frame.get_value("position_lat") / ((2**32) / 360)
        data["longitude"] = frame.get_value("position_long") / ((2**32) / 360)

    for field in record[3:]:
        if frame.has_field(field):
            data[field] = frame.get_value(field)

    return data


def get_fit_other_data(
    col, frame: fitdecode.records.FitDataMessage
) -> Optional[Dict[str, Union[float, int, str, datetime]]]:
    """Extract the data point from other FIT frames(file_id, session, activity)
    with the use of column names and return a relevant Pandas DataFrame
    """

    data: Dict[str, Union[float, int, str, datetime]] = {}

    for field in col:
        if frame.has_field(field):
            data[field] = frame.get_value(field)
    return data


def get_dataframes(fname: str, activity_id: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Takes the path to a FIT file (as a string) and returns two Pandas
    DataFrames: one containing data about the laps, and one containing
    data about the individual points.
    """

    record_data = []
    lap_data = []
    lap_no = 1
    file_id_data = []
    activity_data = []
    session_data = []
    length_data = []
    intensity = []
    wsi = []
    has_intensity = False

    with fitdecode.FitReader(fname) as fit_file:
        for frame in fit_file:
            if isinstance(frame, fitdecode.records.FitDataMessage):
                # intensity in words
                if frame.has_field("intensity"):
                    intensity.append(frame.get_value("intensity"))
                    has_intensity = True
                # intensity as an index. this matches intensity in words but not always, for some reason
                # i will explain the relationship after the with statement
                if frame.has_field("wkt_step_index"):
                    wsi.append(frame.get_value("wkt_step_index"))
                if frame.name == "record":
                    single_point_data = get_fit_point_data(frame)
                    if single_point_data is not None:
                        single_point_data["lap"] = lap_no
                        record_data.append(single_point_data)
                elif frame.name == "lap":
                    single_lap_data = get_fit_lap_data(frame)
                    single_lap_data["number"] = lap_no
                    lap_data.append(single_lap_data)
                    lap_no += 1
                elif frame.name == "file_id":
                    file_id_data.append(get_fit_other_data(file_id, frame))
                elif frame.name == "activity":
                    activity_data.append(get_fit_other_data(activity, frame))
                elif frame.name == "session":
                    session_data.append(get_fit_other_data(session, frame))
                elif frame.name == "length":
                    length_data.append(get_fit_other_data(length, frame))
                    # right now, leaning towards making a new table just for lengths, so just pool swimming as far as I know. Also check and see if heart rate is currently present for swimming activities.

    # Create DataFrames from the data we have collected. If any information is missing from a particular lap or track
    # point, it will show up as a null value or "NaN" in the DataFrame.

    lap_df = pd.DataFrame(lap_data, columns=lap)
    #     lap_df.set_index('number', inplace=True)
    if has_intensity:
        # filter out the intensities if == None
        filtered_list = [value for value in intensity if value is not None]
        # unique indices to match the word values to
        unique_wsi = unique(wsi)

        # this if statements deals with Nans in unique workout step index list
        if len(filtered_list) < len(
            unique_wsi
        ):  # nans may be in unique_wsi, so it should always be at least as long as filtered list
            result_list = list(filtered_list)

            # Update result_list based on NaN check
            # the goal is to replace Nan with None in wsi and have the Nones at the same indices in the result list.
            # ultimately the index in wsi will be matched the word form of intensity and will be added to lap_df if present
            # Nones are prefered to Nans in my case because of their different properties.
            for idx, num in enumerate(unique_wsi):
                if isNan(num):
                    unique_wsi[idx] = None
                    # Check if the index is within the length of result list
                    if idx < len(result_list):
                        result_list.insert(idx, None)
                    else:
                        # If the index is beyond the length, extend the list with None
                        result_list.extend([None] * (idx - len(result_list) + 1))
            filtered_list = result_list
        paired_list = list(zip(unique_wsi, filtered_list))
        # replaces the numbers in wsi with the corresponding word intensity from paired_list
        result_intensity = [
            word for number in wsi for num, word in paired_list if number == num
        ]

        other_data_dict = {"intensity": result_intensity}

        # append to lap_df if intensity has been successfully retrieved
        if len(other_data_dict["intensity"]) == lap_df.shape[0]:
            other_data_df = pd.DataFrame(other_data_dict)
            lap_df = pd.concat([lap_df, other_data_df], axis=1)
        else:
            lap_dict = {"intensity": [None] * lap_df.shape[0]}
            other_data_df = pd.DataFrame(lap_dict)
            lap_df = pd.concat([lap_df, other_data_df], axis=1)

    record_df = pd.DataFrame(record_data, columns=record)
    file_id_df = pd.DataFrame(file_id_data, columns=file_id)
    activity_df = pd.DataFrame(activity_data, columns=activity)
    session_df = pd.DataFrame(session_data, columns=session)
    length_df = pd.DataFrame(length_data, columns=length)

    # Message index starts at 0 and is incremented by 1 for every message, including rests. I want it to be lap count, so I am subtracting not active lengths.
    length_df["message_index"] = length_df["message_index"] + 1

    # subtract one from each message_index on and after each occurence of a value not equal to 'active' in the length_df dataframe
    for idx, row in length_df.iterrows():
        if row["type"] != "active":
            length_df.loc[idx:, "message_index"] = (
                length_df.loc[idx:, "message_index"] - 1
            )

    for df in (lap_df, record_df, file_id_df, activity_df, session_df, length_df):
        df["activity_id"] = activity_id
    if activity_df.empty:
        activity_df = activity_df.append(
            {"activity_id": activity_id}, ignore_index=True
        )

    return lap_df, record_df, file_id_df, activity_df, session_df, length_df


# Function to extract the date from the filename
def extract_date_from_filename_connect(filename):
    # Assuming the format is YYYY-mm-ddThh.mm.ss
    date_str = filename.split("T")[0]  # Extract the date part (YYYY-mm-dd)
    # time_str = filename.split('T')[1].split('.')[0:3]  # Extract the time part (hh.mm.ss)
    # time_str = '.'.join(time_str)  # Combine the time parts back into a string
    # timestamp_str = date_str + 'T' + time_str  # Combine date and time parts
    return datetime.strptime(date_str, "%Y-%m-%d")

def extract_date_from_filename_watch(filename):

    date_str = filename.split(".")[0]
    # return the year, month, and day of filename (which has the format below)
    return datetime.strptime(date_str, "%Y-%m-%d-%H-%M-%S").date()

if __name__ == "__main__":

    from_garmin_connect = False # has to manually be set

    # latest date in the database or manually set it
    # define our stopping point (because sometimes downloads for garmin will be a date in the future)
    today = datetime.now().date()

    # Convert the after_date and today to date objects (without time)
    # after_date = datetime.combine(after_date, datetime.min.time())
    after_date = datetime(2025, 8, 2, 0, 0, 0).date()
    # today = datetime(
    #     2025, 10, 6, 0, 0, 0
    # )  # datetime.combine(today, datetime.min.time())

    files = [
        f for f in listdir(dir) if isfile(join(dir, f)) and f.endswith(file_extension)
    ]

    if from_garmin_connect:
        # Filter files based on the specific date
        filtered_files = [
            f for f in files if after_date < extract_date_from_filename_connect(f) <= today
        ]
        json_files = [f.replace(file_extension, "_summary.json") for f in filtered_files]
        errors = []
        err_count = 0
        swm_count = 0
        index = [0]
        for file in filtered_files:
            try:
                # fname = dir+"\\"+file# WINDOWS
                fname = dir + file  # LINUX
                jname = fname.replace(file_extension, "_summary.json")
                activity_id = get_user_activity_details(fname)
                lap_df, record_df, file_id_df, activity_df, session_df, length_df = (
                    get_dataframes(fname)
                )
                print(activity_df)
                # subset lap swimming activities here
                jframe = pd.DataFrame(get_json_info(jname), index=index)
                activity_df_fixed = pd.concat([activity_df, jframe], axis=1)
                # print('user_activity:', activity_id)
                # load to DB
            #     load_dataframe_to_postgres(activity_df_fixed, "activity")
            #     load_dataframe_to_postgres(file_id_df, "file_id")
            #     load_dataframe_to_postgres(lap_df, "lap")
            #     load_dataframe_to_postgres(record_df, "record")
            #     load_dataframe_to_postgres(session_df, "session")
            #     load_dataframe_to_postgres(length_df, "length")
            except:
            #     write_sql_statement_to_file(activity_df_fixed, "activity")
            #     write_sql_statement_to_file(file_id_df, "file_id")
            #     write_sql_statement_to_file(lap_df, "lap")
            #     write_sql_statement_to_file(record_df, "record")
            #     write_sql_statement_to_file(session_df, "session")
            #     write_sql_statement_to_file(length_df, "length")
                errors.append(activity_id)
                err_count += 1
        print("finished")
        print("errors")
        print(err_count)
    else:
        # files straight from the watch that just have the sensor data (no titles, description, etc yet)
        # Filter files based on the specific date (Augest 2nd rn)
        filtered_files = [
            f for f in files if after_date < extract_date_from_filename_watch(f) <= today
        ]
        for file in filtered_files:
            fname = dir + file

            lap_df, record_df, file_id_df, activity_df, session_df, length_df = (
                   get_dataframes(fname, 1)
               )
            # lap_df.to_csv('lap_data.csv', index=False)
            # record_df.to_csv('record_data.csv', index=False)
            # file_id_df.to_csv('file_id_data.csv', index=False)
            # activity_df.to_csv('activity_data.csv', index=False)
            # session_df.to_csv('session_data.csv', index=False)
            # load avtivity and get activity id back 
            # then load otheres
            write_sql_statement_to_file_watch(activity_df, "activity")
            # write_sql_statement_to_file_watch(file_id_df, "file_id")
            write_sql_statement_to_file_watch(lap_df, "lap")
            write_sql_statement_to_file_watch(record_df, "record")
            write_sql_statement_to_file_watch(session_df, "session")
            write_sql_statement_to_file_watch(length_df, "length")
            # TODO:
 #            adjusted_distance and adjusted_duration need to defualt to the total_distance from total_distance of session df
 #            defualt activity name to location and activity type. from session start_position_lat and start_position_long. type from type column of session df


