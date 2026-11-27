"""Half-open extract windows, and a replay of the same batch that changes nothing."""

from datetime import datetime
from decimal import Decimal


def test_configured_windows_meet_and_do_not_overlap(config):
    first = config.get_batch("2026-01-15")
    second = config.get_batch("2026-01-16")

    assert first.extract_from < first.extract_to
    assert second.extract_from < second.extract_to
    assert first.extract_to == second.extract_from


def test_rows_outside_the_window_never_reach_the_target(loader, config):
    loader.run_batch(config.get_batch("2026-01-15"))
    loader.run_batch(config.get_batch("2026-01-16"))
    present = _target_ids(loader)

    # sub_1090 is before the first window. sub_1091 is exactly at its exclusive end.
    # sub_1099 is exactly at the second window's exclusive end.
    assert "sub_1090" not in present
    assert "sub_1091" not in present
    assert "sub_1099" not in present


def test_inclusive_window_start_is_loaded(loader, config):
    loader.run_batch(config.get_batch("2026-01-15"))
    loader.run_batch(config.get_batch("2026-01-16"))
    row = _subscription(loader, "sub_1008")

    assert row is not None
    assert row[5] == datetime(2026, 1, 16, 0, 0, 0)
    assert row[4] == Decimal("19.00")
    assert row[6] == "2026-01-16"


def test_out_of_window_restatement_does_not_overwrite_the_target(loader, config):
    loader.run_batch(config.get_batch("2026-01-15"))
    loader.run_batch(config.get_batch("2026-01-16"))
    row = _subscription(loader, "sub_1001")

    # The second file restates sub_1001 as enterprise at an older timestamp.
    assert row[2] == "pro"
    assert row[4] == Decimal("49.00")
    assert row[5] == datetime(2026, 1, 15, 10, 0)
    assert row[6] == "2026-01-15"


def test_replaying_a_batch_is_idempotent(loader, config):
    batch = config.get_batch("2026-01-16")
    loader.run_batch(config.get_batch("2026-01-15"))
    loader.run_batch(batch)
    before = loader.conn.execute(
        "SELECT * FROM subscriptions ORDER BY subscription_id"
    ).fetchall()

    replay = loader.run_batch(batch)
    after = loader.conn.execute(
        "SELECT * FROM subscriptions ORDER BY subscription_id"
    ).fetchall()
    audit = loader.latest_audit(batch.batch_id)

    assert replay.insert_count == 0
    assert replay.update_count == 0
    assert replay.delete_count == 0
    assert replay.unchanged_count == 4
    assert replay.already_absent_count == 1
    assert before == after
    assert audit["insert_count"] == 0
    assert audit["update_count"] == 0
    assert audit["delete_count"] == 0
    assert audit["already_absent_count"] == 1


def _target_ids(loader):
    rows = loader.conn.execute(
        "SELECT subscription_id FROM subscriptions ORDER BY subscription_id"
    ).fetchall()
    return [row[0] for row in rows]


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
