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
    -- 1 & 2: materialize record -> session assignment once, indexed.
    --
    -- Fix #1 (LATERAL fan-out): compute each session's window with a single
    -- LEAD() over sessions, one row per session, instead of an uncorrelated
    -- lateral that fanned every activity record into every session.
    --
    -- Fix #2 (cumulative distance rebase): record.distance is an activity-wide
    -- odometer, so we subtract each session's first distance to get the
    -- distance covered *within* that session (session_distance).
    --
    -- Fix #5 (NULL distance): exclude NULL-distance records explicitly.
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
    )
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
    WHERE r.distance IS NOT NULL;

    CREATE INDEX ON _session_records (session_id, session_distance, timestamp);
    ANALYZE _session_records;

    -- 3 & 4: index-probe matching, then rank per activity+sport.
    RETURN QUERY
    WITH best_pairs AS (
        SELECT
            a.activity_id,
            a.sport,
            a.timestamp - b.timestamp AS duration,
            b.timestamp AS start_time
        FROM _session_records a
        CROSS JOIN LATERAL (
            SELECT c.timestamp
            FROM _session_records c
            WHERE c.session_id = a.session_id
              -- Fix #2/#7: compare rebased distance in double precision
              AND c.session_distance <= a.session_distance - p_event_distance::double precision
              -- Fix #4: the start point must precede the end point, so flat /
              -- stationary stretches can't yield zero or negative durations.
              AND c.timestamp < a.timestamp
            ORDER BY c.session_distance DESC, c.timestamp DESC
            LIMIT 1
        ) b
    ),
    ranked AS (
        SELECT
            bp.*,
            ROW_NUMBER() OVER (
                PARTITION BY bp.activity_id, bp.sport
                -- Fix #8: deterministic tie-break on start_time
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
