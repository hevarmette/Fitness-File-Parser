from datetime import datetime
from typing import Dict, Union, Optional, Tuple
import os
import pandas as pd
import fitdecode
from dotenv import load_dotenv
from helpers import get_conn

load_dotenv()
dir = os.getenv("FIT_DIR")
file_extension = ".fit"

# Connection details for Postgresql DB.
conn = get_conn()
session = ["sub_sport", "pool_length", "pool_length_unit"]


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
        if tabl == "session":
            df = df.astype(
                {
                    "activity_id": "int64",
                    "sub_sport": "object",
                    "pool_length": "int64",
                    "pool_length_unit": "object",
                }
            )
            for index, row in df.iterrows():
                cursor.execute(
                    """update session set pool_length = %s, pool_length_unit = %s 
                where activity_id = %s and sub_sport = %s""",
                    [
                        row.pool_length,
                        row.pool_length_unit,
                        row.activity_id,
                        row.sub_sport,
                    ],
                )

        conn.commit()
        cursor.close()


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


def get_dataframes(fname: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Takes the path to a FIT file (as a string) and returns two Pandas
    DataFrames: one containing data about the laps, and one containing
    data about the individual points.
    """

    session_data = []

    with fitdecode.FitReader(fname) as fit_file:
        for frame in fit_file:
            if isinstance(frame, fitdecode.records.FitDataMessage):
                if frame.name == "session":
                    session_data.append(get_fit_other_data(session, frame))

    # Create DataFrames from the data we have collected. If any information is missing from a particular lap or track
    # point, it will show up as a null value or "NaN" in the DataFrame.

    session_df = pd.DataFrame(session_data, columns=session)

    session_df["activity_id"] = activity_id
    session_df = session_df[session_df["sub_sport"] == "lap_swimming"]
    return session_df


# Function to extract the date from the filename
def extract_date_from_filename(filename):
    # Assuming the format is YYYY-mm-ddThh.mm.ss
    date_str = filename.split("T")[0]  # Extract the date part (YYYY-mm-dd)
    # time_str = filename.split('T')[1].split('.')[0:3]  # Extract the time part (hh.mm.ss)
    # time_str = '.'.join(time_str)  # Combine the time parts back into a string
    # timestamp_str = date_str + 'T' + time_str  # Combine date and time parts
    return datetime.strptime(date_str, "%Y-%m-%d")


if __name__ == "__main__":
    from os import listdir
    from os.path import isfile, join
    from datetime import datetime

    # latest date in the database
    # Query the latest timestamp from the activity table before today
    today = datetime.now().date()
    with conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT MAX(timestamp::date) FROM public.activity WHERE timestamp::date <= %s",
                (today,),
            )
            row = cursor.fetchone()
            # after_date = datetime.strptime(row[0], '%Y-%m-%d').date() if row is not None else None
            after_date = row[0]
            if after_date is None:
                print("No activity found before today")
                exit(1)

    files = [
        f for f in listdir(dir) if isfile(join(dir, f)) and f.endswith(file_extension)
    ]

    errors = []
    index = [0]
    for file in files:
        try:
            # fname = dir+"\\"+file# WINDOWS
            fname = dir + file  # LINUX

            activity_id = get_user_activity_details(fname)
            session_df = get_dataframes(fname)
            # print('user_activity:', activity_id)
            # load to DB
            load_dataframe_to_postgres(session_df, "session")
            # ERRORS ['10779726137', '10636216438', '10528926754', '8123112565', '6947713945', '11510943425', '13840205941', '15855828516', '16371670919', '16313355920', '16533124109', '16558142255', '16576282783', '16594262279', '16663462353', '16619751226', '16628552969']
        except:
            errors.append(activity_id)
    print("finished")
    print("errors")
    print(errors)
