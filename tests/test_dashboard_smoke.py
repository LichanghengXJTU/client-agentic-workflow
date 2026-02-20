from __future__ import annotations


def test_dashboard_module_importable() -> None:
    import pytest

    pytest.importorskip("streamlit")
    import dashboard.app as app

    assert callable(app.main)
