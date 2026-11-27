"""MERGE insert, update, and delete counts, reconciled to the target and to load_audit."""

from datetime import datetime
from decimal import Decimal


def test_first_batch_is_all_inserts(loader, config):
    counts = loader.run_batch(config.get_batch("2026-01-15"))

    assert counts.insert_count == 5
    assert counts.update_count == 0
    assert counts.delete_count == 0
    assert counts.unchanged_count == 0
    assert counts.already_absent_count == 0
    assert _target_count(loader) == 5


def test_second_batch_insert_update_and_delete_counts(loader, config):
    loader.run_batch(config.get_batch("2026-01-15"))
    before = _target_count(loader)

    counts = loader.run_batch(config.get_batch("2026-01-16"))
    after = _target_count(loader)

    assert counts.insert_count == 3
    assert counts.update_count == 1
    assert counts.delete_count == 1
    assert counts.unchanged_count == 0
    assert counts.already_absent_count == 0
    assert counts.accounted_rows == 5
    assert after - before == counts.insert_count - counts.delete_count
    assert after == 7


def test_audit_row_matches_the_merge_counts_and_the_window(loader, config):
    batch = config.get_batch("2026-01-16")
    loader.run_batch(config.get_batch("2026-01-15"))
    counts = loader.run_batch(batch)
    audit = loader.latest_audit(batch.batch_id)

    assert audit is not None
    assert audit["batch_id"] == "2026-01-16"
    assert audit["extract_from"] == datetime(2026, 1, 16, 0, 0, 0)
    assert audit["extract_to"] == datetime(2026, 1, 17, 0, 0, 0)
    assert audit["staged_rows"] == 5
    assert audit["insert_count"] == counts.insert_count == 3
    assert audit["update_count"] == counts.update_count == 1
    assert audit["delete_count"] == counts.delete_count == 1
    assert audit["unchanged_count"] == 0
    assert audit["already_absent_count"] == 0


def test_merged_rows_have_the_expected_business_values(loader, config):
    loader.run_batch(config.get_batch("2026-01-15"))
    loader.run_batch(config.get_batch("2026-01-16"))

    upgraded = _subscription(loader, "sub_1002")
    deduped = _subscription(loader, "sub_1003")
    deleted = _subscription(loader, "sub_1005")
    inserted = _subscription(loader, "sub_1006")

    assert upgraded[2:] == ("pro", "active", Decimal("49.00"), datetime(2026, 1, 16, 9, 0), "2026-01-16")
    assert deduped[2:] == ("pro", "active", Decimal("59.00"), datetime(2026, 1, 15, 12, 30), "2026-01-15")
    assert deleted is None
    assert inserted[2:] == ("basic", "active", Decimal("29.00"), datetime(2026, 1, 16, 11, 30), "2026-01-16")


def _subscription(loader, subscription_id):
    return loader.conn.execute(
        """
        SELECT
            subscription_id,
            customer_id,
            plan_code,
            status,
            monthly_amount,
            updated_at,
            loaded_batch_id
        FROM subscriptions
        WHERE subscription_id = ?
        """,
        [subscription_id],
    ).fetchone()


def _target_count(loader):
    return loader.conn.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0]
