"""Viewport bbox 파싱 + 지도 zoom 범위 — `/features/in-bounds`와 `/weather/markers-in-bounds`
공용(T-368).

`bbox`/`zoom` 파라미터 셰입은 두 endpoint가 동일하다("현재 지도 화면"이라는 같은
개념을 가리키므로) — 파싱과 범위 상수를 여기 하나로 둔다.
"""

from __future__ import annotations

import math

from fastapi import HTTPException, status

from app.schemas.feature import BBox

#: 지도 zoom 유효 범위 — 프론트 `clampZoom`(`apps/web/lib/featureBounds.ts`)과 정합.
MIN_ZOOM: int = 5
MAX_ZOOM: int = 19


def parse_bbox(bbox_str: str) -> BBox:
    """`lng_min,lat_min,lng_max,lat_max` → `BBox`."""
    nums = parse_bbox_numbers(bbox_str)
    return BBox(lng_min=nums[0], lat_min=nums[1], lng_max=nums[2], lat_max=nums[3])


def parse_bbox_numbers(bbox_str: str) -> tuple[float, float, float, float]:
    """`lng_min,lat_min,lng_max,lat_max` → 유한한 float 4개(형식 오류는 400). 범위 검사는 호출부 몫."""
    parts = bbox_str.split(",")
    if len(parts) != 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "bbox 는 'lng_min,lat_min,lng_max,lat_max' 형식이어야 합니다.",
            },
        )
    try:
        nums = [float(p) for p in parts]
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "VALIDATION_ERROR", "message": "bbox 숫자 변환 실패."},
        ) from exc
    if not all(math.isfinite(n) for n in nums):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "VALIDATION_ERROR", "message": "bbox 값은 유한한 숫자여야 합니다."},
        )
    return (nums[0], nums[1], nums[2], nums[3])
