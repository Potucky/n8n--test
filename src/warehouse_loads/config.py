"""Load batch windows from YAML, with optional environment overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "warehouse.yaml"
_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class LoadBatch:
    """One extract file and the half-open window it is allowed to load."""

    batch_id: str
    path: Path
    extract_from: datetime
    extract_to: datetime


@dataclass(frozen=True)
class WarehouseConfig:
    database_path: str
    loads: tuple[LoadBatch, ...]
    config_path: Path

    def get_batch(self, batch_id: str) -> LoadBatch:
        for batch in self.loads:
            if batch.batch_id == batch_id:
                return batch
        known = ", ".join(batch.batch_id for batch in self.loads)
        raise KeyError(f"Unknown batch_id {batch_id!r}. Known batches: {known}")


def load_config(path: Path | None = None) -> WarehouseConfig:
    """Read warehouse.yaml. WAREHOUSE_CONFIG and WAREHOUSE_DB_PATH override it."""

    if path is not None:
        config_path = Path(path)
    else:
        config_path = Path(os.environ.get("WAREHOUSE_CONFIG", DEFAULT_CONFIG_PATH))
    config_path = config_path.resolve()
    repo_root = config_path.parent.parent

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{config_path} must contain a mapping")

    database_path = os.environ.get("WAREHOUSE_DB_PATH", raw.get("database_path", ":memory:"))
    loads_raw = raw.get("loads")
    if not isinstance(loads_raw, list) or not loads_raw:
        raise ValueError(f"{config_path} needs a non-empty loads list")

    loads = tuple(_parse_batch(item, repo_root, config_path) for item in loads_raw)
    _require_unique_batch_ids(loads)
    return WarehouseConfig(
        database_path=str(database_path),
        loads=loads,
        config_path=config_path,
    )


def _parse_batch(item: object, repo_root: Path, config_path: Path) -> LoadBatch:
    if not isinstance(item, dict):
        raise ValueError(f"Each load in {config_path} must be a mapping")
    batch_id = str(item["batch_id"])
    file_path = Path(str(item["path"]))
    if not file_path.is_absolute():
        file_path = repo_root / file_path
    extract_from = _as_naive_datetime(item["extract_from"], "extract_from")
    extract_to = _as_naive_datetime(item["extract_to"], "extract_to")
    if extract_from >= extract_to:
        raise ValueError(
            f"Batch {batch_id} has extract_from >= extract_to ({extract_from} .. {extract_to})"
        )
    return LoadBatch(
        batch_id=batch_id,
        path=file_path,
        extract_from=extract_from,
        extract_to=extract_to,
    )


def _as_naive_datetime(value: object, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.strptime(value, _TIMESTAMP_FORMAT)
    else:
        raise TypeError(f"{field_name} must be a timestamp string, got {type(value).__name__}")
    if parsed.tzinfo is not None:
        raise ValueError(f"{field_name} must be a naive UTC wall time, got {parsed}")
    return parsed


def _require_unique_batch_ids(loads: tuple[LoadBatch, ...]) -> None:
    seen: set[str] = set()
    for batch in loads:
        if batch.batch_id in seen:
            raise ValueError(f"Duplicate batch_id {batch.batch_id!r}")
        seen.add(batch.batch_id)
