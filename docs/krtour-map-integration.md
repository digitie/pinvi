# krtour-map-integration.md — TripMate가 `python-krtour-map`을 사용하는 방법

본 문서는 TripMate(`apps/api` + `apps/etl`)가 `python-krtour-map`을 import해서
사용하는 표준 패턴이다. ADR-002 (함수 직접 호출) + ADR-003 (schema 책임 분담)
+ ADR-005 (provider 어댑터 wrapper 금지) 기준.

`python-krtour-map` 측의 ADR-022 (`from krtour.map import ...` namespace),
ADR-020 (디버그 UI 별도 패키지), ADR-006 (wrapper 생성 금지)을 함께 참고.

## 1. 개관

```
┌──────────────────────────────────────────────────────────────────┐
│ TripMate (이 저장소)                                              │
│   apps/api/        — FastAPI 라우터 + Admin + Storage             │
│   apps/web/        — Next.js 사용자 UI                            │
│   apps/etl/        — Dagster definitions/jobs/schedules           │
│                                                                  │
│   pip install python-krtour-map                                  │
│   from krtour.map import AsyncKrtourMapClient, Feature, ...      │
└──────────────────────────────────────────────────────────────────┘
                              │ 함수 직접 호출 (HTTP 없음)
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ python-krtour-map (별 저장소, 같은 venv)                          │
│   src/krtour/map/                                                │
└──────────────────────────────────────────────────────────────────┘
```

TripMate ↔ 라이브러리는 같은 Python 프로세스에서 함수 호출만. REST/JSON
직렬화/네트워크 hop 없음 (ADR-002).

## 2. 설치 / 버전 고정

`apps/api/pyproject.toml` 예시:

```toml
[project]
dependencies = [
  "python-krtour-map @ git+https://github.com/digitie/python-krtour-map.git@<sha>",
  # 또는 PyPI 배포 후: "python-krtour-map>=0.2,<0.3"

  # 라이브러리가 함수 인자로 받기만 하는 provider 클라이언트도 TripMate가 직접 의존:
  "python-kraddr-base @ git+https://github.com/digitie/python-kraddr-base.git@<sha>",
  "python-kraddr-geo  @ git+https://github.com/digitie/python-kraddr-geo.git@<sha>",
  "python-visitkorea-api @ git+...",
  "python-kma-api @ git+...",
  "python-opinet-api @ git+...",
  "python-krex-api @ git+...",
  "python-khoa-api @ git+...",
  "python-knps-api @ git+...",
  "python-krmois-api @ git+...",
  "python-krforest-api @ git+...",
  "python-krheritage-api @ git+...",
  "python-kasi-api @ git+...",
  # ...
]
```

본 라이브러리의 디버그 UI(`krtour-map-debug-ui`)는 별도 패키지이며 TripMate는
의존하지 않는다 (`python-krtour-map` ADR-020). 디버그 UI는 운영자가 별도로 띄울
수 있다.

개발 중에는 sibling checkout + editable install 권장:

```bash
cd ~/tripmate-workspaces
git clone https://github.com/digitie/python-krtour-map.git
cd tripmate
uv pip install -e ../python-krtour-map
```

## 3. Resource 주입 (TripMate가 책임)

라이브러리는 어떤 resource(engine, S3 client, provider client, geocoder)도 자체
생성하지 않는다. 모두 TripMate에서 주입:

```python
# apps/api/app/etl_bridge/krtour_map.py
from functools import lru_cache
from sqlalchemy.ext.asyncio import create_async_engine

from krtour.map import AsyncKrtourMapClient
from kraddr.geo import AsyncAddressClient

from tripmate.api.core.config import Settings
from tripmate.api.services.file_storage import get_file_store
from tripmate.api.services.provider_clients import get_provider_clients


@lru_cache
def get_feature_engine():
    settings = Settings()
    return create_async_engine(
        settings.feature_pg_dsn.get_secret_value(),  # python-krtour-map과 같은 DB
        pool_size=settings.pg_pool_size,
        pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": "public,x_extension"}},
    )


async def get_krtour_map_client() -> AsyncKrtourMapClient:
    return AsyncKrtourMapClient(
        engine=get_feature_engine(),
        file_store=await get_file_store(),
        kraddr_geo_client=AsyncAddressClient(...),
        providers=await get_provider_clients(),
    )
```

`AsyncKrtourMapClient`는 async context manager — `async with`로 lifecycle 관리:

```python
async with AsyncKrtourMapClient(...) as client:
    features = await client.features_in_bounds(bbox, kinds=["place", "event"])
```

장기 ASGI 의존성으로 쓸 때는 FastAPI lifespan에서 한 번 만들고 응용 종료 시 닫는다.

## 4. FastAPI 라우터에서 사용

```python
# apps/api/app/api/routes/trips.py
from fastapi import APIRouter, Depends

from krtour.map import AsyncKrtourMapClient
from tripmate.api.etl_bridge.krtour_map import get_krtour_map_client
from tripmate.api.schemas.trip import TripWithPois

router = APIRouter(prefix="/trips", tags=["trips"])


@router.get("/{trip_id}", response_model=TripWithPois)
async def get_trip(
    trip_id: str,
    feature_client: AsyncKrtourMapClient = Depends(get_krtour_map_client),
):
    trip = await trip_repo.get(trip_id)
    feature_ids = [p.feature_id for d in trip.days for p in d.pois]
    features = await feature_client.features_by_ids(feature_ids)
    return build_trip_response(trip, features)
```

응답 빌더가 `app` 도메인과 `feature` 도메인을 join한다. 응용 레이어에 머무는 join —
SQL JOIN을 schema 경계에 걸지 않는다 (ADR-003).

## 5. Dagster asset에서 사용

```python
# apps/etl/assets/feature_event_festivals.py
from dagster import asset, AssetExecutionContext

from krtour.map import AsyncKrtourMapClient
from tripmate.etl.resources import KrtourMapResource, VisitKoreaResource


@asset(
    group_name="feature_event",
    description="VisitKorea 축제 적재",
)
async def feature_event_festivals(
    ctx: AssetExecutionContext,
    krtour_map: KrtourMapResource,
    visitkorea: VisitKoreaResource,
) -> dict:
    async with krtour_map.client() as client:
        items = await visitkorea.client.search_festival(...)        # provider 직접
        bundles = client.providers.visitkorea.festival_to_bundles(items)
        result = await client.load_festivals(bundles)
        ctx.log.info("loaded", extra=result.as_metadata())
        return result.as_metadata()
```

핵심:

- Dagster resource는 thin wrapper — `client.__aenter__/__aexit__`만 노출.
- provider client 호출은 asset 함수에서 직접 — 라이브러리에 provider client 인스턴스를
  넘겨서 변환만 위임.
- 결과는 asset metadata에 기록 (Dagster UI에서 확인).

## 6. 호출 메서드 카탈로그 (계획)

`python-krtour-map`의 `AsyncKrtourMapClient`가 제공할 메서드 (그쪽 저장소
`docs/architecture.md` 참조). TripMate에서 사용하는 주요 호출:

| 메서드 | 입력 | 출력 | 용도 |
|--------|------|------|------|
| `features_in_bounds(bbox, kinds=...)` | bbox + kinds | `list[Feature]` | 지도 화면 |
| `features_by_ids(feature_ids)` | id 목록 | `list[Feature]` | POI 첨부 join |
| `feature_detail(feature_id, kind=...)` | id | `Feature + detail` | 상세 페이지 |
| `weather_for_feature(feature_id, asof=...)` | id + 시각 | `WeatherCard` | 여행 컨텍스트 카드 |
| `prices_for_feature(feature_id, asof=...)` | id + 시각 | `PriceCard` | 주유소/휴게소 가격 |
| `load_festivals(bundles)` | DTO | `LoadResult` | Dagster asset |
| `load_places(bundles)` | DTO | `LoadResult` | Dagster asset |
| `load_notices(bundles)` | DTO | `LoadResult` | Dagster asset |
| ... | ... | ... | ... |

실제 메서드 시그니처/시멘틱은 `python-krtour-map` 측의 코드/문서가 권위. 본 표는
TripMate 입장의 cheat sheet.

## 7. 응답 셰입 변환 (HTTP 응답)

라이브러리 DTO(`Feature`, `WeatherValue`, `PriceValue`, ...)는 TripMate API의
응답 모델과 다르다. 변환은 응용 레이어:

```python
# apps/api/app/services/trip_view_builder.py
def build_trip_response(trip: TripModel, features: list[Feature]) -> TripWithPois:
    feature_by_id = {f.feature_id: f for f in features}
    return TripWithPois(
        trip_id=str(trip.trip_id),
        title=trip.title,
        days=[
            DayView(
                day_id=str(d.day_id),
                date=d.date,
                pois=[
                    PoiView(
                        attachment_id=str(p.attachment_id),
                        feature_id=p.feature_id,
                        feature=_feature_to_summary(feature_by_id.get(p.feature_id)),
                        feature_snapshot=p.feature_snapshot,
                        user_note=p.user_note,
                    )
                    for p in d.pois
                ],
            )
            for d in trip.days
        ],
    )
```

라이브러리 DTO를 그대로 응답 모델에 노출하지 않는다 — 응답 셰입 변경은 라이브러리
변경과 분리.

## 8. 트랜잭션 / 세션 경계

- 라이브러리는 주입받은 engine으로 자체 세션을 생성하지만, **호출자(TripMate)가
  명시적 트랜잭션을 열어 동일 connection을 공유**할 수도 있다 (Sprint 진입 후
  ADR로 결정).
- 단순 read 호출은 라이브러리 default 세션 사용.
- write가 섞이면 TripMate에서 트랜잭션을 열고 라이브러리에 connection을 주입
  (TBD — `python-krtour-map`에 connection injection API가 추가될 때).

## 9. v1 → v2 이전 매핑

v1의 `apps/api/app/services/krtour_map*.py`, `apps/api/app/core/krtour_map_contract.py`,
`apps/api/app/dagster_etl/` 자산은 v2에서 다음과 같이 처리:

| v1 자산 | v2 처리 |
|---------|---------|
| `services/krtour_map.py` (얇은 wrapper) | 제거 — `AsyncKrtourMapClient` 직접 사용 |
| `services/krtour_map_contract.py` | `python-krtour-map` ADR-006으로 흡수, 본 저장소에서 제거 |
| `services/krtour_map_feature_store.py` | `python-krtour-map.infra.*_repo`로 흡수 |
| `core/krtour_map_contract.py` | 제거 (라이브러리가 소유) |
| `dagster_etl/registry.py`, `loaders.py` | `apps/etl/assets/<name>.py`로 분할 + 얇은 어댑터로 단순화 |

자세한 이전 작업은 ADR-NNN으로 한 건씩 박는다.

## 10. 디버그 UI 사용

`python-krtour-map`에는 별도 `krtour-map-debug-ui` 패키지가 있다 (그쪽 저장소
`packages/krtour-map-debug-ui/`). TripMate는 의존하지 않는다.

운영자가 디버그 UI를 띄우고 싶을 때:

```bash
cd ~/tripmate-workspaces/python-krtour-map
uv pip install -e packages/krtour-map-debug-ui
uvicorn krtour.map_debug_ui.app:app --host 127.0.0.1 --port 8600
```

디버그 UI는 인증이 없다 — localhost / 내부망 전용 (그쪽 저장소 ADR-005). 운영
환경에 노출하지 않는다.

## 11. 작업 체크리스트 (TripMate가 라이브러리에 의존하는 변경 시)

- [ ] 라이브러리 git URL pin sha 갱신 (`pyproject.toml`)
- [ ] 라이브러리 측 PR 머지 확인
- [ ] schema 변경이면 `python-krtour-map alembic upgrade head` 후
      `tripmate alembic upgrade head` 순서 검증
- [ ] 통합 테스트 (`apps/api/tests/integration/krtour_map/`) 통과
- [ ] OpenAPI export 재실행
- [ ] CHANGELOG.md (사용자 가시 변경이면)
- [ ] `docs/journal.md` 엔트리
- [ ] (필요 시) `docs/decisions.md` ADR
