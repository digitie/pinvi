# KASI 통합 — 특일 정보 + 위치별 해·달 출몰시각

본 문서는 Pinvi가 `python-kasi-api`를 통해 한국천문연구원(KASI) data.go.kr API를
사용하는 계약이다. `python-kasi-api`는 `DATA_GO_KR_SERVICE_KEY`를 기본 서비스키로
사용한다. Pinvi는 별도 `KASI_API_KEY` 같은 새 환경변수를 만들지 않는다.

## 1. 사용 API

| Pinvi 기능 | `python-kasi-api` 함수 | KASI operation |
|---------------|------------------------|----------------|
| 특일 정보 | `special_days.holidays` | `getRestDeInfo` |
| 국경일 정보 | `special_days.national_holidays` | `getHoliDeInfo` |
| 기념일 정보 | `special_days.anniversaries` | `getAnniversaryInfo` |
| 24절기 정보 | `special_days.solar_terms_24` | `get24DivisionsInfo` |
| 잡절 정보 | `special_days.sundry_days` | `getSundryDayInfo` |
| 위치별 해·달 출몰시각 | `rise_set.location` | `getLCRiseSetInfo` |

사용자가 별도 축소 범위를 지정하지 않았으므로 "특일 정보"는 위 특일 계열 5개
dataset을 모두 수집 대상으로 본다.

## 2. 특일 정보 업데이트

- Dagster job: `kasi_special_days_daily`
- 실행 주기: 하루 1회, KST 기준
- 조회 범위: 실행일 기준 **과거 6개월 ~ 미래 18개월**
  - 예: 2026-06-04 실행 시 월 단위 API 호출 범위는 2025-12 ~ 2027-12
  - KASI 특일 API가 `sol_year`, `sol_month` 단위이므로 월 bucket을 inclusive로
    생성한다.
- 저장 정책: `app.kasi_special_days`에 upsert
- 삭제 정책: **별도 삭제 없음**. 조회 범위 밖으로 밀려난 과거 데이터도 삭제하지
  않는다.
- 실패 정책: 특정 dataset/month 실패는 해당 partition 실패로 기록하고 재시도한다.
  이미 저장된 row는 유지한다.

권장 unique key:

```text
(dataset, sol_date, sequence, name)
```

KASI 응답에 안정적인 sequence가 없으면 `(dataset, sol_date, name)`을 사용하고 raw
payload를 보존한다.

## 3. POI 출몰시각 업데이트

Pinvi 여행계획 POI 생성 시 한 번만 `위치별 해달 출몰시각 정보조회`
(`getLCRiseSetInfo`)를 호출한다.

흐름:

1. `POST /trips/{trip_id}/pois`가 POI를 생성한다.
2. 서비스 레이어가 POI의 `feature_snapshot.coord` 또는 kor-travel-map batch 조회 결과에서
   `(longitude, latitude)`를 얻는다.
3. 방문일은 `trip_days.date`를 우선 사용한다. 날짜가 아직 없으면 출몰시각 조회를
   보류하고 `status='pending_date'`로 남긴다. 날짜와 좌표가 모두 있으면
   `status='pending_fetch'`로 남겨 Dagster one-shot job이 처리한다.
4. Dagster run 또는 enqueue job이 `rise_set.location(locdate, longitude, latitude)`
   를 호출한다.
5. 결과를 `app.trip_poi_rise_sets`에 POI 부속 정보로 저장한다.

사용자 규칙:

- POI 생성 시 1회 업데이트한다.
- 별도 주기 재계산은 없다.
- POI의 날짜나 좌표가 이후 바뀌어도 자동 재조회하지 않는다. 기존 row는 생성 당시
  `locdate`/좌표 snapshot의 부속 정보로 유지한다.
- 재조회가 필요하면 후속 PR에서 명시적 refresh action(사용자/관리자 버튼 또는
  one-shot job enqueue)을 추가한다. 그 전까지 API/화면은 snapshot 기준임을 전제로
  `locdate`, `longitude`, `latitude`를 함께 노출하거나 값이 불일치하면 숨긴다.

## 4. 저장 셰입

`app.trip_poi_rise_sets` 권장 컬럼:

| 컬럼 | 비고 |
|------|------|
| `poi_id` | `app.trip_day_pois.attachment_id` 참조, PK |
| `locdate` | 조회 기준일 |
| `longitude`, `latitude` | 요청 좌표 snapshot |
| `sunrise_at`, `sunset_at` | 해 출몰시각. 파싱 가능할 때 `timestamptz` |
| `moonrise_at`, `moonset_at` | 달 출몰시각. 파싱 가능할 때 `timestamptz` |
| `raw_payload` | KASI 원문 payload |
| `status` | `pending_date` / `pending_coord` / `pending_fetch` / `success` / `failed` |
| `fetched_at` | 마지막 호출 시각 |
| `error` | 실패 시 redacted error |

응답 셰입에서는 POI 항목에 `rise_set`을 선택 필드로 붙인다. 값이 없거나
`pending_*`이면 클라이언트는 해당 정보를 숨긴다.

## 5. 환경변수

```dotenv
DATA_GO_KR_SERVICE_KEY=
PINVI_KASI_SPECIAL_DAYS_LOOKBACK_MONTHS=6
PINVI_KASI_SPECIAL_DAYS_LOOKAHEAD_MONTHS=18
```

`DATA_GO_KR_SERVICE_KEY`가 없으면 KASI Dagster job은 skip/fail-fast 중 하나를
선택해야 한다. 사용자 지시상 OpenAI 등 외부 AI API key는 사용하지 않는다.

## 6. AI agent 체크리스트

- [x] `apps/etl` dependency에 `python-kasi-api`를 git URL 의존성으로 추가했다.
- [x] `kasi_special_days_daily` job은 삭제 없이 upsert만 수행한다.
- [x] POI 생성 경로는 좌표와 방문일이 있을 때 `trip_poi_rise_sets`를
      `pending_fetch`로 남긴다.
- [ ] KASI 응답/요청 로그에서 `serviceKey`와 인증 관련 값을 마스킹한다.
- [ ] live API 검증은 `DATA_GO_KR_SERVICE_KEY`가 있을 때만 수행한다.
