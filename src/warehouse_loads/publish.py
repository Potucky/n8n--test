"""Assemble the GitHub Pages site from the pytest HTML report."""

from __future__ import annotations

import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = REPO_ROOT / "reports" / "report.html"
DEFAULT_INDEX = REPO_ROOT / "reporting" / "index.html"
DEFAULT_SITE = REPO_ROOT / "site"


def build_site(
    report_path: Path = DEFAULT_REPORT,
    index_path: Path = DEFAULT_INDEX,
    site_dir: Path = DEFAULT_SITE,
) -> Path:
    """Copy the report and the index page into ``site_dir``."""

    if not report_path.is_file():
        raise FileNotFoundError(f"Missing HTML report: {report_path}")
    if not index_path.is_file():
        raise FileNotFoundError(f"Missing Pages index: {index_path}")
    site_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(report_path, site_dir / "report.html")
    shutil.copyfile(index_path, site_dir / "index.html")
    return site_dir


def main() -> None:
    site_dir = build_site()
    print(f"Wrote {site_dir / 'index.html'} and {site_dir / 'report.html'}")


if __name__ == "__main__":
    main()
