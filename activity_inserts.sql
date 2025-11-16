

INSERT INTO activity(activity_id, timestamp, adjusted_distance, adjusted_duration, workout_feel, effort, category, activity_name, description, total_timer_time, local_timestamp, num_sessions, type, event, event_type, event_group)
                    VALUES (1, '2025-08-03 18:45:09+00:00', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 3240.242, '2025-08-03 13:45:09', 1, 'manual', 'activity', 'stop', NULL)
                    ON CONFLICT (activity_id) DO NOTHING;


INSERT INTO activity(activity_id, timestamp, adjusted_distance, adjusted_duration, workout_feel, effort, category, activity_name, description, total_timer_time, local_timestamp, num_sessions, type, event, event_type, event_group)
                    VALUES (1, '2025-08-03 18:45:09+00:00', 9152.19, 3240.242, NULL, NULL, NULL, 'Unknown Location Running', NULL, 3240.242, '2025-08-03 13:45:09', 1, 'manual', 'activity', 'stop', NULL)
                    ON CONFLICT (activity_id) DO NOTHING;


INSERT INTO activity(activity_id, timestamp, adjusted_distance, adjusted_duration, workout_feel, effort, category, activity_name, description, total_timer_time, local_timestamp, num_sessions, type, event, event_type, event_group)
                    VALUES (1, '2025-08-03 18:45:09+00:00', 9152.19, 3240.242, NULL, NULL, NULL, 'Unknown Location Running', NULL, 3240.242, '2025-08-03 13:45:09', 1, 'manual', 'activity', 'stop', NULL)
                    ON CONFLICT (activity_id) DO NOTHING;


INSERT INTO activity(activity_id, timestamp, adjusted_distance, adjusted_duration, workout_feel, effort, category, activity_name, description, total_timer_time, local_timestamp, num_sessions, type, event, event_type, event_group)
                    VALUES (1, '2025-08-03 18:45:09+00:00', 9152.19, 3240.242, NULL, NULL, NULL, 'Mountain Brook Running', NULL, 3240.242, '2025-08-03 13:45:09', 1, 'manual', 'activity', 'stop', NULL)
                    ON CONFLICT (activity_id) DO NOTHING;
