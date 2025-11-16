

INSERT INTO file_id(activity_id, type, manufacturer, product, serial_number, time_created, number)
                    VALUES (1, 'activity', 'garmin', 4570, 3611338015, '2025-08-03 18:45:09+00:00', NULL)
                    ON CONFLICT (activity_id) DO NOTHING;
