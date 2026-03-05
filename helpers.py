# helpers.py
# Shared utilities, constants, FIT parsing helpers, and DataFrame construction

from datetime import datetime, timezone
from dateutil import parser
import pandas as pd
import fitdecode
import json
import os
import numpy as np
import psycopg
from dotenv import load_dotenv

# -------------------------
# COLUMN DEFINITIONS
# -------------------------

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

file_id = ["serial_number", "time_created", "manufacturer", "product", "number", "type"]

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

session = [
    "start_position_lat",
    "start_position_long",
    "nec_long",
    "swc_lat",
    "swc_long",
    "nec_lat",
    "timestamp",
    "start_time",
    "total_elapsed_time",
    "total_timer_time",
    "total_distance",
    "total_strokes",
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


DIVISOR = (2**32) / 360
# -------------------------
# UTILITY FUNCTIONS
# -------------------------


def isNan(num):
    """
    Checks if a value is NaN (Not a Number).

    Args:
        num: The value to check.

    Returns:
        bool: True if the value is NaN, False otherwise.
    """
    return num != num


def unique(list1):
    """
    Returns a list of unique elements from the input list, preserving order.

    Args:
        list1 (list): The input list.

    Returns:
        list: A list containing unique elements.
    """
    unique_list = pd.Series(list1).drop_duplicates().tolist()
    return unique_list


def get_json_info(file):
    """
    Reads _summary.json Garmin Connect files with desired key mappings.

    Extracts specific fields (distance, duration, workout feel, etc.) from
    the JSON structure and maps them to a flat dictionary.

    Args:
        file (str): Path to the JSON file.

    Returns:
        dict: A dictionary containing the extracted and mapped information,
              or None if an error occurs.
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

    try:
        with open(file, "r", encoding="utf-8") as json_file:
            data = json.load(json_file)

        extracted_info = {
            key_mapping[key]: get_nested_value(data, key.split("."))
            for key in desired_keys
        }
        return extracted_info

    except Exception as e:
        print(f"Error processing file {file}: {e}")
        return None


def get_nested_value(data, keys_chain):
    """
    Retrieves a value from a nested dictionary or list using a chain of keys.

    Args:
        data (dict | list): The nested data structure.
        keys_chain (list): A list of keys/indices to traverse.

    Returns:
        Any: The found value, or None if a key/index is missing or invalid.
    """
    value = data
    for sub_key in keys_chain:
        if isinstance(value, dict) and sub_key in value:
            value = value[sub_key]
        elif isinstance(value, list) and sub_key.isdigit():
            idx = int(sub_key)
            value = value[idx] if idx < len(value) else None
        else:
            return None
    return value


def get_user_activity_details(file):
    """
    Returns the activity id for an activity based on the filename.

    Args:
        file (str): The file path.

    Returns:
        str: The extracted activity ID.
    """
    name = os.path.basename(file)
    activity_id = name.split("_")[1]
    if "." in activity_id:
        activity_id = activity_id.split(".")[0]
    return activity_id


def extract_date_from_filename_connect(filename):
    """
    Extracts the date from a Garmin Connect filename.
    Format expected: Date with datetime

    Args:
        filename (str): The filename string.

    Returns:
        datetime.datetime: The extracted datetime object.
    """
    date_str = filename.split("_")[0]
    return parser.isoparse(date_str.replace(".", ":"))
    # return datetime.strptime(date_str, "%Y-%m-%d").date()


def extract_date_from_filename_watch(filename):
    """
    Extracts the date from a generic watch filename.
    Format expected: YYYY-MM-DD-HH-MM-SS.fit

    Args:
        filename (str): The filename string.

    Returns:
        datetime.datetime: The extracted datetime object.
    """
    date_str = filename.split(".")[0]
    return datetime.strptime(date_str, "%Y-%m-%d-%H-%M-%S").replace(tzinfo=timezone.utc)


# -------------------------
# FIT DATA EXTRACTION HELPERS
# -------------------------


def get_fit_lap_data(frame):
    """
    Extracts defined fields from a 'lap' FIT message frame.

    Args:
        frame (fitdecode.FitDataMessage): The FIT message frame.

    Returns:
        dict: Dictionary of extracted lap data.
    """
    data = {}
    for field in lap[1:]:
        if frame.has_field(field):
            data[field] = frame.get_value(field)
    return data


def get_fit_point_data(frame):
    """
    Extracts defined fields from a 'record' FIT message frame.
    Specifically handles latitude/longitude extraction.

    Args:
        frame (fitdecode.FitDataMessage): The FIT message frame.

    Returns:
        dict: Dictionary of extracted record data, or None if coordinates are missing.
    """
    if not (frame.has_field("position_lat") and frame.has_field("position_long")):
        return None

    data = {}
    # renaming cols
    data["latitude"] = frame.get_value("position_lat")
    data["longitude"] = frame.get_value("position_long")

    # NOTE: This requires lat and long to be the first items in the list. I also skip the lap column to manually define it.
    for field in record[3:]:
        if frame.has_field(field):
            data[field] = frame.get_value(field)

    return data


def get_fit_session_data(frame):
    """
    Extracts defined fields from a 'session' FIT message frame.
    Converts positional data (lat/long) using the global DIVISOR.

    Args:
        frame (fitdecode.FitDataMessage): The FIT message frame.

    Returns:
        dict: Dictionary of extracted session data.
    """
    data = {}

    # NOTE: converting from semicircles/degrees to true lat and longs. just because it's easier to play around with the data without converting everytime.
    # This is meant to store data for one person, so precision and computational savings don't matter much to me as ease of use
    # It would be more efficient to do perform vector multiplication on the Series insead of each individual point like below
    for field in session[:5]:
        if frame.has_field(field):
            data[field] = frame.get_value(field) / DIVISOR

    for field in session[6:]:
        if frame.has_field(field):
            data[field] = frame.get_value(field)
    return data


def get_fit_other_data(col, frame):
    """
    Generic extraction for other FIT message types (file_id, activity, etc.).

    Args:
        col (list): List of field names to extract.
        frame (fitdecode.FitDataMessage): The FIT message frame.

    Returns:
        dict: Dictionary of extracted data.
    """
    data = {}
    for field in col:
        if frame.has_field(field):
            data[field] = frame.get_value(field)
    return data


def create_safe_df(data, columns, df_name, activity_id):
    """
    Creates a Pandas DataFrame safely, catching and logging any errors.

    Args:
        data (list): List of dictionaries containing data.
        columns (list): List of column names.
        df_name (str): Name of the DataFrame (for logging).
        activity_id (str): ID of the activity (for logging).

    Returns:
        pd.DataFrame: The created DataFrame, or an empty DataFrame on failure.
    """
    try:
        return pd.DataFrame(data, columns=columns)
    except Exception as e:
        # Log the specific failure immediately
        print(f"[WARNING] {df_name} failed for {activity_id}: {e}")
        log_path = os.path.join(os.path.dirname(__file__), "errors.txt")
        with open(log_path, "a") as f:
            f.write(f"\n{activity_id} - {df_name} failed: {e}")

        # Return an empty DataFrame so the variable exists
        return pd.DataFrame()


# -------------------------
# MAIN DATAFRAME CONSTRUCTOR
# -------------------------


def get_dataframes(fname: str, activity_id=None):
    """
    Reads a FIT file and produces DataFrames for:
    lap, record, file_id, activity, session, length.

    This function iterates through the FIT file messages, aggregates data into lists,
    constructs DataFrames, and performs necessary data cleaning and type conversion
    (e.g., coordinate conversion, timestamp filling, intensity matching).

    Args:
        fname (str): Path to the FIT file.
        activity_id (str, optional): The ID to assign to the rows in the DataFrames.

    Returns:
        tuple: A tuple containing (lap_df, record_df, file_id_df, activity_df, session_df, length_df).
    """

    # Initialize data containers
    record_data = []
    lap_data = []
    lap_no = 1
    file_id_data = []
    activity_data = []
    session_data = []
    length_data = []
    intensity = []
    wsi = []
    # just initially the intensity value for a lap. it may be present
    has_intensity = False

    # Iterate through the FIT file
    with fitdecode.FitReader(fname) as fit_file:
        for frame in fit_file:
            if not isinstance(frame, fitdecode.records.FitDataMessage):
                continue

            # Capture intensity and workout step index if present
            if frame.has_field("intensity"):
                intensity.append(frame.get_value("intensity"))
                has_intensity = True

            if frame.has_field("wkt_step_index"):
                wsi.append(frame.get_value("wkt_step_index"))

            # Sort data into respective lists based on frame name
            if frame.name == "record":
                record_point = get_fit_point_data(frame)
                # in rare cases, a record might return No data which will cause issues when making the record pandas dataframe, so we check before keeping the data
                if record_point is not None:
                    record_data.append(record_point)

            elif frame.name == "lap":
                lap_obj = get_fit_lap_data(frame)
                lap_obj["number"] = lap_no
                lap_data.append(lap_obj)
                lap_no += 1

            elif frame.name == "file_id":
                file_id_data.append(get_fit_other_data(file_id, frame))

            elif frame.name == "activity":
                activity_data.append(get_fit_other_data(activity, frame))

            elif frame.name == "session":
                # session_data.append(get_fit_session_data(frame))
                session_data.append(get_fit_other_data(session, frame))
            elif frame.name == "length":
                length_data.append(get_fit_other_data(length, frame))

    # Build DataFrames
    lap_df = create_safe_df(lap_data, lap, "lap_df", activity_id)

    # Handle intensity matching logic
    # This block aligns intensity values with workout step indices (wsi)
    if has_intensity:
        filtered_list = [i for i in intensity if i is not None]
        unique_wsi_vals = unique(wsi)

        # If we have fewer intensity values than unique workout steps, pad with None
        # Sometimes, a file will be missing the wu and cd intensities, so that's the use of padding
        if len(filtered_list) < len(unique_wsi_vals):
            result = list(filtered_list)
            for idx, num in enumerate(unique_wsi_vals):
                if isNan(num):
                    unique_wsi_vals[idx] = None
                    if idx < len(result):
                        result.insert(idx, None)
                    else:
                        result.extend([None] * (idx - len(result) + 1))
            filtered_list = result

        # Map intensity values back to the full list based on WSI
        paired = list(zip(unique_wsi_vals, filtered_list))
        result_intensity = [
            word for number in wsi for num, word in paired if number == num
        ]

        # Assign to lap_df if lengths match, otherwise fill with None
        if len(result_intensity) == len(lap_df):
            lap_df["intensity"] = result_intensity
        else:
            lap_df["intensity"] = [None] * len(lap_df)

    # stop if activity df is failed
    try:
        activity_df = pd.DataFrame(activity_data, columns=activity)
    except Exception as e:
        raise ValueError(f"CRITICAL: activity_df failed: {e}")
    record_df = create_safe_df(
        record_data, record, "record_df", activity_id=activity_id
    )
    file_id_df = create_safe_df(
        file_id_data, file_id, "file_id_df", activity_id=activity_id
    )
    session_df = create_safe_df(
        session_data, session, "session_df", activity_id=activity_id
    )
    length_df = create_safe_df(
        length_data, length, "length_df", activity_id=activity_id
    )

    # Post-processing: Date formatting and fallbacks
    if not file_id_df.empty and "time_created" in file_id_df.columns:
        # 'errors="coerce"' turns invalid formats into NaT (Not a Time)
        file_id_df["time_created"] = pd.to_datetime(
            file_id_df["time_created"], errors="coerce", utc=True
        )

        if pd.isna(file_id_df.iloc[0]["time_created"]):
            if not activity_df.empty and "timestamp" in activity_df.columns:
                fallback_time = pd.to_datetime(
                    activity_df.iloc[0]["timestamp"], utc=True
                )
                file_id_df.loc[0, "time_created"] = fallback_time

    # NOTE: converting lat and long from ints into floats.
    lat_long_cols_session = session[:6]
    session_df[lat_long_cols_session] = (
        session_df[lat_long_cols_session].astype(float) / DIVISOR
    )

    lat_long_cols_record = ["latitude", "longitude"]
    record_df[lat_long_cols_record] = (
        record_df[lat_long_cols_record].astype(float) / DIVISOR
    )

    # NOTE: calculating lap numbers for record df based if the distance has surpassed the cumulative distance for each lap from the lap df
    if not record_df.empty:
        lap_bounds = lap_df["total_distance"].cumsum().values
        lap_indices = np.searchsorted(lap_bounds, record_df["distance"].values)
        record_df["lap"] = lap_indices + 1

    # Counting swimming laps to start at 1 and increment at active laps (not recovery laps)
    length_df["message_index"] = length_df["message_index"] + 1

    for idx, row in length_df.iterrows():
        if row["length_type"] != "active":
            length_df.loc[idx:, "message_index"] -= 1

    # This should only be true for files from garmin connect.
    if activity_id:
        for df in (lap_df, record_df, file_id_df, activity_df, session_df, length_df):
            df["activity_id"] = activity_id

    # it seems some manual activities from garmin connect will be missing some timestamps,
    # so we will try filling any missing timestamps from the activity table with timestamps
    # from the session table
    if pd.isna(activity_df["timestamp"]).any():
        earliest_time = session_df["start_time"].min()
        activity_df["timestamp"] = activity_df["timestamp"].fillna(earliest_time)

    return lap_df, record_df, file_id_df, activity_df, session_df, length_df


def get_cursor():
    """
    Connects to DB_UI_LOCAL environment variable. Needs to be set up in the project folder. Must have SCHEMA set up in the .env file as well.

    Returns:
        postgres.Cursor: postgres cursor
    """

    load_dotenv()
    database_url = os.getenv("DB_UI_LOCAL")
    schema = os.getenv("SCHEMA")

    conn = psycopg.connect(database_url, options=f"-c search_path={schema}")
    cur = conn.cursor()
    return cur


def get_after_date(_cur):
    """
    Retrieve the latest activity timestamp from in the database

    Args:
        _cur (psycopg.Cursor): Interface to postgres.

    Returns:
        datetime.datetime: UTC
    """

    _cur.execute(
        "SELECT MAX(timestamp) FROM activity where timestamp < NOW() AT TIME ZONE 'UTC';"
    )
    after_date = _cur.fetchone()[0]
    return after_date
