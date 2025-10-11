SELECT a.*, s.total_distance FROM public.activity a
JOIN public.session s ON a.activity_id = s.activity_id 
WHERE a.num_sessions > 1 --AND s.sport = 'swimming' -- doesn't get multisport sessions
GROUP BY a.activity_id, s.total_distance
ORDER BY a.adjusted_distance DESC, SUM(s.total_distance) DESC
	
-- ORDER BY a.adjusted_distance DESC
-- SELECT * from public.activity
-- WHERE activity_id = 4033373463	