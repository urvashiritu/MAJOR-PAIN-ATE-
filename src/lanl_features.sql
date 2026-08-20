-- Per-event behavioral features over the LANL auth slice, with red-team labels.
CREATE OR REPLACE TABLE redteam_distinct AS SELECT DISTINCT * FROM redteam;

CREATE OR REPLACE TABLE feat AS
WITH base AS (
    SELECT
        a.time,
        a.src_user,
        a.dst_user,
        a.src_computer,
        a.dst_computer,
        a.auth_type,
        a.logon_type,
        a.orientation,
        a.result,
        (a.time % 86400) / 3600 AS hour,
        EXISTS (
            SELECT 1 FROM redteam_distinct r
            WHERE r.time = a.time AND r.user = a.src_user
              AND r.src_computer = a.src_computer AND r.dst_computer = a.dst_computer
        ) AS is_red
    FROM auth_slice a
)
SELECT
    b.*,
    CASE WHEN min(b.time) OVER (PARTITION BY b.src_user, b.dst_computer) = b.time THEN 1 ELSE 0 END AS dst_first,
    CASE WHEN min(b.time) OVER (PARTITION BY b.src_user, b.src_computer) = b.time THEN 1 ELSE 0 END AS src_first,
    count(*) OVER (PARTITION BY b.src_user, b.hour) AS hour_events,
    count(*) OVER (PARTITION BY b.src_user) AS user_events,
    count(*) OVER (PARTITION BY b.src_user, b.dst_computer ORDER BY b.time RANGE BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS dst_prior_events,
    coalesce(sum(CASE WHEN b.result = 'Fail' THEN 1 ELSE 0 END) OVER (PARTITION BY b.src_user ORDER BY b.time RANGE BETWEEN 3600 PRECEDING AND 1 PRECEDING), 0) AS fail_1h,
    count(*) OVER (PARTITION BY b.src_user ORDER BY b.time RANGE BETWEEN 3600 PRECEDING AND 1 PRECEDING) AS vel_1h
FROM base b;