"""The subscription grain is subscription_id, including after a file repeats a key."""


def test_no_duplicate_natural_keys_after_both_batches(loader, config):
    loader.run_batch(config.get_batch("2026-01-15"))
    loader.run_batch(config.get_batch("2026-01-16"))

    duplicates = loader.conn.execute(
        """
        SELECT subscription_id, COUNT(*) AS n
        FROM subscriptions
        GROUP BY subscription_id
        HAVING COUNT(*) > 1
        ORDER BY subscription_id
        """
    ).fetchall()
    distinct_count, row_count = loader.conn.execute(
        """
        SELECT COUNT(DISTINCT subscription_id), COUNT(*)
        FROM subscriptions
        """
    ).fetchone()

    assert duplicates == []
    assert distinct_count == row_count == 7


def test_repeated_source_key_lands_once(loader, config):
    loader.run_batch(config.get_batch("2026-01-15"))
    loader.run_batch(config.get_batch("2026-01-16"))

    for subscription_id in ("sub_1003", "sub_1006"):
        found = loader.conn.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE subscription_id = ?",
            [subscription_id],
        ).fetchone()[0]
        assert found == 1
