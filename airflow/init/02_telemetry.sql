CREATE TABLE IF NOT EXISTS telemetry (
    id                   BIGSERIAL PRIMARY KEY,
    customer_id          BIGINT NOT NULL,
    signal_quality       REAL NOT NULL DEFAULT 0,
    battery_level        REAL NOT NULL DEFAULT 0,
    response_time_ms     REAL NOT NULL DEFAULT 0,
    session_duration_sec INTEGER NOT NULL DEFAULT 0,
    movements_count      INTEGER NOT NULL DEFAULT 0,
    recorded_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO telemetry (customer_id, signal_quality, battery_level, response_time_ms, session_duration_sec, movements_count, recorded_at) VALUES
(1, 87.5, 92.3, 45.2, 3600, 1250, now() - interval '1 day' - interval '5 minutes'),
(1, 85.0, 88.1, 48.7, 2400,  980, now() - interval '1 day' - interval '4 minutes'),
(1, 90.1, 94.5, 42.0, 3000, 1100, now() - interval '1 day' - interval '3 minutes'),
(2, 91.2, 95.0, 38.5, 4200, 1800, now() - interval '1 day' - interval '2 minutes'),
(2, 89.8, 90.2, 41.3, 3800, 1650, now() - interval '1 day' - interval '1 minute'),
(3, 78.3, 82.5, 55.1, 1800,  650, now() - interval '1 day' - interval '40 seconds'),
(3, 80.1, 85.0, 52.3, 2100,  750, now() - interval '1 day' - interval '20 seconds');