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
    CREATE TEMP TABLE _session_records ON COMMIT DROP AS
    SELECT
        s.activity_id,
        s.session_id,
        s.sport,
        r.timestamp,
        r.distance
    FROM session s
    JOIN LATERAL (
        SELECT lead(s2.start_time) OVER (
                   PARTITION BY s2.activity_id ORDER BY s2.start_time
               ) AS next_start_time
        FROM session s2
        WHERE s2.activity_id = s.activity_id
    ) nxt ON true
    JOIN record r
        ON r.activity_id = s.activity_id
        AND r.timestamp >= s.start_time
        AND (r.timestamp < nxt.next_start_time OR nxt.next_start_time IS NULL)
    WHERE p_activity_ids IS NULL OR s.activity_id = ANY(p_activity_ids);

    CREATE INDEX ON _session_records (session_id, distance, timestamp);
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
              AND c.distance <= a.distance - p_event_distance
            ORDER BY c.distance DESC, c.timestamp DESC
            LIMIT 1
        ) b
    ),
    ranked AS (
        SELECT
            bp.*,
            ROW_NUMBER() OVER (
                PARTITION BY bp.activity_id, bp.sport
                ORDER BY bp.duration
            ) AS rn
        FROM best_pairs bp
    )
    SELECT ranked.activity_id, ranked.sport, ranked.duration, ranked.start_time
    FROM ranked
    WHERE rn = 1
    ORDER BY ranked.activity_id, ranked.sport;
END;
$$;
