-- Key-level diff of the pre-load snapshot against the current target.
-- The hash covers the same business columns the MERGE treats as a change.

WITH snap AS (
    SELECT
        subscription_id,
        md5(concat_ws(
            '|',
            customer_id,
            plan_code,
            status,
            CAST(monthly_amount AS VARCHAR),
            CAST(updated_at AS VARCHAR)
        )) AS row_hash
    FROM subscriptions_snapshot
),
cur AS (
    SELECT
        subscription_id,
        md5(concat_ws(
            '|',
            customer_id,
            plan_code,
            status,
            CAST(monthly_amount AS VARCHAR),
            CAST(updated_at AS VARCHAR)
        )) AS row_hash
    FROM subscriptions
)
SELECT
    COALESCE(cur.subscription_id, snap.subscription_id) AS subscription_id,
    CASE
        WHEN snap.subscription_id IS NULL THEN 'inserted'
        WHEN cur.subscription_id IS NULL THEN 'deleted'
        WHEN snap.row_hash IS DISTINCT FROM cur.row_hash THEN 'updated'
        ELSE 'unchanged'
    END AS diff_action
FROM cur
FULL OUTER JOIN snap
    ON cur.subscription_id = snap.subscription_id
ORDER BY subscription_id;
