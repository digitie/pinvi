"""canonical Map collection을 수용하는 plan 문자열 상한 계약."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.notice import NoticePlanCreate, NoticePlanUpdate


def test_notice_plan_accepts_map_collection_title_and_theme_slug_bounds() -> None:
    created = NoticePlanCreate(
        slug="canonical-map-collection",
        title="가" * 300,
        category="나" * 128,
    )
    patched = NoticePlanUpdate(title="가" * 300, category="나" * 128)

    assert len(created.title) == 300
    assert len(created.category) == 128
    assert len(patched.title or "") == 300
    assert len(patched.category or "") == 128


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"title": "가" * 301}, "title"),
        ({"category": "나" * 129}, "category"),
    ],
)
def test_notice_plan_rejects_values_beyond_map_contract(
    payload: dict[str, str],
    field: str,
) -> None:
    with pytest.raises(ValidationError) as error:
        NoticePlanUpdate(**payload)

    assert field in str(error.value)
