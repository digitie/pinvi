"""좌표·날짜 → 해·달 출몰(Asia/Seoul) 계산 — `astral` (2026-11-16 소유자 요청 18, 11-17 달 출몰 이관).

일출·일몰·월출·월몰은 좌표와 날짜만 있으면 결정적으로 계산되므로 응답을 만들 때 바로 계산한다 — 외부 호출·키·
ETL 대기·저장 행이 없다. 종전 KASI 출몰시각 ETL(`pinvi_trip_day_rise_sets`)과 그 표(`trip_day_rise_sets`·
`trip_poi_rise_sets`)는 0109에서 은퇴했다(POI 행 8,966건은 채우는 job이 없어 늘 `pending_fetch`였다).

정확도: 해는 KASI 고시값과 분 단위로 맞는다(표준 대기차 34분각·태양 반지름 16분각, 고도 0 m — 산 위·해안 절벽의
지형 효과는 반영하지 않는다). 달은 astral의 Meeus 근사라 몇 분 차이가 날 수 있다. 달은 하루에 뜨거나 지지 않는
날이 있어(약 25시간 주기) 그날 값이 없으면 None이다.

응답 셰입은 `PoiRiseSetResponse`다(`status`·`sunrise_at`·`sunset_at`·`moonrise_at`·`moonset_at`·…). 계산값이므로
`fetched_at`은 비운다.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final, Protocol
from zoneinfo import ZoneInfo

from astral import Observer
from astral.moon import riseset as moon_riseset
from astral.sun import sunrise, sunset

from app.services.kasi import extract_feature_coordinates

SEOUL: Final = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True, slots=True)
class SunTimes:
    sunrise_at: datetime | None
    sunset_at: datetime | None
    moonrise_at: datetime | None = None
    moonset_at: datetime | None = None


def compute_sun_times(*, longitude: float, latitude: float, on: date) -> SunTimes:
    """그 날짜(KST 민간일)의 해·달 출몰. 그날 일어나지 않는 사건(극야·백야, 달이 안 뜨는 날)은 None이다."""
    observer = Observer(latitude=latitude, longitude=longitude)
    return SunTimes(
        sunrise_at=_safe(lambda: sunrise(observer, on, tzinfo=SEOUL)),
        sunset_at=_safe(lambda: sunset(observer, on, tzinfo=SEOUL)),
        moonrise_at=_round(moon[0]) if (moon := _moon_events(observer, on)) else None,
        moonset_at=_round(moon[1]) if moon else None,
    )


def _moon_events(observer: Observer, on: date) -> tuple[datetime | None, datetime | None]:
    """KST 민간일 `on`의 (월출, 월몰). 그날 사건이 없으면 그 자리는 None.

    `astral.moon.moonrise/moonset(tzinfo=KST)`은 **UTC 날짜**의 사건만 구한 뒤 옮겨 보므로, KST 오전 9시 전 사건이
    전날 UTC에 떨어지는 날(예: 서울 2026-05-06 월몰 08시대)에 "그날 지지 않는다"고 잘못 답한다. 그래서 KST 날짜와
    겹치는 UTC 사흘(전날·당일·다음날)의 사건을 모두 모아 KST 날짜가 같은 첫 사건을 고른다.
    """
    rises: list[datetime] = []
    sets: list[datetime] = []
    for delta in (-1, 0, 1):
        try:
            rise, set_ = moon_riseset(on + timedelta(days=delta), observer)
        except ValueError:
            continue
        rises += [rise] if rise is not None else []
        sets += [set_] if set_ is not None else []

    def first_on_day(events: list[datetime]) -> datetime | None:
        local = sorted(event.astimezone(SEOUL) for event in events)
        return next((event for event in local if event.date() == on), None)

    return first_on_day(rises), first_on_day(sets)


def _safe(compute: Callable[[], datetime]) -> datetime | None:
    try:
        value = compute()
    except ValueError:  # 극야·백야 — 한국 좌표에서는 일어나지 않지만 좌표 입력은 외부에서 온다.
        return None
    return _round(value)


def _round(value: datetime | None) -> datetime | None:
    # 분 단위로 반올림한다 — 화면은 HH:MM이고 KASI 고시값도 분 반올림이다(05:10:41 → 05:11).
    if value is None:
        return None
    return (value + timedelta(seconds=30)).replace(second=0, microsecond=0)


def sun_rise_set_dict(
    *,
    locdate: date | None,
    coord: tuple[float, float] | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """`PoiRiseSetResponse` 셰입. 날짜가 없으면 `pending_date`, 좌표가 없으면 `pending_coord`.

    `coord`는 `(lon, lat)`(`services.kasi.extract_feature_coordinates`와 같은 순서)다.
    """
    computed_at = now or datetime.now(UTC)
    base: dict[str, Any] = {
        "locdate": locdate,
        "sunrise_at": None,
        "sunset_at": None,
        "moonrise_at": None,
        "moonset_at": None,
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
        "moonrise_at": times.moonrise_at,
        "moonset_at": times.moonset_at,
    }


class _SnapshotPoi(Protocol):
    attachment_id: uuid.UUID
    feature_snapshot: Any


@dataclass(frozen=True, slots=True)
class DayReference:
    longitude: float
    latitude: float
    reference_poi_id: uuid.UUID
    reference_label: str


def snapshot_coord(snapshot: Any) -> tuple[float, float] | None:
    """POI feature snapshot의 `(lon, lat)`. snapshot이 dict가 아니면 None."""
    return extract_feature_coordinates(snapshot) if isinstance(snapshot, Mapping) else None


def resolve_day_reference(pois: Sequence[_SnapshotPoi]) -> DayReference | None:
    """일자 기준 좌표 — 좌표 있는 POI들의 centroid, 대표(라벨)는 그중 첫 POI. 좌표 있는 POI가 없으면 None.

    `pois`는 non-deleted, (created_at, attachment_id) 오름차순 정렬 가정(대표가 결정적이다).
    """
    with_coord = [(poi, coord) for poi in pois if (coord := snapshot_coord(poi.feature_snapshot))]
    if not with_coord:
        return None
    lon = sum(coord[0] for _, coord in with_coord) / len(with_coord)
    lat = sum(coord[1] for _, coord in with_coord) / len(with_coord)
    rep = with_coord[0][0]
    rep_snapshot = rep.feature_snapshot if isinstance(rep.feature_snapshot, Mapping) else {}
    label = rep_snapshot.get("name") or rep_snapshot.get("title") or "장소"
    return DayReference(
        longitude=lon,
        latitude=lat,
        reference_poi_id=rep.attachment_id,
        reference_label=str(label),
    )
