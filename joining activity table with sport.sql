WITH sport_classification AS (
                SELECT 
                    s.activity_id,
                    CASE 
                        WHEN COUNT(DISTINCT s.sport) > 1 THEN 'multi_sport'
                        ELSE MAX(s.sport)
                    END AS sport
                FROM public.session s
                GROUP BY s.activity_id
            )
            SELECT *
                -- a.activity_id, 
                -- DATE(a.timestamp) AS activity_date, 
                -- a.activity_name, 
                -- sc.sport AS sport
            FROM 
                public.activity a
            LEFT JOIN 
                sport_classification sc ON a.activity_id = sc.activity_id
			WHERE adjusted_distance/1609.335 > 9
			AND sport = 'running'
            ORDER BY timestamp DESC
-- SELECT * FROM public.activity
-- WHERE adjusted_distance/1609.335 > 9
-- ORDER BY timestamp DESC 