-- Classify every staged row against the current target before MERGE runs.
-- The business columns are the same ones the MERGE update predicate compares:
-- customer_id, plan_code, status, monthly_amount, updated_at.

SELECT action, COUNT(*) AS n
FROM (
    SELECT
        CASE
            WHEN s.change_type = 'DELETE' AND t.subscription_id IS NULL THEN 'already_absent'
            WHEN s.change_type = 'DELETE' THEN 'delete'
            WHEN t.subscription_id IS NULL THEN 'insert'
            WHEN t.customer_id IS DISTINCT FROM s.customer_id
              OR t.plan_code IS DISTINCT FROM s.plan_code
              OR t.status IS DISTINCT FROM s.status
              OR t.monthly_amount IS DISTINCT FROM s.monthly_amount
              OR t.updated_at IS DISTINCT FROM s.updated_at
            THEN 'update'
            ELSE 'unchanged'
        END AS action
    FROM stg_subscriptions AS s
    LEFT JOIN subscriptions AS t
        ON t.subscription_id = s.subscription_id
) AS classified
GROUP BY action;
