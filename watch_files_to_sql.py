import pandas as pd
import os
from os import listdir
from os.path import isfile, join
from datetime import datetime


def write_sql_statement_to_file(df, tabl, log_file_path=None):
    """
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

    def get_sql_value(row, col, quote=False):
        if col in row:
            return sql_format(row[col], quote=quote)
        return "NULL"

    with open(log_file_path, "a") as log_file:
        log_file.write("\n\n")

        if df.empty:
            return

        else:
            if tabl == "activity":

                # Remove timezone from local_timestamp if present
                if "local_timestamp" in df.columns and df[
                    "local_timestamp"
                ].dtype.name.startswith("datetime64[ns,"):
                    df["local_timestamp"] = df["local_timestamp"].dt.tz_localize(None)

                # Ensure all expected columns exist (missing → None)
                expected_cols = [
                    "activity_id",
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

                for col in expected_cols:
                    if col not in df.columns:
                        df[col] = None

                # ---- BUILD BULK INSERT ----
                values_list = []

                for index, row in df.iterrows():

                    row_str = (
                        "("
                        f"{get_sql_value(row, 'activity_id')}, "
                        f"{get_sql_value(row, 'timestamp', quote=True)}, "
                        f"{get_sql_value(row, 'adjusted_distance')}, "
                        f"{get_sql_value(row, 'adjusted_duration')}, "
                        f"{get_sql_value(row, 'workout_feel')}, "
                        f"{get_sql_value(row, 'effort')}, "
                        f"{get_sql_value(row, 'category', quote=True)}, "
                        f"{get_sql_value(row, 'activity_name', quote=True)}, "
                        f"{get_sql_value(row, 'description', quote=True)}, "
                        f"{get_sql_value(row, 'total_timer_time')}, "
                        f"{get_sql_value(row, 'local_timestamp', quote=True)}, "
                        f"{get_sql_value(row, 'num_sessions')}, "
                        f"{get_sql_value(row, 'type', quote=True)}, "
                        f"{get_sql_value(row, 'event', quote=True)}, "
                        f"{get_sql_value(row, 'event_type', quote=True)}, "
                        f"{get_sql_value(row, 'event_group', quote=True)}"
                        ")"
                    )

                    values_list.append(row_str)

                if values_list:
                    bulk_values = ",\n".join(values_list)

                    sql = f"""
                    INSERT INTO activity (
                        activity_id, timestamp, adjusted_distance, adjusted_duration,
                        workout_feel, effort, category, activity_name, description,
                        total_timer_time, local_timestamp, num_sessions, type,
                        event, event_type, event_group
                    )
                    VALUES
                    {bulk_values}
                    ON CONFLICT (activity_id) DO NOTHING;
                    """

                    log_file.write(sql + "\n")

            elif tabl == "session":
                # *** REVIEW/EDIT THIS SCHEMA ***
                # desired_dtypes = {
                #     "activity_id": "int64",
                #     "timestamp": "datetime64[ns, UTC]",
                #     "start_time": "datetime64[ns, UTC]",
                #     "start_position_lat": "float",
                #     "start_position_long": "float",
                #     "total_elapsed_time": "float64",
                #     "total_timer_time": "float64",
                #     "total_distance": "float64",
                #     "total_strokes": "float64",
                #     "nec_lat": "float",
                #     "nec_long": "float",
                #     "swc_lat": "float",
                #     "swc_long": "float",
                #     "message_index": "int64",
                #     "total_calories": "float",
                #     "total_fat_calories": "float64",
                #     "enhanced_avg_speed": "float64",
                #     "avg_speed": "float64",
                #     "enhanced_max_speed": "float64",
                #     "max_speed": "float64",
                #     "avg_power": "float64",
                #     "max_power": "float64",
                #     "total_ascent": "float",
                #     "total_descent": "float",
                #     "first_lap_index": "float",
                #     "num_laps": "float",
                #     "event": "object",
                #     "event_type": "object",
                #     "sport": "object",
                #     "sub_sport": "object",
                #     "avg_heart_rate": "float",
                #     "max_heart_rate": "float",
                #     "avg_cadence": "float",
                #     "max_cadence": "float",
                #     "total_training_effect": "float64",
                #     "event_group": "float64",
                #     "trigger": "object",
                #     "pool_length": "float",
                #     "pool_length_unit": "object",
                # }
                #
                # existing_dtypes = {
                #     col: dtype
                #     for col, dtype in desired_dtypes.items()
                #     if col in df.columns
                # }
                # if existing_dtypes:
                #     df = df.astype(existing_dtypes)
                #
                # for col in desired_dtypes.keys():
                #     if col not in df.columns:
                #         df[col] = None

                values_list = []

                for index, row in df.iterrows():
                    # Create the value group for this specific row
                    row_str = (
                        f"("
                        f"{get_sql_value(row, 'activity_id')}, "
                        f"{get_sql_value(row, 'timestamp', quote=True)}, "
                        f"{get_sql_value(row, 'start_time', quote=True)}, "
                        f"{get_sql_value(row, 'start_position_lat')}, "
                        f"{get_sql_value(row, 'start_position_long')}, "
                        f"{get_sql_value(row, 'total_elapsed_time')}, "
                        f"{get_sql_value(row, 'total_timer_time')}, "
                        f"{get_sql_value(row, 'total_distance')}, "
                        f"{get_sql_value(row, 'total_strokes')}, "
                        f"{get_sql_value(row, 'nec_lat')}, "
                        f"{get_sql_value(row, 'nec_long')}, "
                        f"{get_sql_value(row, 'swc_lat')}, "
                        f"{get_sql_value(row, 'swc_long')}, "
                        f"{get_sql_value(row, 'message_index')}, "
                        f"{get_sql_value(row, 'total_calories')}, "
                        f"{get_sql_value(row, 'total_fat_calories')}, "
                        f"{get_sql_value(row, 'enhanced_avg_speed')}, "
                        f"{get_sql_value(row, 'avg_speed')}, "
                        f"{get_sql_value(row, 'enhanced_max_speed')}, "
                        f"{get_sql_value(row, 'max_speed')}, "
                        f"{get_sql_value(row, 'avg_power')}, "
                        f"{get_sql_value(row, 'max_power')}, "
                        f"{get_sql_value(row, 'total_ascent')}, "
                        f"{get_sql_value(row, 'total_descent')}, "
                        f"{get_sql_value(row, 'first_lap_index')}, "
                        f"{get_sql_value(row, 'num_laps')}, "
                        f"{get_sql_value(row, 'event', quote=True)}, "
                        f"{get_sql_value(row, 'event_type', quote=True)}, "
                        f"{get_sql_value(row, 'sport', quote=True)}, "
                        f"{get_sql_value(row, 'sub_sport', quote=True)}, "
                        f"{get_sql_value(row, 'avg_heart_rate')}, "
                        f"{get_sql_value(row, 'max_heart_rate')}, "
                        f"{get_sql_value(row, 'avg_cadence')}, "
                        f"{get_sql_value(row, 'max_cadence')}, "
                        f"{get_sql_value(row, 'total_training_effect')}, "
                        f"{get_sql_value(row, 'event_group')}, "
                        f"{get_sql_value(row, 'trigger', quote=True)}, "
                        f"{get_sql_value(row, 'pool_length')}, "
                        f"{get_sql_value(row, 'pool_length_unit', quote=True)}"
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
                # desired_dtypes = {
                #     "activity_id": "int64",
                #     "number": "int64",
                #     "start_time": "datetime64[ns, UTC]",
                #     "total_distance": "float64",
                #     "total_timer_time": "float64",
                #     "total_ascent": "int64",
                #     "total_descent": "int64",
                #     "avg_vertical_oscillation": "float64",
                #     "avg_stance_time": "float64",
                #     "avg_vertical_ratio": "float64",
                #     "avg_stance_time_balance": "float64",
                #     "avg_step_length": "float64",
                #     "intensity": "object",
                #     "avg_running_cadence": "int64",
                #     "max_heart_rate": "int64",
                #     "avg_heart_rate": "int64",
                # }

                # existing_dtypes = {
                #     col: dtype
                #     for col, dtype in desired_dtypes.items()
                #     if col in df.columns
                # }
                # if existing_dtypes:
                #     try:
                #         df = df.astype(existing_dtypes)
                #     except:
                #         df.to_csv("error lap df.csv", index=False)
                # for col in desired_dtypes.keys():
                #     if col not in df.columns:
                #         df[col] = None

                values_list = []

                for index, row in df.iterrows():
                    # Create the value group for this specific row
                    row_str = (
                        f"("
                        f"{get_sql_value(row, 'activity_id')}, "
                        f"{get_sql_value(row, 'number')}, "
                        f"{get_sql_value(row, 'start_time', quote=True)}, "
                        f"{get_sql_value(row, 'total_distance')}, "
                        f"{get_sql_value(row, 'total_timer_time')}, "
                        f"{get_sql_value(row, 'total_ascent')}, "
                        f"{get_sql_value(row, 'total_descent')}, "
                        f"{get_sql_value(row, 'avg_vertical_oscillation')}, "
                        f"{get_sql_value(row, 'avg_stance_time')}, "
                        f"{get_sql_value(row, 'avg_vertical_ratio')}, "
                        f"{get_sql_value(row, 'avg_stance_time_balance')}, "
                        f"{get_sql_value(row, 'avg_step_length')}, "
                        f"{get_sql_value(row, 'intensity', quote=True)}, "
                        f"{get_sql_value(row, 'avg_running_cadence')}, "
                        f"{get_sql_value(row, 'max_heart_rate')}, "
                        f"{get_sql_value(row, 'avg_heart_rate')}"
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
                # desired_dtypes = {
                #     "activity_id": "int64",
                #     "latitude": "float64",
                #     "longitude": "float64",
                #     "lap": "int64",
                #     "altitude": "float64",
                #     "timestamp": "datetime64[ns, UTC]",
                #     "heart_rate": "int64",
                #     "cadence": "int64",
                #     "fractional_cadence": "float64",
                #     "enhanced_speed": "int64",
                #     "distance": "float64",
                # }
                #
                # existing_dtypes = {
                #     col: dtype
                #     for col, dtype in desired_dtypes.items()
                #     if col in df.columns
                # }
                # if existing_dtypes:
                #     df = df.astype(existing_dtypes)
                #
                # for col in desired_dtypes.keys():
                #     if col not in df.columns:
                #         df[col] = None

                values_list = []

                for index, row in df.iterrows():
                    # Create a tuple of formatted strings using your existing helper function
                    row_values = (
                        f"{get_sql_value(row, 'activity_id')}",
                        f"{get_sql_value(row, 'latitude')}",
                        f"{get_sql_value(row, 'longitude')}",
                        f"{get_sql_value(row, 'lap')}",
                        f"{get_sql_value(row, 'altitude')}",
                        f"{get_sql_value(row, 'timestamp', quote=True)}",
                        f"{get_sql_value(row, 'heart_rate')}",
                        f"{get_sql_value(row, 'cadence')}",
                        f"{get_sql_value(row, 'fractional_cadence')}",
                        f"{get_sql_value(row, 'enhanced_speed')}",
                        f"{get_sql_value(row, 'distance')}",
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
                # desired_dtypes = {
                #     "activity_id": "int64",
                #     "type": "object",
                #     "manufacturer": "object",
                #     "product": "int64",
                #     "serial_number": "int64",
                #     "time_created": "datetime64[ns, UTC]",
                #     "number": "float",  # Changed from int64 to float to handle NaN
                # }
                #
                # existing_dtypes = {
                #     col: dtype
                #     for col, dtype in desired_dtypes.items()
                #     if col in df.columns
                # }
                #
                # if existing_dtypes:
                #     # Handle potential conversion errors if 'product' is not purely numeric
                #     for col, dtype in existing_dtypes.items():
                #         try:
                #             if dtype == "int64":
                #                 # Convert to float first to handle NaNs, then to nullable Int64
                #                 df[col] = (
                #                     pd.to_numeric(df[col], errors="coerce")
                #                     .astype("float")
                #                     .astype("Int64")
                #                 )
                #             else:
                #                 df = df.astype({col: dtype})
                #         except Exception as e:
                #             print(
                #                 f"Error casting column {col} to {dtype}: {e}. Forcing to object."
                #             )
                #             df = df.astype({col: "object"})  # Fallback
                #
                # for col in desired_dtypes.keys():
                #     if col not in df.columns:
                #         df[col] = None

                values_list = []

                for index, row in df.iterrows():
                    # Create the value group for this specific row
                    row_str = (
                        f"("
                        f"{get_sql_value(row, 'activity_id')}, "
                        f"{get_sql_value(row, 'type', quote=True)}, "
                        f"{get_sql_value(row, 'manufacturer', quote=True)}, "
                        f"{get_sql_value(row, 'product', quote=True)}, "
                        f"{get_sql_value(row, 'serial_number')}, "
                        f"{get_sql_value(row, 'time_created', quote=True)}, "
                        f"{get_sql_value(row, 'number')}"
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
            elif tabl == "length" and not df.empty:
                # *** REVIEW/EDIT THIS SCHEMA ***
                desired_dtypes = {
                    "activity_id": "int64",
                    "timestamp": "datetime64[ns, UTC]",
                    "start_time": "datetime64[ns, UTC]",
                    "total_timer_time": "float64",
                    "total_strokes": "float64",
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
                        f"{get_sql_value(row, 'activity_id')}, "
                        f"{get_sql_value(row, 'timestamp', quote=True)}, "
                        f"{get_sql_value(row, 'start_time', quote=True)}, "
                        f"{get_sql_value(row, 'total_timer_time')}, "
                        f"{get_sql_value(row, 'total_strokes')}, "
                        f"{get_sql_value(row, 'avg_speed')}, "
                        f"{get_sql_value(row, 'swim_stroke', quote=True)}"
                        f")"
                    )
                    values_list.append(row_str)

                if values_list:
                    # Join all rows with a comma and newline
                    bulk_values = ",\n".join(values_list)

                    # Construct the final bulk insert statement
                    sql = f"""
                    INSERT INTO length(
                        activity_id, timestamp, start_time,  
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
