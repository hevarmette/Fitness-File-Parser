"""
Backfill avg_power, max_power, normalized_power for existing lap rows.

Scans all .fit files in FIT_DIR, extracts lap power data, and UPDATEs
matching rows in the lap table using activity timestamp to find the activity_id.
"""

import os
import fitdecode
from os import listdir
from os.path import isfile, join
from helpers import get_conn
from dotenv import load_dotenv

load_dotenv()

POWER_FIELDS = ["avg_power", "max_power", "normalized_power"]


def extract_lap_power(fname):
    """Returns list of dicts with lap number and power fields from a FIT file."""
    laps = []
    lap_no = 1
    with fitdecode.FitReader(fname) as fit:
        for frame in fit:
            if not isinstance(frame, fitdecode.records.FitDataMessage):
                continue
            if frame.name == "lap":
                power = {}
                for field in POWER_FIELDS:
                    if frame.has_field(field):
                        power[field] = frame.get_value(field)
                if any(v is not None for v in power.values()):
                    power["number"] = lap_no
                    laps.append(power)
                lap_no += 1
    return laps


def get_activity_timestamp(fname):
    """Extracts the activity timestamp from a FIT file."""
    with fitdecode.FitReader(fname) as fit:
        for frame in fit:
            if isinstance(frame, fitdecode.records.FitDataMessage) and frame.name == "activity":
                if frame.has_field("timestamp"):
                    return frame.get_value("timestamp")
    return None


if __name__ == "__main__":
    raw_dir = os.getenv("FIT_DIR")
    fit_dir = os.path.expandvars(raw_dir)

    files = [f for f in listdir(fit_dir) if isfile(join(fit_dir, f)) and f.endswith(".fit")]

    conn = get_conn()
    updated = 0
    skipped = 0

    for file in files:
        fname = join(fit_dir, file)
        laps = extract_lap_power(fname)

        if not laps:
            continue

        ts = get_activity_timestamp(fname)
        if ts is None:
            print(f"[SKIP] No activity timestamp: {file}")
            skipped += 1
            continue

        # Find activity_id by timestamp
        with conn.cursor() as cur:
            cur.execute("SELECT activity_id FROM activity WHERE timestamp = %s", (ts,))
            row = cur.fetchone()

        if row is None:
            print(f"[SKIP] No matching activity in DB: {file}")
            skipped += 1
            continue

        activity_id = row[0]

        for lap in laps:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE lap
                       SET avg_power = %s, max_power = %s, normalized_power = %s
                       WHERE activity_id = %s AND number = %s""",
                    (
                        lap.get("avg_power"),
                        lap.get("max_power"),
                        lap.get("normalized_power"),
                        activity_id,
                        lap["number"],
                    ),
                )
                if cur.rowcount:
                    updated += cur.rowcount

        conn.commit()
        print(f"[OK] {file} -> activity {activity_id}: {len(laps)} laps updated")

    conn.close()
    print(f"\nDone. Updated {updated} laps, skipped {skipped} files.")
