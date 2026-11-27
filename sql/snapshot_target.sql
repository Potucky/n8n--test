-- Full copy of the target immediately before a load.
-- This is the local stand-in for Snowflake zero-copy CLONE and for
-- SELECT ... FROM subscriptions AT (TIMESTAMP => <before the load>).
-- DuckDB does not keep table history, so the snapshot is an ordinary table
-- and it stays as it was while later statements change subscriptions.

CREATE OR REPLACE TABLE subscriptions_snapshot AS
SELECT * FROM subscriptions;
