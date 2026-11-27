"""The Pages site is the HTML report plus an index page that links to it."""

from warehouse_loads.publish import build_site


def test_build_site_copies_the_report_and_the_index(tmp_path):
    report = tmp_path / "report.html"
    index = tmp_path / "index.html"
    site = tmp_path / "site"
    report.write_text("<html><body>report</body></html>", encoding="utf-8")
    index.write_text('<html><body><a href="report.html">report</a></body></html>', encoding="utf-8")

    build_site(report, index, site)

    assert (site / "report.html").read_text(encoding="utf-8") == report.read_text(encoding="utf-8")
    assert 'href="report.html"' in (site / "index.html").read_text(encoding="utf-8")
