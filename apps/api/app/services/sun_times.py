"""좌표·날짜 → 일출·일몰(Asia/Seoul) 계산 — `astral` (2026-11-16 소유자 요청 18).

종전에는 KASI 출몰시각 API를 ETL(`pinvi_trip_day_rise_sets`, 20분 주기)이 채운 행만 보였다. 그래서 일자는
첫 적재까지 "준비 중"이었고, POI 단위 행(`trip_poi_rise_sets`)은 채우는 job이 없어 늘 `pending_fetch`였다
(2026-11-16 prod: 8,966행 전부). 일출·일몰은 좌표와 날짜만 있으면 결정적으로 계산되므로 응답을 만들 때 바로
계산한다 — 외부 호출·키·대기가 없다. 정확도는 KASI 고시값과 1~2분 안이다(표준 대기차 34분각·태양 반지름 16분각,
고도 0 m 기준 — 산 위·해안 절벽의 지형 효과는 반영하지 않는다).

응답 셰입은 그대로 `PoiRiseSetResponse`다(`status`·`sunrise_at`·`sunset_at`·…). 계산값이므로 `fetched_at`은
비우고, 달 출몰은 KASI 행이 같은 날짜로 성공해 있을 때만 그 값을 싣는다(astral 달 계산은 쓰지 않는다).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final
from zoneinfo import ZoneInfo

from astral import Observer
from astral.sun import sunrise, sunset

SEOUL: Final = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True, slots=True)
class SunTimes:
    sunrise_at: datetime | None
    sunset_at: datetime | None


def compute_sun_times(*, longitude: float, latitude: float, on: date) -> SunTimes:
    """그 날짜(KST 민간일)의 일출·일몰. 해가 뜨지(지지) 않는 위도면 그 값만 None이다."""
    observer = Observer(latitude=latitude, longitude=longitude)
    return SunTimes(
        sunrise_at=_safe(lambda: sunrise(observer, on, tzinfo=SEOUL)),
        sunset_at=_safe(lambda: sunset(observer, on, tzinfo=SEOUL)),
    )


def _safe(compute: Callable[[], datetime]) -> datetime | None:
    try:
        value = compute()
    except ValueError:  # 극야·백야 — 한국 좌표에서는 일어나지 않지만 좌표 입력은 외부에서 온다.
        return None
    # 분 단위로 반올림한다 — 화면은 HH:MM이고 KASI 고시값도 분 반올림이다(05:10:41 → 05:11).
    return (value + timedelta(seconds=30)).replace(second=0, microsecond=0)


def sun_rise_set_dict(
    *,
    locdate: date | None,
    coord: tuple[float, float] | None,
    moon: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """`PoiRiseSetResponse` 셰입. 날짜가 없으면 `pending_date`, 좌표가 없으면 `pending_coord`.

    `coord`는 `(lon, lat)`(`services.kasi.extract_feature_coordinates`와 같은 순서)다. `moon`은 같은 날짜로
    성공한 KASI 행의 `moonrise_at`·`moonset_at`(없으면 None)이다.
    """
    computed_at = now or datetime.now(UTC)
    base: dict[str, Any] = {
        "locdate": locdate,
        "sunrise_at": None,
        "sunset_at": None,
        "moonrise_at": (moon or {}).get("moonrise_at"),
        "moonset_at": (moon or {}).get("moonset_at"),
        "fetched_at": None,
        "updated_at": computed_at,
    }
    if locdate is None:
        return {**base, "status": "pending_date"}
    if coord is None:
        return {**base, "status": "pending_coord"}
    times = compute_sun_times(longitude=coord[0], latitude=coord[1], on=locdate)
    if times.sunrise_at is None and times.sunset_at is None:
        return {**base, "status": "failed"}
    return {
        **base,
        "status": "success",
        "sunrise_at": times.sunrise_at,
        "sunset_at": times.sunset_at,
    }
