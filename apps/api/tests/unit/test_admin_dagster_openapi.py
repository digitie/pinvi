"""Admin Dagster의 nullable count/tick 계약은 export와 같이 바뀐다."""

import json
from pathlib import Path

from app.main import app


def test_admin_dagster_export_matches_actual_openapi() -> None:
    root = Path(__file__).resolve().parents[4]
    exported = json.loads((root / "docs/api/admin-dagster-openapi.json").read_text())
    actual = app.openapi()["components"]["schemas"]
    for name, schema in exported["components"]["schemas"].items():
        assert actual[name] == schema, name
    assert "AdminPinviEtlSummary" in exported["components"]["schemas"]
    assert "AdminDagsterTickSummary" in exported["components"]["schemas"]
