

INSERT INTO activity(activity_id, timestamp, adjusted_distance, adjusted_duration, workout_feel, effort, category, activity_name, description, total_timer_time, local_timestamp, num_sessions, type, event, event_type, event_group)
                    VALUES (0, '2025-10-09 22:20:39+00:00', 16556.66, 3769.8509999999997, NULL, NULL, NULL, 'Multisport', NULL, 3769.851, '2025-10-09 17:20:39', 3, 'auto_multi_sport', 'activity', 'stop', NULL)
                    ON CONFLICT (activity_id) DO NOTHING;


INSERT INTO activity(activity_id, timestamp, adjusted_distance, adjusted_duration, workout_feel, effort, category, activity_name, description, total_timer_time, local_timestamp, num_sessions, type, event, event_type, event_group)
                    VALUES (0, '2025-08-09 12:38:39+00:00', 18038.120000000003, 3032.4939999999997, NULL, NULL, NULL, 'Multisport', NULL, 3032.494, '2025-08-09 07:38:39', 5, 'auto_multi_sport', 'activity', 'stop', NULL)
                    ON CONFLICT (activity_id) DO NOTHING;
