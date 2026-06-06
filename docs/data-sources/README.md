# 데이터 소스 인덱스 (cross-reference)

본 디렉토리는 TripMate가 사용하는 데이터 소스 목록 + 소유 저장소 안내.

> **핵심 분담**: 지도 feature provider raw 적재 + serving 테이블은
> **`python-krtour-map` 소유**. TripMate는 OpenAPI HTTP 결과만 사용한다(ADR-026).
> 주소/행정구역/geocoding은 krtour-map 경유가 아니라 **`python-kraddr-geo` v2 REST**
> 를 직접 호출한다(ADR-025).
> 단, KASI 특일/POI 출몰시각은 TripMate `app` schema 소유 데이터라 본 저장소가
> `python-kasi-api`로 직접 통합한다.

## 1. 라이브러리 소유 데이터 소스

다음은 모두 `python-krtour-map` 저장소에서 문서/적재. 본 저장소는 cross-ref만.

| 도메인 | provider | 라이브러리 문서 |
|--------|----------|----------------|
| 날씨 | `python-kma-api` (단기/중기/실황/특보), `python-krex-api` (휴게소 날씨), `python-krairport-api` (공항 날씨), `python-khoa-api` (해양 지수), `python-airkorea-api` (대기질) | `python-krtour-map/docs/kma-weather-etl.md` 외 |
| 축제 / 행사 | `python-visitkorea-api`, `data.go.kr` 표준 (15013104), `python-krheritage-api` | `python-krtour-map/docs/event-feature-etl.md` |
| 유가 | `python-opinet-api` | `python-krtour-map/docs/opinet-place-price-etl.md` |
| 휴게소 | `python-krex-api` | `python-krtour-map/docs/krex-rest-area-feature-etl.md` |
| 해수욕장 | `python-khoa-api`, `python-kma-api` | `python-krtour-map/docs/khoa-beach-info-etl.md` |
| 휴양림 / 트래킹 / 국립공원 | `python-krforest-api`, `python-knps-api` | `python-krtour-map/docs/{forest,knps}-feature-etl.md` |
| 국가유산 | `python-krheritage-api` | `python-krtour-map/docs/krheritage-feature-etl.md` |
| 인허가 (MOIS LOCALDATA) | `python-krmois-api`, `python-mois-api` | `python-krtour-map/docs/mois-feature-etl.md` |
| 공항 | `python-krairport-api` | `python-krtour-map/docs/` |
| 문화/여가/도서관 | `python-mcst-api` | `python-krtour-map/docs/` |
| 표준데이터 (관광지/박물관/주차장/길/축제) | `data.go.kr-standard` (15017321, 15017323, 15012896, 15021141, 15013104) | `python-krtour-map/docs/standard-data-feature-etl.md` |

## 2. TripMate 직접 사용 데이터 소스

라이브러리 위임 안 함 — 본 저장소가 직접 통합.

| 도메인 | provider | 문서 |
|--------|----------|------|
| 이메일 | Resend | `docs/integrations/resend.md` |
| 소셜 로그인 | Google OAuth (Naver/Kakao는 T-122 future provider) | `docs/integrations/social-login.md` |
| 주소 / 행정구역 / geocoding | `python-kraddr-geo` v2 REST | `docs/integrations/kraddr-geo.md` |
| 지도 SDK | `maplibre-vworld-js` (VWorld + MapLibre GL JS, ADR-015) | `docs/integrations/maplibre-vworld.md` |
| AI Research (사용자 키) | Google Gemini | `docs/integrations/gemini.md` |
| 알림 | Telegram Bot | `docs/integrations/telegram.md` |
| 에러 추적 | Sentry | `docs/integrations/sentry.md` |
| 로그 집계 | Loki + Grafana | `docs/integrations/loki.md` |
| 객체 저장소 | RustFS (S3 호환) | `docs/runbooks/file-storage.md` |
| 특일 / POI 해·달 출몰시각 | `python-kasi-api` | `docs/integrations/kasi.md` |

## 3. 데이터 정책

자세히는 [`docs/compliance/data-policy.md`](../compliance/data-policy.md). 핵심:

- TOS 준수 (provider별 시점 확인)
- raw long-term 저장은 소유 서비스에서만. krtour-map feature raw는 krtour-map
  `source_records`, KASI raw는 TripMate `app.kasi_special_days` /
  `app.trip_poi_rise_sets`
- 키는 환경변수 + 마스킹
- 같은 region + time window 반복 호출 X
- 사용자 가시 결과는 provider 라벨 명시

## 4. v1 → v2 데이터 소스 이전

v1 `docs/data-sources/*.md` (8개) 자산은 모두 `python-krtour-map` 저장소로 이전.
본 저장소에는 단일 인덱스 (본 파일) + cross-ref만.

| v1 파일 | v2 위치 |
|---------|---------|
| `docs/data-sources/address-region.md` | `python-krtour-map/docs/address-geocoding.md` 등 |
| `docs/data-sources/beach-sources.md` | `python-krtour-map/docs/khoa-beach-info-etl.md` |
| `docs/data-sources/fuel-opinet.md` | `python-krtour-map/docs/opinet-place-price-etl.md` |
| `docs/data-sources/public-places.md` | `python-krtour-map/docs/mois-feature-etl.md` |
| `docs/data-sources/rest-area-expressway.md` | `python-krtour-map/docs/krex-rest-area-feature-etl.md` |
| `docs/data-sources/tour-festival.md` | `python-krtour-map/docs/event-feature-etl.md` |
| `docs/data-sources/weather-air-quality.md` | `python-krtour-map/docs/kma-weather-etl.md` 등 |
| `docs/data-sources/provider-policy-and-todo.md` | `docs/compliance/data-policy.md` (본 저장소) |

## 5. AI agent 작업 가이드

새 외부 데이터 소스 추가 시 결정 순서:

1. 사용자 / 인증 / Admin / 알림 / 지도 SDK인가? → **TripMate 직접 통합**
   (`docs/integrations/` 신규)
2. 한국 공공 API feature 데이터인가? → **`python-krtour-map`에 PR**.
   TripMate `app` schema 소유 데이터(예: KASI 특일/POI 출몰시각)면 본 저장소에
   통합 문서와 Dagster job을 추가
3. 본 README 표 갱신
4. `docs/compliance/data-policy.md` TOS 정책 추가
