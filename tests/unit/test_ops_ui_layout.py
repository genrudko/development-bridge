from pathlib import Path


ROOT = Path(__file__).parents[2]
STYLE = ROOT / "app" / "ops" / "static" / "style.css"
DASHBOARD = ROOT / "app" / "ops" / "templates" / "dashboard.html"


def test_operator_dashboard_desktop_layout_uses_available_width():
    css = STYLE.read_text(encoding="utf-8")

    assert "max-width: 1800px" in css
    assert "grid-template-columns: minmax(0, 1fr)" in css


def test_operator_dashboard_tables_scroll_instead_of_crushing_columns():
    css = STYLE.read_text(encoding="utf-8")
    dashboard = DASHBOARD.read_text(encoding="utf-8")

    assert "min-width: 960px" in css
    assert 'class="card-body table-scroll"' in dashboard
    assert ".card-body.table-scroll" in css
    assert "overflow-x: auto" in css
    assert "white-space: nowrap" in css
    assert "overflow-wrap: anywhere" in css


def test_operator_dashboard_navigation_and_header_are_responsive():
    css = STYLE.read_text(encoding="utf-8")

    assert "nav.tabs" in css
    assert "overflow-x: auto" in css
    assert "flex-wrap: wrap" in css
    assert "@media (max-width: 900px)" in css
    assert "@media (max-width: 600px)" in css
