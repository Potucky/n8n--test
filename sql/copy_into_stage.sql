-- COPY-like load from a local CSV or JSON extract into a transient staging table.
-- __READER__ is replaced with read_csv_auto or read_json_auto (allowlisted).
-- The extract window is half-open: updated_at >= extract_from AND updated_at < extract_to.
-- When the file repeats a natural key, the latest updated_at wins, then the higher extract_seq.

CREATE OR REPLACE TABLE stg_subscriptions AS
WITH raw AS (
    SELECT
        CAST(subscription_id AS VARCHAR) AS subscription_id,
        CAST(customer_id AS VARCHAR) AS customer_id,
        CAST(plan_code AS VARCHAR) AS plan_code,
        CAST(status AS VARCHAR) AS status,
        CAST(monthly_amount AS DECIMAL(10, 2)) AS monthly_amount,
        CAST(updated_at AS TIMESTAMP) AS updated_at,
        CAST(change_type AS VARCHAR) AS change_type,
        CAST(extract_seq AS INTEGER) AS extract_seq
    FROM __READER__($path)
),
windowed AS (
    SELECT *
    FROM raw
    WHERE updated_at >= $extract_from
      AND updated_at < $extract_to
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY subscription_id
            ORDER BY updated_at DESC, extract_seq DESC
        ) AS rn
    FROM windowed
)
SELECT
    subscription_id,
    customer_id,
    plan_code,
    status,
    monthly_amount,
    updated_at,
    change_type,
    extract_seq,
    $batch_id AS batch_id
FROM ranked
WHERE rn = 1;
