/**
    This function can search through thousands of activities in seconds to
    find the fastest time a user has covered some distance, p_event_distance.
    I look through ~4000 activities for a single user in about ~20-30 seconds.
**/

CREATE OR REPLACE FUNCTION shortest_duration_for_distance_all(
    p_event_distance NUMERIC(10, 3),
    p_activity_ids   BIGINT[] DEFAULT NULL   -- NULL = all activities
)
RETURNS TABLE (
    activity_id        BIGINT,
    sport              VARCHAR(50),
    shortest_duration  INTERVAL,
    start_time         TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    -- this is a more efficient way to find the fastest effort for a specified
    -- distance per session of an activity than the original
    -- fastest_efforts.sql file. it materializes a record per session
    -- assignment once, indexed.
    --
    -- a FIT activity can hold several sessions (think swim->bike->run in a
    -- multisport file), but record rows don't carry a session id. so we figure
    -- out each session's time window with a single LEAD() over sessions: a
    -- session owns every record from its start_time up to the next session's
    -- start_time, and the last session runs to the end of the activity.
    --
    -- cumulative distance rebase: record.distance is an activity-wide
    -- odometer, so we subtract each session's first distance to get the
    -- distance covered within that session (session_distance).
    --
    -- records tick roughly once a second, so the point we land on is almost
    -- never sitting exactly on the distance we want. to get a precise effort
    -- time we interpolate between two records, so each row also carries the
    -- next record's distance and timestamp (next_distance / next_timestamp)
    -- via a LEAD() within the session. the interpolation itself happens later,
    -- in best_pairs.
    --
    -- also be sure to exclude NULL-distance records!
    CREATE TEMP TABLE _session_records ON COMMIT DROP AS
    WITH session_bounds AS (
        SELECT
            s.activity_id,
            s.session_id,
            s.sport,
            s.start_time,
            LEAD(s.start_time) OVER (
                PARTITION BY s.activity_id ORDER BY s.start_time
            ) AS next_start_time
        FROM session s
        WHERE p_activity_ids IS NULL OR s.activity_id = ANY(p_activity_ids)
    ),
    rebased AS (
        SELECT
            sb.activity_id,
            sb.session_id,
            sb.sport,
            r.timestamp,
            -- rebase cumulative distance to the start of the session
            (r.distance - MIN(r.distance) OVER (PARTITION BY sb.session_id))::double precision
                AS session_distance
        FROM session_bounds sb
        JOIN record r
            ON r.activity_id = sb.activity_id
            AND r.timestamp >= sb.start_time
            AND (r.timestamp < sb.next_start_time OR sb.next_start_time IS NULL)
        WHERE r.distance IS NOT NULL
    )
    SELECT
        rebased.*,
        -- the record right after this one in the same session. we use this
        -- pair (this record + the next) to interpolate a sub-second start time.
        LEAD(session_distance) OVER (
            PARTITION BY session_id ORDER BY timestamp
        ) AS next_distance,
        LEAD(timestamp) OVER (
            PARTITION BY session_id ORDER BY timestamp
        ) AS next_timestamp
    FROM rebased;

    CREATE INDEX ON _session_records (session_id, session_distance, timestamp);
    ANALYZE _session_records;

    -- index-probe matching, then rank per activity+sport.
    RETURN QUERY
    WITH best_pairs AS (
        SELECT
            a.activity_id,
            a.sport,
            -- the probe gives us b, the last record at or before the target
            -- distance. b is almost always a touch too far back (the odometer
            -- jumped past the target somewhere between b and b.next_timestamp),
            -- so measuring from b.timestamp would report an effort slightly
            -- longer than p_event_distance.
            --
            -- fix: interpolate the exact instant the odometer crossed the
            -- target, assuming constant speed across that one-second gap.
            --   target   = a.session_distance - p_event_distance
            --   fraction = how far between b and its next record the target sits
            --   start    = b.timestamp + fraction * (gap in time to next record)
            -- NULLIF guards a stationary gap (next_distance = session_distance),
            -- which would divide by zero; that candidate just drops out.
            a.timestamp - (
                b.timestamp
                + (
                    (a.session_distance - p_event_distance::double precision - b.session_distance)
                    / NULLIF(b.next_distance - b.session_distance, 0)
                  ) * (b.next_timestamp - b.timestamp)
            ) AS duration,
            b.timestamp AS start_time
        FROM _session_records a
        CROSS JOIN LATERAL (
            -- For end point a, look for the latest/closest earlier point c that is at least
            -- p_event_distance behind it
            SELECT
                c.timestamp,
                c.session_distance,
                c.next_distance,
                c.next_timestamp
            FROM _session_records c
            WHERE c.session_id = a.session_id
              -- compare rebased distance in double precision
              AND c.session_distance <= a.session_distance - p_event_distance::double precision
              -- the start point must precede the end point, so flat /
              -- stationary stretches can't yield zero or negative durations.
              AND c.timestamp < a.timestamp
              -- need the next record to interpolate against; the very last
              -- record of a session has none, and can't be a start anyway.
              AND c.next_timestamp IS NOT NULL
            ORDER BY c.session_distance DESC, c.timestamp DESC
            LIMIT 1
        ) b
    ),
    ranked AS (
        -- this returns the time and effort to the nearest record.timestamp, not the interpolated
        -- timestamp
        SELECT
            bp.*,
            ROW_NUMBER() OVER (
                PARTITION BY bp.activity_id, bp.sport
                -- deterministic tie-break on start_time
                ORDER BY bp.duration, bp.start_time
            ) AS rn
        FROM best_pairs bp
    )
    SELECT ranked.activity_id, ranked.sport, ranked.duration, ranked.start_time
    FROM ranked
    WHERE rn = 1
    ORDER BY ranked.activity_id, ranked.sport;
END;
$$;
