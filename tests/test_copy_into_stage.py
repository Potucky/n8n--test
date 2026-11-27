"""COPY-style loads: window filter, natural-key dedupe, CSV and JSON."""

import csv
import json
from datetime import datetime
from decimal import Decimal

import pytest

from warehouse_loads.config import LoadBatch
from warehouse_loads.loader import StageValidationError


def test_csv_batch_keeps_only_rows_inside_the_window(loader, config):
    batch = config.get_batch("2026-01-15")
    with batch.path.open(encoding="utf-8", newline="") as handle:
        file_rows = list(csv.DictReader(handle))

    staged = loader.copy_into_stage(batch)
    staged_ids = _staged_ids(loader)

    assert len(file_rows) == 8
    assert staged == 5
    assert staged_ids == ["sub_1001", "sub_1002", "sub_1003", "sub_1004", "sub_1005"]
    assert "sub_1090" not in staged_ids
    assert "sub_1091" not in staged_ids


def test_duplicate_natural_key_in_the_file_keeps_the_latest_row(loader, config):
    loader.copy_into_stage(config.get_batch("2026-01-15"))
    amount, updated_at, extract_seq = loader.conn.execute(
        """
        SELECT monthly_amount, updated_at, extract_seq
        FROM stg_subscriptions
        WHERE subscription_id = 'sub_1003'
        """
    ).fetchone()

    assert amount == Decimal("59.00")
    assert updated_at == datetime(2026, 1, 15, 12, 30)
    assert extract_seq == 2
    assert _count(loader, "stg_subscriptions", "sub_1003") == 1


def test_json_batch_stages_the_window_and_dedupes(loader, config):
    batch = config.get_batch("2026-01-16")
    file_rows = json.loads(batch.path.read_text(encoding="utf-8"))

    staged = loader.copy_into_stage(batch)
    staged_ids = _staged_ids(loader)
    amount = loader.conn.execute(
        """
        SELECT monthly_amount
        FROM stg_subscriptions
        WHERE subscription_id = 'sub_1006'
        """
    ).fetchone()[0]

    assert len(file_rows) == 8
    assert staged == 5
    assert staged_ids == ["sub_1002", "sub_1005", "sub_1006", "sub_1007", "sub_1008"]
    assert amount == Decimal("29.00")
    assert "sub_1001" not in staged_ids
    assert "sub_1099" not in staged_ids


def test_stage_is_replaced_on_the_next_batch(loader, config):
    loader.copy_into_stage(config.get_batch("2026-01-15"))
    loader.copy_into_stage(config.get_batch("2026-01-16"))

    staged_ids = _staged_ids(loader)
    assert "sub_1004" not in staged_ids
    assert staged_ids == ["sub_1002", "sub_1005", "sub_1006", "sub_1007", "sub_1008"]


def test_unknown_change_type_is_rejected_before_merge(loader, tmp_path):
    source = tmp_path / "bad.csv"
    source.write_text(
        "subscription_id,customer_id,plan_code,status,monthly_amount,updated_at,change_type,extract_seq\n"
        "sub_2001,cust_01,pro,active,49.00,2026-01-15 10:00:00,SCRUB,1\n",
        encoding="utf-8",
    )
    batch = _temp_batch(source)

    with pytest.raises(StageValidationError, match="change_type"):
        loader.run_batch(batch)

    assert _target_count(loader) == 0
    assert _audit_count(loader) == 0


def test_blank_natural_key_is_rejected_before_merge(loader, tmp_path):
    source = tmp_path / "blank.csv"
    source.write_text(
        "subscription_id,customer_id,plan_code,status,monthly_amount,updated_at,change_type,extract_seq\n"
        ",cust_01,pro,active,49.00,2026-01-15 10:00:00,UPSERT,1\n",
        encoding="utf-8",
    )
    batch = _temp_batch(source)

    with pytest.raises(StageValidationError, match="subscription_id"):
        loader.run_batch(batch)

    assert _target_count(loader) == 0
    assert _audit_count(loader) == 0


def _temp_batch(path):
    return LoadBatch(
        batch_id="bad-batch",
        path=path,
        extract_from=datetime(2026, 1, 15, 0, 0, 0),
        extract_to=datetime(2026, 1, 16, 0, 0, 0),
    )


def _staged_ids(loader):
    rows = loader.conn.execute(
        "SELECT subscription_id FROM stg_subscriptions ORDER BY subscription_id"
    ).fetchall()
    return [row[0] for row in rows]


def _count(loader, table, subscription_id):
    return loader.conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE subscription_id = ?",
        [subscription_id],
    ).fetchone()[0]


def _target_count(loader):
    return loader.conn.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0]


def _audit_count(loader):
    return loader.conn.execute("SELECT COUNT(*) FROM load_audit").fetchone()[0]
