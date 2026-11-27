"""Snapshot the target before a load and diff inserted, updated, deleted, and unchanged keys."""

from datetime import datetime
from decimal import Decimal

import pytest

from warehouse_loads.loader import StageValidationError


def test_snapshot_is_the_target_before_the_load(loader, config):
    loader.run_batch(config.get_batch("2026-01-15"))
    loader.run_batch(config.get_batch("2026-01-16"), take_snapshot=True)

    snapshot_ids = _ids(loader, "subscriptions_snapshot")
    assert snapshot_ids == ["sub_1001", "sub_1002", "sub_1003", "sub_1004", "sub_1005"]

    snapshot_plan, snapshot_amount = loader.conn.execute(
        """
        SELECT plan_code, monthly_amount
        FROM subscriptions_snapshot
        WHERE subscription_id = 'sub_1002'
        """
    ).fetchone()
    current_plan, current_amount, current_batch = loader.conn.execute(
        """
        SELECT plan_code, monthly_amount, loaded_batch_id
        FROM subscriptions
        WHERE subscription_id = 'sub_1002'
        """
    ).fetchone()

    assert snapshot_plan == "basic"
    assert snapshot_amount == Decimal("19.00")
    assert current_plan == "pro"
    assert current_amount == Decimal("49.00")
    assert current_batch == "2026-01-16"


def test_snapshot_diff_classifies_every_key(loader, config):
    loader.run_batch(config.get_batch("2026-01-15"))
    loader.run_batch(config.get_batch("2026-01-16"), take_snapshot=True)

    diff = loader.snapshot_diff()

    assert diff["inserted"] == ["sub_1006", "sub_1007", "sub_1008"]
    assert diff["deleted"] == ["sub_1005"]
    assert diff["updated"] == ["sub_1002"]
    assert diff["unchanged"] == ["sub_1001", "sub_1003", "sub_1004"]
    assert sum(len(keys) for keys in diff.values()) == 8


def test_unchanged_keys_keep_the_pre_load_business_values(loader, config):
    loader.run_batch(config.get_batch("2026-01-15"))
    loader.run_batch(config.get_batch("2026-01-16"), take_snapshot=True)

    rows = loader.conn.execute(
        """
        SELECT
            cur.subscription_id,
            cur.plan_code,
            cur.status,
            cur.monthly_amount,
            cur.updated_at,
            cur.loaded_batch_id
        FROM subscriptions AS cur
        JOIN subscriptions_snapshot AS snap
            ON snap.subscription_id = cur.subscription_id
        WHERE cur.subscription_id IN ('sub_1001', 'sub_1003', 'sub_1004')
          AND cur.customer_id = snap.customer_id
          AND cur.plan_code = snap.plan_code
          AND cur.status = snap.status
          AND cur.monthly_amount = snap.monthly_amount
          AND cur.updated_at = snap.updated_at
          AND cur.loaded_batch_id = snap.loaded_batch_id
        ORDER BY cur.subscription_id
        """
    ).fetchall()

    assert [row[0] for row in rows] == ["sub_1001", "sub_1003", "sub_1004"]
    sub_1003 = next(row for row in rows if row[0] == "sub_1003")
    assert sub_1003[3] == Decimal("59.00")
    assert sub_1003[4] == datetime(2026, 1, 15, 12, 30)


def test_snapshot_diff_requires_a_snapshot(loader):
    with pytest.raises(StageValidationError, match="snapshot"):
        loader.snapshot_diff()


def _ids(loader, table):
    rows = loader.conn.execute(
        f"SELECT subscription_id FROM {table} ORDER BY subscription_id"
    ).fetchall()
    return [row[0] for row in rows]
