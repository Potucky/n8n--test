-- MERGE staged subscription changes into the target.
-- A matched DELETE removes the key. A DELETE for a missing key does nothing.
-- A new UPSERT inserts. A matched UPSERT updates only when a business column differs,
-- so replaying the same batch does not rewrite the row.

MERGE INTO subscriptions AS t
USING stg_subscriptions AS s
    ON t.subscription_id = s.subscription_id
WHEN MATCHED AND s.change_type = 'DELETE' THEN DELETE
WHEN MATCHED AND s.change_type = 'UPSERT'
    AND (
        t.customer_id IS DISTINCT FROM s.customer_id
        OR t.plan_code IS DISTINCT FROM s.plan_code
        OR t.status IS DISTINCT FROM s.status
        OR t.monthly_amount IS DISTINCT FROM s.monthly_amount
        OR t.updated_at IS DISTINCT FROM s.updated_at
    )
THEN UPDATE SET
    customer_id = s.customer_id,
    plan_code = s.plan_code,
    status = s.status,
    monthly_amount = s.monthly_amount,
    updated_at = s.updated_at,
    loaded_batch_id = s.batch_id
WHEN NOT MATCHED AND s.change_type = 'UPSERT' THEN
INSERT (
    subscription_id,
    customer_id,
    plan_code,
    status,
    monthly_amount,
    updated_at,
    loaded_batch_id
)
VALUES (
    s.subscription_id,
    s.customer_id,
    s.plan_code,
    s.status,
    s.monthly_amount,
    s.updated_at,
    s.batch_id
);
