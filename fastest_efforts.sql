-- CREATE OR REPLACE FUNCTION shortest_duration_for_distance(event_distance INTEGER, activity BIGINT)
-- RETURNS INTERVAL AS $$
-- DECLARE
--     shortest_duration INTERVAL;
-- BEGIN
--     WITH cumulative_distances AS (
--         SELECT 
--             timestamp,
--             distance,
--             LAG(timestamp) OVER (ORDER BY timestamp) AS start_timestamp,
--             LAG(distance) OVER (ORDER BY timestamp) AS start_distance
--         FROM public.record
--         WHERE activity_id = activity
--     ),
--     intervals AS (
--         SELECT 
--             a.timestamp - b.timestamp AS duration,
--             a.distance - b.distance AS distance_covered
--         FROM cumulative_distances a
--         CROSS JOIN cumulative_distances b
--         WHERE a.timestamp > b.timestamp
--           AND a.distance - b.distance >= event_distance
--     )
--     SELECT MIN(duration)
--     INTO shortest_duration
--     FROM intervals;

--     RETURN shortest_duration;
-- END;
-- $$ LANGUAGE plpgsql;
-- DROP FUNCTION shortest_duration_for_distance(integer,integer);
-- CREATE OR REPLACE FUNCTION shortest_duration_for_distance(event_distance INTEGER, activity INTEGER)
-- RETURNS TABLE(shortest_duration INTERVAL, start_time TIMESTAMP WITH TIME ZONE) AS $$
-- BEGIN
--     RETURN QUERY
--     WITH cumulative_distances AS (
--         SELECT 
--             timestamp,
--             distance,
--             LAG(timestamp) OVER (ORDER BY timestamp) AS start_timestamp,
--             LAG(distance) OVER (ORDER BY timestamp) AS start_distance
--         FROM public.record
--         WHERE activity_id = activity
--     ),
--     intervals AS (
--         SELECT 
--             a.timestamp - b.timestamp AS duration,
--             a.distance - b.distance AS distance_covered,
--             b.timestamp AS start_time
--         FROM cumulative_distances a
--         CROSS JOIN cumulative_distances b
--         WHERE a.timestamp > b.timestamp
--           AND a.distance - b.distance >= event_distance
--     )
--     SELECT duration, start_time
--     FROM intervals
--     WHERE duration = (SELECT MIN(duration) FROM intervals);
-- END;
-- $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION shortest_duration_for_distance(event_distance INTEGER, activity BIGINT)
RETURNS TABLE(shortest_duration INTERVAL, start_time TIMESTAMP WITH TIME ZONE) AS $$
BEGIN
    RETURN QUERY
    WITH cumulative_distances AS (
        SELECT 
            timestamp,
            distance,
            LAG(timestamp) OVER (ORDER BY timestamp) AS start_timestamp,
            LAG(distance) OVER (ORDER BY timestamp) AS start_distance
        FROM record
        WHERE activity_id = activity
    ),
    intervals AS (
        SELECT 
            a.timestamp - b.timestamp AS duration,
            a.distance - b.distance AS distance_covered,
            b.timestamp AS start_time
        FROM cumulative_distances a
        CROSS JOIN cumulative_distances b
        WHERE a.timestamp > b.timestamp
          AND a.distance - b.distance >= event_distance
    ),
    min_duration AS (
        SELECT MIN(duration) AS min_dur FROM intervals
    )
    SELECT i.duration, i.start_time
    FROM intervals i, min_duration m
    WHERE i.duration = m.min_dur
    ORDER BY i.start_time;
END;
$$ LANGUAGE plpgsql;
-- SELECT * FROM shortest_duration_for_distance(10000, 10368363529);
