

INSERT INTO session(activity_id, timestamp, start_time, total_elapsed_time, total_timer_time, total_distance, event, event_type, sport, sub_sport)
                        VALUES (1, '2025-08-03 18:45:09+00:00', '2025-08-03 18:45:09+00:00', 3965.428, 3240.242, 9152.19, 'session', 'stop', 'running', 'generic')
                        ON CONFLICT (activity_id, timestamp) DO NOTHING;
