"""vendored Map admin OpenAPI 스냅샷의 단일 핀.

admin/ops 두 계약 게이트가 같은 스냅샷 파일(`tests/contract/
kor-travel-map-openapi-admin.json`)을 각자 리터럴로 byte-핀하다가, 2026-09-01
재핀에서 절반만 갱신돼 CI가 깨졌다(적대 리뷰 적발 — 핀 4개가 2모듈에 분산).
핀은 이 모듈 하나가 소유하고 각 게이트는 여기서 import한다. 재핀 시 바꿀 곳은
스냅샷 바이트 + 이 모듈 + `test_kor_travel_map_admin_contract.py`의 이중 핀
리터럴(리뷰 강제 장치, 단 한 곳)뿐이다.
"""

from __future__ import annotations

from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parent.parent / "contract" / "kor-travel-map-openapi-admin.json"
UPSTREAM_COMMIT = "72f62c4c5ee0f9461a257c1da1d14dd90254978e"
SNAPSHOT_SHA256 = "6419c1332ba95ab03b8ec794d9d2e7c2a6f2e6da012d23118708e4e4bc5343bb"
