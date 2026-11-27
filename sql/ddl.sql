-- Subscription warehouse tables.
-- subscriptions is the MERGE target. load_audit appends one row per batch run.
-- Timestamps are TIMESTAMP without time zone, the usual shape of a
-- Snowflake TIMESTAMP_NTZ extract.

CREATE TABLE IF NOT EXISTS subscriptions (
    subscription_id VARCHAR PRIMARY KEY,
    customer_id VARCHAR NOT NULL,
    plan_code VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    monthly_amount DECIMAL(10, 2) NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    loaded_batch_id VARCHAR NOT NULL
);

CREATE SEQUENCE IF NOT EXISTS load_audit_run_id START 1;

CREATE TABLE IF NOT EXISTS load_audit (
    run_id BIGINT PRIMARY KEY,
    batch_id VARCHAR NOT NULL,
    extract_from TIMESTAMP NOT NULL,
    extract_to TIMESTAMP NOT NULL,
    staged_rows INTEGER NOT NULL,
    insert_count INTEGER NOT NULL,
    update_count INTEGER NOT NULL,
    delete_count INTEGER NOT NULL,
    unchanged_count INTEGER NOT NULL,
    already_absent_count INTEGER NOT NULL,
    loaded_at TIMESTAMP NOT NULL
);
