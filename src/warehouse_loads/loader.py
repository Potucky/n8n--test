"""Stage a file, MERGE it into the subscription table, and snapshot the before-image.

DuckDB is the warehouse. The steps follow a Snowflake load, with two stand-ins:

* ``read_csv_auto`` / ``read_json_auto`` stand in for COPY INTO a stage table.
* ``subscriptions_snapshot`` is a full table copy standing in for
  ``CREATE TABLE ... CLONE`` or ``AT (TIMESTAMP => ...)``. DuckDB does not
  keep time-travel history.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from warehouse_loads.config import LoadBatch

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"

# Only these readers are substituted into the COPY statement.
_READERS = {
    ".csv": "read_csv_auto",
    ".json": "read_json_auto",
}

_COUNT_FIELDS = (
    "insert",
    "update",
    "delete",
    "unchanged",
    "already_absent",
)


class StageValidationError(ValueError):
    """Staged rows failed a gate that must pass before MERGE."""


@dataclass(frozen=True)
class MergeCounts:
    """Insert, update, delete, and no-op counts for one staged batch."""

    insert_count: int = 0
    update_count: int = 0
    delete_count: int = 0
    unchanged_count: int = 0
    already_absent_count: int = 0

    @property
    def accounted_rows(self) -> int:
        return (
            self.insert_count
            + self.update_count
            + self.delete_count
            + self.unchanged_count
            + self.already_absent_count
        )

    @classmethod
    def from_rows(cls, rows: list[tuple[str, int]]) -> MergeCounts:
        counts = {name: 0 for name in _COUNT_FIELDS}
        for action, n in rows:
            if action not in counts:
                raise StageValidationError(f"Unexpected merge action {action!r}")
            counts[action] = int(n)
        return cls(
            insert_count=counts["insert"],
            update_count=counts["update"],
            delete_count=counts["delete"],
            unchanged_count=counts["unchanged"],
            already_absent_count=counts["already_absent"],
        )


class WarehouseLoader:
    """Run one extract window at a time against an open DuckDB connection."""

    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.conn = conn
        self.clock = clock or _utc_now_naive

    def apply_ddl(self) -> None:
        _execute_script(self.conn, _read_sql("ddl.sql"))

    def run_batch(self, batch: LoadBatch, *, take_snapshot: bool = False) -> MergeCounts:
        """Load one file into stage, then MERGE it into ``subscriptions``.

        When ``take_snapshot`` is set, the target is copied after the stage
        gate passes and before MERGE. A rejected file does not change the target
        and does not write an audit row.
        """

        staged_rows = self.copy_into_stage(batch)
        self.validate_stage()
        if take_snapshot:
            self.snapshot_target()
        counts = self.classify_merge()
        if counts.accounted_rows != staged_rows:
            raise StageValidationError(
                f"Classification covered {counts.accounted_rows} rows, stage has {staged_rows}"
            )
        self.merge_into_target()
        self._write_audit(batch, staged_rows, counts)
        return counts

    def copy_into_stage(self, batch: LoadBatch) -> int:
        """Replace ``stg_subscriptions`` with the rows inside this batch's window."""

        if not batch.path.is_file():
            raise FileNotFoundError(batch.path)
        reader = _reader_for(batch.path)
        sql = _read_sql("copy_into_stage.sql").replace("__READER__", reader)
        self.conn.execute(
            sql,
            {
                "path": str(batch.path),
                "extract_from": batch.extract_from,
                "extract_to": batch.extract_to,
                "batch_id": batch.batch_id,
            },
        )
        return int(self.conn.execute("SELECT COUNT(*) FROM stg_subscriptions").fetchone()[0])

    def validate_stage(self) -> None:
        """Reject a blank natural key or a change_type other than UPSERT or DELETE."""

        blank_keys = int(
            self.conn.execute(
                """
                SELECT COUNT(*)
                FROM stg_subscriptions
                WHERE subscription_id IS NULL OR TRIM(subscription_id) = ''
                """
            ).fetchone()[0]
        )
        bad_types = self.conn.execute(
            """
            SELECT subscription_id, change_type
            FROM stg_subscriptions
            WHERE change_type IS NULL OR change_type NOT IN ('UPSERT', 'DELETE')
            ORDER BY subscription_id
            """
        ).fetchall()
        problems: list[str] = []
        if blank_keys:
            problems.append(f"{blank_keys} staged row(s) with a null or blank subscription_id")
        if bad_types:
            shown = ", ".join(
                f"{key or '<blank>'}={change!r}" for key, change in bad_types[:10]
            )
            problems.append(f"change_type must be UPSERT or DELETE ({shown})")
        if problems:
            raise StageValidationError("; ".join(problems))

    def classify_merge(self) -> MergeCounts:
        rows = self.conn.execute(_read_sql("classify_merge.sql")).fetchall()
        return MergeCounts.from_rows([(str(action), int(n)) for action, n in rows])

    def merge_into_target(self) -> None:
        self.conn.execute(_read_sql("merge_subscriptions.sql")).fetchall()

    def snapshot_target(self) -> None:
        """Copy ``subscriptions`` to ``subscriptions_snapshot``."""

        self.conn.execute(_read_sql("snapshot_target.sql"))

    def snapshot_diff(self) -> dict[str, list[str]]:
        """Group natural keys into inserted, deleted, updated, and unchanged."""

        if not self._table_exists("subscriptions_snapshot"):
            raise StageValidationError("No snapshot. Call snapshot_target() before the load.")
        rows = self.conn.execute(_read_sql("snapshot_diff.sql")).fetchall()
        grouped = {"inserted": [], "deleted": [], "updated": [], "unchanged": []}
        for subscription_id, action in rows:
            if action not in grouped:
                raise StageValidationError(f"Unexpected snapshot action {action!r}")
            grouped[action].append(subscription_id)
        return grouped

    def latest_audit(self, batch_id: str) -> dict[str, object] | None:
        """Return the newest ``load_audit`` row for a batch, or None."""

        result = self.conn.execute(
            """
            SELECT
                run_id,
                batch_id,
                extract_from,
                extract_to,
                staged_rows,
                insert_count,
                update_count,
                delete_count,
                unchanged_count,
                already_absent_count,
                loaded_at
            FROM load_audit
            WHERE batch_id = ?
            ORDER BY run_id DESC
            LIMIT 1
            """,
            [batch_id],
        )
        row = result.fetchone()
        if row is None:
            return None
        columns = [item[0] for item in result.description]
        return dict(zip(columns, row, strict=True))

    def _write_audit(self, batch: LoadBatch, staged_rows: int, counts: MergeCounts) -> None:
        self.conn.execute(
            """
            INSERT INTO load_audit (
                run_id,
                batch_id,
                extract_from,
                extract_to,
                staged_rows,
                insert_count,
                update_count,
                delete_count,
                unchanged_count,
                already_absent_count,
                loaded_at
            )
            VALUES (nextval('load_audit_run_id'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                batch.batch_id,
                batch.extract_from,
                batch.extract_to,
                staged_rows,
                counts.insert_count,
                counts.update_count,
                counts.delete_count,
                counts.unchanged_count,
                counts.already_absent_count,
                self.clock(),
            ],
        )

    def _table_exists(self, table_name: str) -> bool:
        found = self.conn.execute(
            "SELECT COUNT(*) FROM duckdb_tables() WHERE table_name = ?",
            [table_name],
        ).fetchone()[0]
        return int(found) > 0


def _reader_for(path: Path) -> str:
    try:
        return _READERS[path.suffix.lower()]
    except KeyError as exc:
        allowed = ", ".join(sorted(_READERS))
        raise ValueError(f"Unsupported extract format {path.suffix!r}. Use one of: {allowed}") from exc


def _read_sql(name: str) -> str:
    return (SQL_DIR / name).read_text(encoding="utf-8")


def _execute_script(conn: duckdb.DuckDBPyConnection, sql: str) -> None:
    for statement in _statements(sql):
        conn.execute(statement)


def _statements(sql: str) -> list[str]:
    """Split a script on semicolons, ignoring full-line comments."""

    lines = []
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        lines.append(line)
    return [part.strip() for part in "\n".join(lines).split(";") if part.strip()]


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
