"""Batch windows come from config/warehouse.yaml. Env vars override the file."""

from pathlib import Path

from warehouse_loads.config import load_config


def test_default_config_points_at_the_sample_extracts(config):
    assert config.database_path == ":memory:"
    csv_batch = config.get_batch("2026-01-15")
    json_batch = config.get_batch("2026-01-16")
    assert csv_batch.path.name == "subscriptions_20260115.csv"
    assert json_batch.path.suffix == ".json"
    assert csv_batch.path.is_file()
    assert json_batch.path.is_file()


def test_environment_overrides_database_path_and_config_file(monkeypatch, tmp_path):
    config_path = tmp_path / "warehouse.yaml"
    config_path.write_text(
        "\n".join(
            [
                'database_path: ":memory:"',
                "loads:",
                '  - batch_id: "day-1"',
                f"    path: {tmp_path / 'extract.csv'}",
                '    extract_from: "2026-01-15 00:00:00"',
                '    extract_to: "2026-01-16 00:00:00"',
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "extract.csv").write_text("subscription_id\n", encoding="utf-8")
    database_path = tmp_path / "local-only.duckdb"
    monkeypatch.setenv("WAREHOUSE_CONFIG", str(config_path))
    monkeypatch.setenv("WAREHOUSE_DB_PATH", str(database_path))

    loaded = load_config()

    assert loaded.database_path == str(database_path)
    assert loaded.get_batch("day-1").path == (tmp_path / "extract.csv").resolve()
    assert Path(loaded.database_path).name == "local-only.duckdb"
