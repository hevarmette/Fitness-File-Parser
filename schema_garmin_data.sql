/* renamed record columns: speed to enhanced_speed
added fractional_cadence which is a floating decimal to one decimal place
fractional_cadence DECIMAL(1,1)
dropped power and temperature columns
DONE IMPLEMENTING THE ABOVE

changed lap columns from ['number', 'start_time', 'total_distance', 'total_elapsed_time', 'max_speed', 
'max_heart_rate', 'avg_heart_rate']
to ['number', 'start_time', 'total_distance', 
	ADD				 'total_timer_time', 'total_ascent', 'total_descent', 
					 'avg_heart_rate', 'max_heart_rate', 
	ADD				 'avg_step_length', 'avg_stance_time', 'avg_stance_time_balance', 'avg_running_cadence', 
					 'avg_vertical_oscillation', 'avg_vertical_ratio']
	REMOVE			 'max_speed', 'total_elapsed_time'

total_ascent smallint
total_descent smallint
avg_vertical_oscillation real
avg_stance_time real
avg_vertical_ratio real
avg_stance_time_balance real
avg_step_length real
avg_heart_rate smallint
max_heart_rate smallint
avg_running_cadence smallint
total_timer_time real
DONE IMPLEMENTING THE ABOVE
 */
-- Create sequences
/*CREATE SEQUENCE file_id_record_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

CREATE SEQUENCE lap_lap_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

CREATE SEQUENCE record_record_id_seq
    AS bigint
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

CREATE SEQUENCE session_session_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    

CREATE SEQUENCE length_length_id_seq
  AS integer
  START WITH 1
  INCREMENT BY 1
  NO MINVALUE
  NO MAXVALUE
  CACHE 1;
*/

-- Create tables with default values from sequences
CREATE TABLE activity (
    --activity_id bigint DEFAULT nextval('lap_lap_id_seq'::regclass) NOT NULL,
    activity_id bigserial NOT NULL,
    "timestamp" timestamp with time zone,
    /*
    insert new columns from json here
    Distance  Duration Workout_Feel Effort Category                Activity_Name                                        Description
    */
    adjusted_distance real,
    adjusted_duration real,
    workout_feel smallint,
    effort smallint,
    category char(15),
    activity_name text,
    description text,
    
    total_timer_time real,
    local_timestamp timestamp without time zone,
    num_sessions integer,
    type character varying(50),
    event character varying(50),
    event_type character varying(50),
    event_group character varying(50),
    PRIMARY KEY (activity_id)
);

CREATE TABLE file_id (
    --file_id integer DEFAULT nextval('record_record_id_seq'::regclass) NOT NULL,
    file_id serial NOT NULL,
    activity_id bigint NOT NULL,
    serial_number bigint,
    time_created timestamp with time zone,
    manufacturer character varying(50),
    number real,
    type character varying(50),
    product character varying(50),
    PRIMARY KEY (file_id),
    CONSTRAINT fk_file_id_activity FOREIGN KEY (activity_id) REFERENCES activity(activity_id)
);

CREATE TABLE lap (
    --lap_id integer DEFAULT nextval('lap_lap_id_seq'::regclass) NOT NULL,
    lap_id serial NOT NULL,
    activity_id bigint NOT NULL,
    start_time timestamp with time zone,
    number smallint,
    total_distance real,
    total_timer_time real,
    total_ascent smallint,
    total_descent smallint,
    avg_vertical_oscillation real,
    avg_stance_time real,
    avg_vertical_ratio real,
    avg_stance_time_balance real,
    avg_step_length real,
    avg_running_cadence smallint,
    max_heart_rate smallint,
    avg_heart_rate smallint,
    intensity VARCHAR(20),
    PRIMARY KEY (lap_id),
    CONSTRAINT fk_lap_activity FOREIGN KEY (activity_id) REFERENCES activity(activity_id)
);

CREATE TABLE record (
    --record_id bigint DEFAULT nextval('record_record_id_seq'::regclass) NOT NULL,
    record_id bigserial NOT NULL, 
    activity_id bigint NOT NULL,
    latitude double precision,
    longitude double precision,
    lap smallint,
    altitude real,
    "timestamp" timestamp with time zone,
    heart_rate smallint,
    cadence smallint,
    fractional_cadence DECIMAL(1,1),
    enhanced_speed real,
    distance real,
    PRIMARY KEY (record_id),
    CONSTRAINT fk_record_activity FOREIGN KEY (activity_id) REFERENCES activity(activity_id)
);

CREATE TABLE session (
    --session_id integer DEFAULT nextval('session_session_id_seq'::regclass) NOT NULL,
    session_id serial NOT NULL,
    activity_id bigint NOT NULL,
    "timestamp" timestamp with time zone,
    start_time timestamp with time zone,
    start_position_lat float,
    start_position_long float,
    total_elapsed_time real,
    total_timer_time real,
    total_distance real,
    total_strokes real,
    nec_lat float,
    nec_long float,
    swc_lat float,
    swc_long float,
    message_index integer,
    total_calories smallint,
    total_fat_calories real,
    enhanced_avg_speed real,
    avg_speed real,
    enhanced_max_speed real,
    max_speed real,
    avg_power real,
    max_power real,
    total_ascent smallint,
    total_descent smallint,
    first_lap_index smallint,
    num_laps smallint,
    event character varying(50),
    event_type character varying(50),
    sport character varying(50),
    sub_sport character varying(50),
    avg_heart_rate smallint,
    max_heart_rate smallint,
    avg_cadence smallint,
    max_cadence smallint,
    total_training_effect real,
    event_group real,
    trigger character varying(50),
    pool_length smallint,
    pool_length_unit character varying(20),
    PRIMARY KEY (session_id),
    CONSTRAINT fk_session_activity FOREIGN KEY (activity_id) REFERENCES activity(activity_id)
);

CREATE TABLE length (
  --length_id integer DEFAULT nextval('length_length_id_seq'::regclass) NOT NULL,
  length_id serial NOT NULL,
  activity_id bigint NOT NULL,
  "timestamp" timestamp with time zone,
  start_time timestamp with time zone,
  message_index smallint, 
  total_timer_time real,
  total_strokes smallint, 
  avg_speed real,
  swim_stroke varchar(15),
  length_type varchar(15),
  PRIMARY KEY (length_id),
  CONSTRAINT fk_length_activity FOREIGN KEY (activity_id) REFERENCES activity(activity_id)
);
