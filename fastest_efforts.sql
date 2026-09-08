CREATE OR REPLACE FUNCTION shortest_duration_for_distance(event_distance INTEGER, activity BIGINT)
RETURNS TABLE(sport VARCHAR(50), shortest_duration INTERVAL, start_time TIMESTAMP WITH TIME ZONE) AS $$
BEGIN
    RETURN QUERY
    WITH sessions AS (
        SELECT
            s.session_id,
            s.activity_id,
            s.sport,
            s.start_time,
            LEAD(s.start_time) OVER (
                PARTITION BY s.activity_id
                ORDER BY s.start_time
            ) AS next_start_time
        FROM session s
    ),
    cumulative_distances AS (
        SELECT 
            s.session_id,
            s.sport,
            r.timestamp,
            r.distance,
            LAG(r.timestamp) OVER (
                PARTITION BY s.session_id
                ORDER BY r.timestamp
            ) AS start_timestamp,
            LAG(r.distance) OVER (
                PARTITION BY s.session_id
                ORDER BY r.timestamp
            ) AS start_distance
        FROM sessions s
        JOIN record r
            ON r.activity_id = s.activity_id
            AND r.timestamp >= s.start_time
            AND (
                r.timestamp < s.next_start_time
                OR s.next_start_time IS NULL
            )
        WHERE r.activity_id = activity
    ),
    intervals AS (
        SELECT 
            a.session_id,
            a.sport,
            a.timestamp - b.timestamp AS duration,
            a.distance - b.distance AS distance_covered,
            b.timestamp AS start_time
        FROM cumulative_distances a
        JOIN cumulative_distances b
            ON a.session_id = b.session_id
            AND a.timestamp > b.timestamp
        WHERE a.distance - b.distance >= event_distance
    ),
    ranked_intervals AS (
        SELECT
            i.*,
            ROW_NUMBER() OVER (
                PARTITION BY i.sport
                ORDER BY i.duration
            ) AS rn
        FROM intervals i
    )
    SELECT
        r.sport,
        r.duration AS shortest_duration,
        r.start_time
    FROM ranked_intervals r
    WHERE rn = 1 -- remove this to allow tied times to return
    ORDER BY sport;
END;
$$ LANGUAGE plpgsql;
-- SELECT * FROM shortest_duration_for_distance(10000, 10368363529);
