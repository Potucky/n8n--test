"""Fresh in-memory warehouse for every test. No shared file and no sleeps."""

import duckdb
import pytest

from warehouse_loads.config import load_config
from warehouse_loads.loader import WarehouseLoader


def pytest_html_report_title(report):
    report.title = "Snowflake-style SQL tests"


def pytest_metadata(metadata, config):
    metadata.pop("Packages", None)
    metadata.pop("Plugins", None)
    metadata["DuckDB"] = duckdb.__version__
    metadata["Warehouse"] = "in-memory DuckDB, Snowflake load patterns"


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def loader():
    conn = duckdb.connect(":memory:")
    warehouse = WarehouseLoader(conn)
    warehouse.apply_ddl()
    yield warehouse
    conn.close()
