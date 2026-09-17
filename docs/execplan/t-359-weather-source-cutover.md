# T-359 날씨 소스 이관 실행 계획 (`kor-travel-map` → `kor-travel-weather`)

## 상태

2026-09-17 설계·계약 고정(P0) 완료. **코드 변경 없음.** 운영 날씨는 여전히
`kor-travel-map`에서 온다.

결정 = ADR-068. 설계 정본 = [`docs/integrations/kor-travel-weather.md`](../integrations/kor-travel-weather.md).

## 목표

Pinvi의 날씨 소스를 전용 서비스로 옮기되, **공개 계약을 바꾸지 않고**, 각 단계를
feature flag로 되돌릴 수 있게 한다.

## 차단 게이트 G-1 (가장 중요)

`kor-travel-weather`의 전국 KMA 격자 커버리지 확보 전에는 **P6(기본값 on)에 진입하지
않는다.**

2026-09-17 실측: 전체 location 1,430개 중 KMA 격자 앵커는 `e2e-seoul` **1개**. 실제
관광지에서는 상용 provider(OpenWeatherMap/WeatherAPI 등) 예보만 잡힌다. 부산 해운대
최근접 앵커 `/latest`의 KMA 행은 0건이었다.

- 소관: **`kor-travel-weather` 저장소**. Pinvi는 구현하지 않는다(금지룰 3).
- Pinvi 측 강제 수단: 표본 좌표 커버리지 테스트(게이트 F). 통과 전까지 flag 기본값은
  `off`를 유지한다.
- **P1~P5는 G-1과 무관하게 진행 가능하다.**

## 단계

### P0 — 설계·계약 고정 ✅

- ADR-068, `docs/integrations/kor-travel-weather.md`, 본 문서.
- 교차 문서 정합(§ 문서 동기화).

### P1 — client + DTO + 계약 테스트 (배선 없음)

- `kor-travel-weather`의 `packages/kor-travel-weather-api/openapi.json`에서 DTO 생성.
  **손으로 옮겨 적지 않는다.**
- `apps/api/app/clients/kor_travel_weather.py` — httpx client, 도메인 예외, 재시도,
  타임아웃. 인증 헤더 **없음**.
- vendored OpenAPI snapshot + 드리프트 CI 게이트(현재 `kor-travel-map` 방식과 동일).
- `Settings`에 `pinvi_kor_travel_weather_*` 배선 + `.env.example`.
- 검증: MockTransport 계약 테스트, 422/404/RFC7807 오류 매핑, 좌표 범위 경계값.

### P2 — feature → location 해석기 + 캐시

- Alembic: `app.weather_location_links`
  (`feature_id` PK, `location_id`, `source_location_ids[]`, `lat/lon`, `distance_km`,
  `measurement_point` jsonb, `resolved_at`, `stale`).
- 해석기: `radius_km` 20 → 50 → 100 단계 확대. 반경 내 앵커 없음은 장애가 아니라
  `no_data`.
- **`source_location_ids`를 통째로 저장한다** — 대표 location만 쓰면 기상청 예보가
  조용히 누락된다(설계 §3.3).
- 좌표 변경 시 `stale=true` 후 재해석.
- 검증: 해석 캐시 히트/미스, 반경 확대, 좌표 변경 무효화.

### P3 — 단건 weather 표면 전환 (flag)

- `GET /features/{id}/weather`를 flag로 새 경로에 태운다. 응답 셰입 불변.
- provider 우선순위 상수 + `unit` 무가정 매핑.
- `advisory` 정규화: `alerts[]` → `forecast_style="advisory"` 투영.
- **metric key 정규화 결정** — 상용 어휘를 서버에서 KMA 어휘로 접을지, 클라이언트
  분류기를 넓힐지. 접지 않으면 `TripWeatherSummary.tsx`가 상용 metric을 **조용히
  버린다**(설계 §3.1-(3)).
- **`?asof=` 축소 반영** — 시점 조회 엔드포인트가 없고 보존이 2일이라 과거 `target_at`은
  `no_data`가 된다. `docs/api/features.md` §2.3을 함께 고친다.
- **`kind='weather'` feature 분기**(설계 §4.6) — `FeatureMapView.tsx`가 weather feature
  선택 시 호출하는 단건 weather도 새 경로를 타야 한다.
- 검증: 동일 feature에 대해 구/신 경로 응답을 **나란히 비교**하는 테스트.

### P4 — Trip view 전환 (flag)

- batch 1회 → `/markers` 1회 + location별 `/forecast` fanout.
- `card_key := location_id`.
- view당 10초 예산, fanout 동시성 상한, 부모 취소 전파, 부분 실패는 `unavailable`.
- `retired` 판정을 선행 feature batch 결과로 이관(설계 §4.3).
- **e2e·런북 재정의**(삭제 아님): `apps/web/e2e/trip-detail.e2e.ts`의 "단건 weather 요청
  0회" 단언, `trip-feature-resolution-live-mutating.live.ts` + `PINVI_LIVE_WEATHER_*`
  픽스처(현재 `feature_id` 모양), `docs/runbooks/live-mutating-e2e.md`의 "Trip read 1회당
  weather batch POST 정확히 1회" 게이트 — 모두 새 호출 모양(`/markers` 1회 + location별
  `/forecast`)으로 다시 쓴다.
- 검증: 카드 파티션 불변식(Pydantic + Zod), 예산 초과, 취소, 중복 location dedupe.

### P5 — Admin weather-values 전환 (flag) — **셰입 변경 동반**

lineage 필드는 이미 노출돼 있다. P5의 실제 문제는 그 반대다 — **일부가 새 소스에서
살아남지 못한다.**

- `apps/api/app/clients/kor_travel_map_admin.py`의 `get_feature_weather`를 새 경로로
  옮긴다. (사용자 경로와 **별도 client 파일**이다 — 놓치기 쉽다.)
- `AdminFeatureWeatherMetric` 필수 필드 조정:
  - `provider_dataset_id`(int), `dataset_display_name`(str) — 새 소스에 **대응물 없음**
  - `known_at` — 새 소스에서 **nullable**
    → 셋을 nullable로 넓히고 Pydantic(`schemas/admin.py`) · Zod
    (`packages/schemas/src/admin.ts`) · Admin 테이블 렌더러(`FeatureDetailSubpage.tsx`)를
    함께 고친다. **없는 값을 지어내 채우지 않는다.**
- `asof` 422 거부 정책: 기존 사유("Map Admin 계약이 현재값만 제공")는 소멸하므로
  **사유를 다시 세운 뒤** 유지 여부를 정한다. 새 소스에는 `/forecast?from=&to=`가 있다.

### P6 — 기본값 on + 구 경로 제거 **(G-1 게이트)**

- 커버리지 게이트 F(G-1) **및 처리방침 게이트 H(G-2)** 통과 확인.
- flag 기본값 `on`.
- 구 경로 제거 — **두 파일이다**:
  - `kor_travel_map.py` 사용자 3경로(`feature_weather`가 `/weather`·`/weather/snapshot`
    둘을 겸한다, `get_weather_batch`) + 관련 DTO/디코더
  - `kor_travel_map_admin.py` `get_feature_weather` (P5에서 이미 옮겼다면 잔여 정리)
- `pinvi_kor_travel_map_service_token`은 **남긴다** — feature batch가 계속 쓴다.
- `kor-travel-map` OpenAPI 계약 테스트에서 weather 기대 제거:
  `tests/unit/test_kor_travel_map_contract.py`의 `_CONSUMED_PATHS`·query 집합·DTO 이름과
  **SHA-256 핀이 걸린** `tests/contract/kor-travel-map-openapi-*.json` 픽스처를 함께
  갱신한다(핀 때문에 픽스처만 고치면 깨진다).
- N150 live 검증 후 문서 정리.

### P7 — 과거 날씨 스냅샷 (ADR-068 결정 8, 사용자 결정 대기)

- `app.trip_day_weather_snapshots`. 지난 여행 일자 카드를 확정 저장.
- 읽기 분기: 과거 → 스냅샷, 현재/미래 → 라이브.
- **설계 §7-1 사용자 결정(A/B/C) 확정 후 착수.** 권장 B.

## 검증 게이트

| ID  | 내용                                                                         |
| --- | ---------------------------------------------------------------------------- |
| A   | Pinvi가 provider 원천을 파싱하지 않음 — 어휘 통합 입력은 `WeatherValueOut`뿐 |
| B   | `source_location_ids` 전체 합산 회귀 — 서울 좌표에서 KMA 행 0이면 실패       |
| C   | `weather_cards` 키 집합 == `found.card_key` 참조 집합 (Pydantic + Zod)       |
| D   | view당 10초, fanout 동시성 상한, 취소 전파                                   |
| E   | `kor-travel-weather` OpenAPI 스냅샷 드리프트                                 |
| F   | **표본 좌표 KMA 커버리지 — cutover를 기계적으로 막는 게이트**                |
| G   | Playwright e2e는 N150에서만 (ADR-051)                                        |

## 문서 동기화 대상

### P0에서 이미 상호 참조를 걸어 둔 것

- `docs/integrations/kor-travel-map-rest-api.md` §2.6/2.6a/2.6b — 이관 예정 표기
- `docs/api/features.md` §2.3
- `docs/data-sources/README.md`, `docs/kor-travel-map-integration.md`
- `CLAUDE.md`, `AGENTS.md`, `SKILL.md`

### 아직 남은 것 — 해당 단계에서 반드시 갱신

| 문서                                               | 무엇이 어긋나는가                                                                                     | 단계             |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ---------------- |
| `docs/compliance/data-policy.md`                   | "날씨: 기상청" + "국외 이전 의무 발생 안 함" — 상용 provider 표시 시 **거짓**. 위탁 목록도 재작성     | **G-2, P6 이전** |
| `docs/api/trips.md`                                | "같은 일자·**기상 격자**의 여러 feature가 같은 카드를 참조" — dedupe 근거가 `location_id`로 바뀐다    | P4               |
| `docs/api/admin.md`                                | weather-values 소스를 map admin 엔드포인트로 명시 + `asof` 422 사유                                   | P5               |
| `docs/runbooks/live-mutating-e2e.md`               | "weather batch POST 정확히 1회" 운영 게이트 — P4가 깬다                                               | P4               |
| `docs/kor-travel-map-requirements.md` §2.6 / K-6   | map에 대한 `build_weather_card` **미해결 요청**이 열려 있다. 소비를 끊으면 중복 투자 유발 → 철회 표기 | P6               |
| `docs/execplan/t-vn-16b-weather-batch-consumer.md` | 헤더가 "현재 계약은 §2.6a" — P4에서 stale                                                             | P4               |
| `docs/legal/terms-of-service.md`                   | "공공데이터 기반" 문구 — 상용 provider 비중에 따라 재검토                                             | G-2와 함께       |

> `docs/architecture.md`와 `docs/test-strategy.md`는 날씨 언급이 **없다** — 동기화
> 대상이 아니다.
> `docs/api/public.md`의 beach passthrough는 불투명 필드라 소스 교체와 독립이다.

## 실패 복구

- 각 단계는 flag `off`로 즉시 되돌린다. P2의 테이블은 남겨도 무해하다.
- P6 이후 문제 발견 시 flag만으로는 못 돌아온다(구 경로 제거됨) → P6는 **P3~P5가
  운영에서 안정적으로 관측된 뒤** 착수한다.
- schema 변경은 P2(링크 테이블)와 P7(스냅샷) 둘뿐이며 둘 다 additive다.
