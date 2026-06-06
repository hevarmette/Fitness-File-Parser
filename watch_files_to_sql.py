from __future__ import annotations

from typing import Any

import pandas as pd
import os


def write_sql_statement_to_file(df: pd.DataFrame, tabl: str, log_file_path: str | None = None, return_sql: bool = False) -> str | None:
    """
    Outputs SQL INSERT statements with robust formatting.

    :param return_sql: If True, returns the SQL string instead of writing to a file.
    """

    # ---------------------------------------------------------
    # 1. HELPER FUNCTIONS
    # ---------------------------------------------------------
    def sql_format(value: Any, quote: bool = False) -> str:
        """
        Replaces NaN with NULLs and double quotes apostrophes to prevent accidentally ending strings with an apostrophe
        """
        if pd.isna(value):
            return "NULL"
        if quote:
            # Escape single quotes by doubling them
            safe = str(value).replace("'", "''")
            return f"'{safe}'"
        return str(value)

    def get_sql_value(row: pd.Series, col: str, quote: bool = False) -> str:
        """
        Will return formatted value for sql statement creation or NULL if column is not present.
        """
        if col in row:
            return sql_format(row[col], quote=quote)
        return "NULL"

    # ---------------------------------------------------------
    # 2. GENERATE SQL STRING
    # ---------------------------------------------------------
    if df.empty:
        return None

    sql = ""

    # --- Activity Table ---
    if tabl == "activity":
        # Remove timezone from local_timestamp if present
        if "local_timestamp" in df.columns and df[
            "local_timestamp"
        ].dtype.name.startswith("datetime64[ns,"):
            df["local_timestamp"] = df["local_timestamp"].dt.tz_localize(None)

        # Determine if we should insert activity_id or let DB auto-increment
        # We assume if the first row has a valid ID, they all do.
        include_id = False
        if "activity_id" in df.columns:
            first_val = df["activity_id"].iloc[0] if not df.empty else None
            if pd.notna(first_val):
                include_id = True

        # 2. Define standard columns (excluding activity_id initially)
        cols_ordered = [
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

        # 3. Add activity_id to columns if valid
        if include_id:
            cols_ordered.insert(0, "activity_id")

        # 4. Ensure all columns exist in DF
        for col in cols_ordered:
            if col not in df.columns:
                df[col] = None

        values_list = []
        for index, row in df.iterrows():
            # Build value list dynamically based on cols_ordered
            row_vals = []
            for col in cols_ordered:
                # define which columns need quotes
                needs_quote = col in [
                    "timestamp",
                    "category",
                    "activity_name",
                    "description",
                    "local_timestamp",
                    "type",
                    "event",
                    "event_type",
                ]
                row_vals.append(get_sql_value(row, col, quote=needs_quote))

            # Join values: (val1, val2, ...)
            row_str = "(" + ", ".join(row_vals) + ")"
            values_list.append(row_str)

        if values_list:
            bulk_values = ",\n".join(values_list)
            cols_str = ", ".join(cols_ordered)

            sql = f"""
            INSERT INTO activity (
                {cols_str}
            )
            VALUES
            {bulk_values}
            ON CONFLICT (activity_id) DO NOTHING;
            """

    # --- Session Table ---
    elif tabl == "session":
        values_list = []
        for index, row in df.iterrows():
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
            bulk_values = ",\n".join(values_list)
            sql = f"""
            INSERT INTO session(
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

    # --- Lap Table ---
    elif tabl == "lap":
        values_list = []
        for index, row in df.iterrows():
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
                f"{get_sql_value(row, 'avg_heart_rate')}, "
                f"{get_sql_value(row, 'avg_power')}, "
                f"{get_sql_value(row, 'max_power')}, "
                f"{get_sql_value(row, 'normalized_power')}"
                f")"
            )
            values_list.append(row_str)

        if values_list:
            bulk_values = ",\n".join(values_list)
            sql = f"""
            INSERT INTO lap(
                activity_id, number, start_time, total_distance, 
                total_timer_time, total_ascent, total_descent, 
                avg_vertical_oscillation, avg_stance_time, avg_vertical_ratio, 
                avg_stance_time_balance, avg_step_length, intensity, 
                avg_running_cadence, max_heart_rate, avg_heart_rate,
                avg_power, max_power, normalized_power
            )
            VALUES 
            {bulk_values};
            """

    # --- Record Table ---
    elif tabl == "record":
        values_list = []
        for index, row in df.iterrows():
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
            values_list.append(f"({', '.join(row_values)})")

        if values_list:
            bulk_values = ",\n".join(values_list)
            sql = f"""
            INSERT INTO record(
                activity_id, latitude, longitude, lap, altitude, 
                timestamp, heart_rate, cadence, fractional_cadence, 
                enhanced_speed, distance
            )
            VALUES 
            {bulk_values};
            """

    # --- File ID Table ---
    elif tabl == "file_id":
        values_list = []
        for index, row in df.iterrows():
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
            bulk_values = ",\n".join(values_list)
            sql = f"""
            INSERT INTO file_id(
                activity_id, type, manufacturer, product, 
                serial_number, time_created, number
            )
            VALUES 
            {bulk_values};
            """

    # --- Length Table ---
    elif tabl == "length" and not df.empty:
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
            col: dtype for col, dtype in desired_dtypes.items() if col in df.columns
        }
        if existing_dtypes:
            df = df.astype(existing_dtypes)

        for col in desired_dtypes.keys():
            if col not in df.columns:
                df[col] = None

        values_list = []
        for index, row in df.iterrows():
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
            bulk_values = ",\n".join(values_list)
            sql = f"""
            INSERT INTO length(
                activity_id, timestamp, start_time,  
                total_timer_time, total_strokes, avg_speed, swim_stroke
            )
            VALUES 
            {bulk_values};
            """

    elif tabl == "event":
        values_list = []
        for index, row in df.iterrows():
            row_str = (
                f"("
                f"{get_sql_value(row, 'activity_id')}, "
                f"{get_sql_value(row, 'timestamp', quote=True)}, "
                f"{get_sql_value(row, 'event', quote=True)}, "
                f"{get_sql_value(row, 'event_type', quote=True)}, "
                f"{get_sql_value(row, 'data', quote=True)}, "
                f"{get_sql_value(row, 'event_group')}"
                f")"
            )
            values_list.append(row_str)

        if values_list:
            bulk_values = ",\n".join(values_list)
            sql = f"""
            INSERT INTO event(
                activity_id, timestamp, event, event_type, data, event_group
            )
            VALUES 
            {bulk_values};
            """

    else:
        print(
            f"Warning: No specific SQL generation logic defined for table '{tabl}'. No statements written."
        )
        return None

    # ---------------------------------------------------------
    # 3. OUTPUT LOGIC (RETURN OR WRITE)
    # ---------------------------------------------------------
    if return_sql:
        return sql
    else:
        if log_file_path is None:
            log_file_path = os.path.join(
                os.path.dirname(__file__), f"{tabl}_inserts.sql"
            )

        print(f"Writing SQL file: {log_file_path}")
        with open(log_file_path, "a") as log_file:
            log_file.write("\n\n")
            log_file.write(sql + "\n")
        return None
