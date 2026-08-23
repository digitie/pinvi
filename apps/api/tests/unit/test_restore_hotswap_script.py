from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts/restore-hotswap.sh"


def test_restore_hotswap_rejects_session_and_lock_control_in_dump_sql() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "pg_advisory_(lock|unlock)" in source
    assert "pg_(cancel|terminate)_backend" in source
    assert "discard[[:space:]]+all" in source
    assert "advisory_lock_sql_guard" in source
    assert source.count("advisory_lock_sql_guard") >= 6
