"""reconciliation 술어의 3값 논리와 canonical 축 주조 금지를 결박한다."""

from __future__ import annotations

import uuid

import pytest

from app.clients.kor_travel_map_feature_reference_reconciliation import FeatureReference
from app.services.feature_reference_reconciliation import (
    _rebound_uuid,
    _row_is_reconcilable,
)

_REF_ID = "f_place_x"
_REF_UUID = uuid.UUID("11111111-1111-4111-8111-111111111111")
_OTHER_UUID = uuid.UUID("22222222-2222-4222-8222-222222222222")
_NEW_UUID = uuid.UUID("33333333-3333-4333-8333-333333333333")


def _reference() -> FeatureReference:
    return FeatureReference.model_validate(
        {"feature_id": _REF_ID, "feature_uuid": str(_REF_UUID), "row_revision": 2}
    )


@pytest.mark.parametrize(
    ("feature_id", "feature_uuid", "expected"),
    [
        # canonical 축이 맞으면 텍스트가 무엇이든 같은 feature다(Map ADR-068).
        (_REF_ID, _REF_UUID, True),
        ("f_legacy_alias", _REF_UUID, True),
        (None, _REF_UUID, True),
        # canonical 축이 비어 있으면 legacy 축으로 판정한다.
        (_REF_ID, None, True),
        ("f_other", None, False),
        (None, None, False),
        # canonical 축이 **다른** feature를 가리키면 진짜 모순이다.
        (_REF_ID, _OTHER_UUID, False),
        ("f_other", _OTHER_UUID, False),
        (None, _OTHER_UUID, False),
    ],
)
def test_reconcilable_partition_covers_the_three_valued_space(
    feature_id: str | None, feature_uuid: uuid.UUID | None, expected: bool
) -> None:
    assert _row_is_reconcilable(feature_id, feature_uuid, _reference()) is expected


def test_rebind_never_mints_a_canonical_binding() -> None:
    """canonical 축이 비어 있던 행에 UUID를 새로 새기면 안 된다.

    그 행이 old feature를 가리킨다는 유일한 근거는 길이만 검증되는 client
    자유 문자열이다. 미검증 값을 근거로 정본화하면 저장소가 이미 적대 리뷰로
    정한 불변식("검증된 alias map만 채운다")이 깨진다."""

    replacement = FeatureReference.model_validate(
        {"feature_id": "f_new", "feature_uuid": str(_NEW_UUID), "row_revision": 1}
    )
    # 비어 있던 축은 계속 비어 있다 — 정본화 권한은 cutover에 남는다.
    assert _rebound_uuid(None, replacement) is None
    # 이미 검증된 결박은 replacement로 이동한다.
    assert _rebound_uuid(_REF_UUID, replacement) == _NEW_UUID
    # detach는 두 경우 모두 NULL이다.
    assert _rebound_uuid(None, None) is None
    assert _rebound_uuid(_REF_UUID, None) is None


def test_pair_condition_is_derived_not_a_third_declaration() -> None:
    """lock 술어는 두 구성 술어에서 파생돼야 한다.

    접힌 형태를 직접 쓰면 세 번째 독립 선언이 생기고, 구성 술어가 바뀔 때
    lock 술어만 조용히 좁아진다 — 결과는 눈에 보이는 block이 아니라 행이
    아예 안 잡히는 무성 누락이다."""

    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "feature_reference_reconciliation.py"
    ).read_text(encoding="utf-8")
    body = source[source.index("def _pair_condition(") :]
    body = body[: body.index("\ndef ")]
    assert "_reconcilable_condition(id_column, uuid_column, reference)" in body
    assert "_conflicting_condition(id_column, uuid_column, reference)" in body
