# kor-travel-weather 연동 (날씨 소스 이관 설계)

Pinvi 날씨 데이터 소스를 `kor-travel-map`에서 **`kor-travel-weather`**로 옮기는 설계
정본이다. 결정 근거는 ADR-068, 실행 순서는
[`docs/execplan/t-359-weather-source-cutover.md`](../execplan/t-359-weather-source-cutover.md)에
있다.

> **현재 상태**: 설계·계약 고정 단계. **코드는 아직 한 줄도 바뀌지 않았다.** 운영
> 날씨는 여전히 `kor-travel-map`에서 온다(§2.6/2.6a/2.6b,
> [`kor-travel-map-rest-api.md`](kor-travel-map-rest-api.md)).

---

## 0. 한눈에 — 이 이관의 실제 모양

| 축               | 현재 (`kor-travel-map`)                      | 이관 후 (`kor-travel-weather`)                                   |
| ---------------- | -------------------------------------------- | ---------------------------------------------------------------- |
| 키               | `feature_id`                                 | `location_id` (문자열, 서비스 고유)                              |
| 좌표→날씨 해석   | 생산자가 spatial KNN으로 anchor feature 선택 | **소비자(Pinvi)가** `/v1/weather/resolve`로 해석 후 캐시         |
| Trip 조회        | `POST /v1/features/weather/batch` **1회**    | location별 fanout (`/markers` 1회 + location당 `/forecast` 1회)  |
| 인증             | ServiceToken 필수                            | **인증 없음** (공개 read)                                        |
| 카드 dedupe      | 서버 계산 `card_key` (anchor bundle ordinal) | **`location_id`가 곧 dedupe 키**                                 |
| 보존             | 3년 immutable                                | 현재 **기본 2일** → **15일로 연장 예정**(G-3, 아직 미배포, §4.2) |
| 기상청(KMA) 예보 | 전국 격자 자동 생성                          | **현재 1개 지점뿐** — §1.2 차단 사유                             |

**한 줄 요약**: 계약 정합은 어렵지 않다. 막는 것은 **데이터 커버리지(G-1)** ·
**개인정보 처리방침 정합(G-2)** · **보존 지평(G-3)** 셋이다.

---

## 1. 이관 준비 상태 실측 (2026-09-17)

설계 판단을 문서 주장이 아니라 **운영 인스턴스 실측**으로 세웠다. 대상은
`https://weather-api.digitie.mywire.org` (`/version` → `git_commit: 3411ecc`, 로컬
`main` HEAD와 동일).

### 1.1 갖춰진 것

- 서비스는 **운영 중이고 살아 있다**. 141 커밋, 최신 2026-09-16.
- 카탈로그 **1,430개 location**. 실제 관광지 기준 최근접 앵커 거리는 충분히 가깝다:

  | POI             | 최근접 앵커    |   거리 | 종류     |
  | --------------- | -------------- | -----: | -------- |
  | 부산 해운대     | 해운대해수욕장 | 0.1 km | khoa     |
  | 울릉도 도동     | 울릉읍         | 0.4 km | airkorea |
  | 여수 오동도     | 덕충동         | 1.0 km | airkorea |
  | 전주 한옥마을   | 노송동         | 1.6 km | airkorea |
  | 제주 성산일출봉 | 성산읍         | 3.0 km | airkorea |
  | 안동 하회마을   | 예천군         | 5.8 km | airkorea |
  | 설악산 소공원   | 청정넷 0441    | 7.7 km | krforest |

  → **공간 커버리지는 문제가 아니다.**

- 대기질(AirKorea `PM10`/`PM25`/`KHAI` 등) 673개 측정소 — 현재 Pinvi 미세먼지 표시와
  **동등 이상**.
- 해양(KHOA 49) · 산악(krforest 520) · 휴게소(krex 187).
- `{data, meta}` envelope, RFC7807 오류, `X-Request-ID` 왕복 — Pinvi client 관례와 호환.

### 1.2 **차단 사유 — 기상청(KMA) 전국 커버리지 부재**

```
전체 location                 1,430
KMA 격자 앵커(nx/ny 보유)          1   ← e2e-seoul "서울 운영 테스트"
  airkorea 673 / krforest 520 / krex 187 / khoa 49 / e2e 1
```

전국에 **KMA 격자 앵커가 단 하나**이며 그나마 이름이 "서울 운영 테스트"인 픽스처다.
실제 결과:

- 서울시청 `/resolve` → 대표 location은 `airkorea-station-5852754068ed`(중구),
  KMA 단기예보 1,415행은 **다른 location(`e2e-seoul`)**에서 온다.
- 부산 해운대 최근접 앵커(`khoa-BCH001`) `/latest` → `weatherapi` 149행 +
  `openweathermap` 48행. **KMA 행 0건.**

즉 지금 이관하면 전국 대부분 지점에서 **기상청 공식 예보가 아니라 상용 API 예보**
(OpenWeatherMap/WeatherAPI/wttr.in/Open-Meteo)를 표시하게 된다. 한국 여행 앱에서
기상청은 사용자가 기대하는 권위 출처이므로 이는 조용히 넘길 변경이 아니다.

`kor-travel-map`은 POI 좌표에서 `(nx, ny)` 격자를 유도해 격자마다 weather-kind
Feature를 자동 생성한다(`providers/kma.py grid_to_weather_bundle`). `kor-travel-weather`에는
그 자동 provisioning이 아직 없다.

> **게이트 G-1**: `kor-travel-weather`가 요청 좌표에 대해 KMA 격자 앵커를 생성·수집하기
> 전에는 cutover하지 않는다. 이 작업은 `kor-travel-weather` 저장소 소관이며 Pinvi가
> 대신 구현하지 않는다(금지룰 3: provider 원천 변환은 Pinvi 밖).

### 1.2b **차단 사유 2 — 개인정보 처리방침이 사실과 어긋나게 된다 (게이트 G-2)**

`docs/compliance/data-policy.md`는 현재 이렇게 선언한다.

- 날씨 출처 = **기상청**
- 제공 provider가 전부 국내 정부/공공기관이므로 **"국외 이전 의무 발생 안 함"**

G-1이 풀리기 전 상태에서 이관하면 대부분 지점의 날씨가 OpenWeatherMap·WeatherAPI·
wttr.in·Open-Meteo — **국외 사업자**에서 온다. 위 두 문장이 즉시 거짓이 된다.

> **게이트 G-2**: 처리방침·위탁 목록 갱신과 국외 이전 판단을 마치기 전에는 비KMA
> provider 값을 사용자에게 **표시하지 않는다.** 이는 UX 판단이 아니라 법적 의무이며,
> §7-2의 "상용 provider 표시 허용 여부"는 그 판단이 끝난 뒤에야 열리는 질문이다.

### 1.3 그 밖의 실측 제약

- **`/resolve` 응답 3,121,446 bytes (3.1 MB), 1.9초.** 매 조회 경로에 둘 수 없다 —
  **좌표 해석 1회용(discovery)**으로만 쓰고 결과를 캐시한다.
- **ETag/Cache-Control 없음, rate limit 없음.** 캐시는 전적으로 Pinvi 책임이다.
- **보존 기본 2일**(`KOR_TRAVEL_WEATHER_RETENTION_DAYS=2`, `known_at` day partition
  통째 drop). 3년 immutable인 현재 소스와 근본적으로 다르다 → §4.2에서 **15일로 연장
  (C, 반영 예정)**하기로 결정했고 게이트 G-3으로 건다.
- **일출/일몰(KASI) 없음.** 해당 기능은 Pinvi 자체 ETL 소유이므로 이관 영향 없다
  (ADR-055, `app.trip_day_rise_sets`).
- CORS 허용 목록에 Pinvi 브라우저 origin이 없다 → **서버 간 호출만** 한다(현재
  구조와 동일하므로 추가 작업 없음).

---

## 2. 서비스 계약 요약

정본은 `kor-travel-weather`의 `packages/kor-travel-weather-api/openapi.json`
(OpenAPI 3.1)이다. **DTO를 손으로 옮겨 적지 않고 그 문서에서 생성**한다.

### 2.1 Pinvi가 쓰는 엔드포인트

| 용도                       | 호출                                                       | 비용               |
| -------------------------- | ---------------------------------------------------------- | ------------------ |
| 좌표 → location 해석 (1회) | `GET /v1/weather/resolve?lat=&lon=&radius_km=`             | **3.1 MB / 1.9 s** |
| 다지점 현재값 + 특보       | `GET /v1/weather/markers?location_id=…` (≤500)             | ~2 KB/지점         |
| 단일 지점 현재값           | `GET /v1/weather/locations/{id}/latest?limit=`             | ~8 KB              |
| 단일 지점 예보 구간        | `GET /v1/weather/locations/{id}/forecast?from=&to=&limit=` | 구간 비례          |

- `radius_km` 기본 100(과도) / 최대 500. Pinvi는 **명시적으로 좁혀** 보낸다(§3.2).
- `/markers`는 `latest` + `alerts`만 준다 — **예보 없음**.
- `/forecast`는 `from` 없이 부르면 가장 오래된 행부터 연다 → **항상 `from` 필수**.
- 좌표 범위 검증: `lat 33..43`, `lon 124..132` 밖은 422.

### 2.2 사실 DTO — `WeatherValueOut`

Pinvi 현재 `WeatherMetric`과 **거의 1:1**이다. 이관이 쉬운 유일한 축이다.

| `WeatherValueOut`                                                                                      | Pinvi `WeatherMetric` | 비고                                                     |
| ------------------------------------------------------------------------------------------------------ | --------------------- | -------------------------------------------------------- |
| `forecast_style`                                                                                       | `forecast_style`      | 동일 어휘 (`nowcast\|ultra_short\|short\|mid\|observed`) |
| `metric_key` / `metric_name`                                                                           | 동일                  |                                                          |
| `timeline_bucket`                                                                                      | 동일                  |                                                          |
| `value_number` / `value_text` / `unit` / `severity`                                                    | 동일                  | 정확히 하나만 non-null                                   |
| `issued_at` / `valid_at` / `valid_from` / `valid_until` / `observed_at`                                | 동일                  |                                                          |
| `provider` / `weather_domain`                                                                          | 동일                  |                                                          |
| `target_at`(필수) / `known_at`(nullable)                                                               | Pinvi 측 없음         | §4.2                                                     |
| `dataset_key`, `normalization_version`, `collected_at`, `source_record_key`, `value_id`, `location_id` | 없음                  | Admin 표면에서만 노출                                    |

`advisory`/`index`는 `kor-travel-weather`의 `forecast_style`에 없다. 특보는 별도
`alerts[]` 배열 + `weather_domain="weather_alert"` + `metric_key="ALERT"` +
`severity ∈ {warning, watch, advisory}`로 온다 → Pinvi는 이를 `forecast_style="advisory"`로
**투영 계층에서** 정규화한다.

### 2.3 metric 어휘가 둘이다 (신규 부담)

한 `location_id`에 5개 이상 provider의 사실이 **동시에** 담기며 어휘가 다르다.

- KMA 계열: `T1H TMP TMN TMX T3H REH POP WSD VEC RN1 PCP SNO PTY SKY LGT`
- 상용 계열: `TEMP FEELS_LIKE HUMIDITY PRESSURE WIND_SPEED WIND_DIRECTION PRECIP
PRECIP_PROB CLOUD_COVER VISIBILITY UV_INDEX WEATHER_CODE`
- AirKorea: `PM10 PM25 O3 NO2 SO2 CO KHAI`

**단위는 provider마다 다르다 — `unit` 필드를 반드시 읽고 가정하지 않는다.**
현재 `kor-travel-map`은 단일 어휘로 정규화해서 주므로, 이 매핑은 Pinvi가 **새로 지는
책임**이다.

> 금지룰 정합: 이는 provider _원천(raw)_ → DTO 변환이 아니라, 이미 정규화된
> `WeatherValueOut` 두 어휘를 Pinvi **표시 계층**에서 통합하는 작업이다. 원천 파싱은
> 여전히 `kor-travel-weather`가 한다. (§6-A에 이 경계를 테스트로 고정한다.)

### 2.4 provider 선택 정책이 필요하다

같은 `(location_id, metric, target_at)`에 여러 provider가 값을 준다. 현재는
`kor-travel-map`이 tier 규칙으로 하나를 골라줬다. 이관 후에는 Pinvi가 고른다.

**정책(제안)**: `python-kma-api` > `python-airkorea-api`(대기질 전용) > 상용
(`openweathermap` > `weatherapi` > `open_meteo` > `wttr_in`). 동률이면 `known_at` 최신.
이 우선순위는 코드 상수 하나에 두고 **테스트로 고정**한다.

---

## 3. Pinvi 소비 설계

### 3.1 공개 계약 — 경로·셰입은 유지, 예외 셋은 명시한다

Pinvi가 web/mobile에 노출하는 표면의 **경로와 응답 셰입**은 유지한다.

- `GET /features/{feature_id}/weather` → `FeatureWeatherCard`
- `TripViewDay.weather_by_feature_id` (6-상태 union) + `weather_cards`
- `GET /admin/features/{feature_id}/weather-values`

소비자에게 `location_id`를 노출하지 않는다. 즉 **`feature_id` ↔ `location_id` 해석은
Pinvi API 내부에 가둔다.** 되돌리기가 서버 한쪽에서 끝난다.

다만 "변경 0"이라고 적으면 거짓이 된다. **바뀌는 것 셋을 여기 못박는다.**

#### (1) `?asof=` 의미가 좁아진다 — 승계 엔드포인트가 없다

현재 `GET /features/{id}/weather?asof=`는 map의 `/weather/snapshot`
(`target_at` + `known_at`)으로 라우팅된다. **`kor-travel-weather`에는 시점 조회
엔드포인트가 없고**(§2.1) 보존이 2일이라, `target_at`이 과거인 조회는 T-366 스냅샷이
붙기 전까지 `no_data`가 된다.

경로와 파라미터는 남지만 **동작 범위가 줄어드는 공개 계약 변경**이다. 조용히 넘기지
않고 `docs/api/features.md` §2.3에 함께 반영한다.

#### (2) Admin weather-values는 셰입이 바뀐다 — 유지 불가

`AdminFeatureWeatherMetric`은 공개 metric에 **필수·non-null 4개**를 더한다
(`apps/api/app/schemas/admin.py`, `packages/schemas/src/admin.ts` 양쪽 동일).

| 필드                            | `kor-travel-weather` 대응                      |
| ------------------------------- | ---------------------------------------------- |
| `dataset_key` (str)             | ✅ 있음                                        |
| `known_at` (datetime, non-null) | ⚠️ **nullable**                                |
| `provider_dataset_id` (int)     | ❌ **없음** — map의 정수 dataset registry 소유 |
| `dataset_display_name` (str)    | ❌ **없음**                                    |

→ 세 필드를 nullable로 넓히고 Pydantic·Zod·Admin 테이블 렌더러
(`FeatureDetailSubpage.tsx`)를 함께 고친다. **없는 값을 지어내 채우지 않는다** —
provenance 표면에서 거짓 lineage는 금지다. (T-364)

#### (3) web 분류기가 상용 어휘를 인식하지 못한다

`TripWeatherSummary.tsx`의 `WEATHER_LABELS`·`WEATHER_RE`·`DUST_RE`는 **KMA 코드 전용**
이다. `TEMP`/`FEELS_LIKE`/`HUMIDITY`/`PRESSURE`/`WIND_SPEED`/`WIND_DIRECTION`/
`PRECIP`/`PRECIP_PROB`/`CLOUD_COVER`/`VISIBILITY`/`UV_INDEX`/`WEATHER_CODE`와 AirKorea의
`O3`/`NO2`/`SO2`/`CO`는 **어느 정규식에도 걸리지 않아 카드에서 조용히 사라진다.**

두 선택지 중 하나를 택한다.

- **(권장) 서버에서 metric key를 정규화**해 클라이언트에 KMA 어휘로 내려보낸다.
  클라이언트 변경이 0으로 유지되고 분류기 중복도 사라진다.
- 클라이언트 분류기를 상용 어휘까지 확장한다. 변경 면이 web + 테스트로 번진다.

어느 쪽이든 T-362/T-363 범위이며, "web 변경 0"은 **성립하지 않는다.**

### 3.2 feature → location 해석과 캐시 (신규)

`/resolve`가 3.1 MB이므로 POI마다 매번 부를 수 없다. 해석 결과를 Pinvi가 소유한다.

```
app.weather_location_links
  feature_id        text PK        -- Pinvi가 아는 feature 식별자
  location_id       text NOT NULL  -- kor-travel-weather canonical key
  source_location_ids text[]       -- 번들 구성원 전체 (§3.3 — 대표 1개로 부족)
  lat, lon          double precision
  distance_km       double precision
  measurement_point jsonb          -- station 표시용 (allow-list된 공개 필드)
  resolved_at       timestamptz
  stale             boolean DEFAULT false
```

- 해석은 **좌표 기준**이므로 feature 좌표가 바뀌면 `stale=true`로 표시하고 재해석한다.
- `radius_km`는 기본 100이 아니라 **20**으로 보내고, 미스 시 50 → 100으로 단계 확대한다.
  (§1.1 실측상 20 km면 표본 전부 적중한다.)
- 해석 실패(반경 내 앵커 없음)는 장애가 아니라 `no_data`다.

### 3.3 **함정 — 대표 `location` 하나로는 부족하다**

실측(§1.2)에서 드러난 사실이다. `/resolve`의 `data.location`은 대표 1개지만, 실제
사실은 `data.source_locations`에 걸쳐 있다. 서울시청 예에서 KMA 예보는 대표
location이 **아닌** 쪽에 있었고, 대표 location만 `/locations/{id}/forecast`로 부르면
`openweathermap`만 돌아온다.

→ **`source_location_ids`를 통째로 캐시하고, 조회 시 그 집합 전체를 합친다.**
이것을 놓치면 "이관했더니 기상청 예보가 사라졌다"가 **조용히** 발생한다. 회귀
테스트로 고정한다(§6-B).

### 3.4 Trip view 호출 계획

현재는 `POST /features/weather/batch` **1회**다. 이관 후에는:

```
1) trip의 POI 좌표 → weather_location_links 조회 (캐시 히트)
2) 미해석 좌표만 /resolve (보통 0건, 신규 POI에서만 발생)
3) 고유 location 집합 L 계산  (POI N개 → 보통 L은 5~20)
4) GET /markers?location_id=… (|L| ≤ 500)              — 현재값 + 특보, 1회
5) location마다 GET /forecast?from=여행시작&to=여행종료  — |L|회, 병렬
6) location_id로 카드 구성 → feature_id로 투영
```

- **`card_key := location_id`**. 같은 location에 걸린 여러 POI가 자연히 한 카드를
  공유하므로 현재의 `weather_cards` 파티션 불변식(Pydantic + Zod 이중 검증)을
  **그대로** 만족한다. 이 축은 오히려 단순해진다.
- 여행 전 구간을 `from`/`to` 한 번으로 덮으므로 **날짜 fanout은 없다**(location fanout만).
- 전체 예산은 현재와 같이 **view당 10초**, 동시성 상한을 두고 부모 취소를 전파한다.
- 부분 실패는 추측하지 않는다 — 미결 location의 weather는 `unavailable`.

### 3.5 상태 모델 매핑

현재 6-상태 union을 유지하되 의미를 다시 건다.

| 상태                     | 현재 근거                        | 이관 후 근거                     |
| ------------------------ | -------------------------------- | -------------------------------- |
| `found`                  | batch item `found` + card        | location 해석 성공 + 사실 ≥ 1행  |
| `no_data`                | 공개 parent 있으나 weather 없음  | 해석 성공했으나 구간 내 사실 0행 |
| `retired`                | `public_features`에 없음         | **근거 소멸** — §4.3             |
| `suppressed` / `missing` | 선행 feature batch의 parent 상태 | **변화 없음** (Pinvi 자체 판정)  |
| `unavailable`            | transport/계약/예산 실패         | 동일                             |

---

## 4. 회귀 — 정직하게 적는다

### 4.1 기상청 예보 상실 (치명, 게이트 G-1)

§1.2 참조. **cutover 차단 사유.** 해소 전에는 flip하지 않는다.

### 4.2 과거 날짜 날씨 상실 (보존 2일)

Pinvi는 여행 **계획·기록·공유** 앱이다. 지난 여행 상세를 열면 그날 날씨가 보여야
한다. 현재 소스는 3년 보존이라 가능하지만 `kor-travel-weather`는 **기본 2일**이다.

정확히 무엇을 잃는지: Pinvi는 `known_at`을 항상 "지금"으로만 보내므로 **bitemporal
replay는 원래 안 쓰고 있었다.** 실제 손실은 `target_at`이 2일 이전인 과거 구간이다.

**선택지와 결정**

| 안  | 내용                                             | 비용                        | 결과                     |
| --- | ------------------------------------------------ | --------------------------- | ------------------------ |
| A   | 과거 날씨 미지원 (`no_data`)                     | 0                           | 기록 기능 후퇴           |
| B   | Pinvi가 여행 일자 카드를 확정 시점에 스냅샷 저장 | 테이블 1개 + 저장 시점 정의 | 미채택                   |
| C   | **`kor-travel-weather` 보존 연장**               | 외부 저장소 + 스토리지      | **채택 (2026-09-17)** ✅ |

**사용자 결정 = C, 목표치 15일** (2026-09-17, **반영 예정 — 아직 배포되지 않음**).
Pinvi는 `app.trip_day_weather_snapshots` 같은 별도 스냅샷 테이블을 **만들지 않는다.**
보존은 사실을 소유한 서비스가 진다.

**15일은 3년 목표(그쪽 ADR-062)의 일부만 먼저 배포하는 것이며, 여전히 짧다.** 여행
종료 15일이 지난 뒤 상세를 열람·공유하면 그 날짜의 과거 날씨는 계속 `no_data`다. 이
잔여 한계를 "과거 날씨 지원"이라는 말로 감추지 않는다 — UI 문구·문서 모두 "최근 15일"
범위임을 밝힌다.

> **게이트 G-3**: `kor-travel-weather`의 실효 보존이 **15일 이상**일 때만 통과한다.
> 15일 미만이면(아직 미배포 상태 포함) 과거 날짜 날씨를 "지원한다"고 말하지 않는다.
> 해당 저장소 소관이며 현재는 **반영 예정** 단계다.

**대가 둘을 감수한다 — 문서에 남긴다.**

1. **소급되지 않는다.** 보존을 늘려도 이미 drop된 `known_at` partition은 돌아오지
   않는다. **연장 시점 이전 여행의 날씨는 영구 소실**이며 어떤 후속 작업으로도
   복구할 수 없다. (B였다면 스냅샷 시작 시점부터 쌓였을 것이고, C도 마찬가지로
   연장 시점부터다 — 다만 C는 그 시점이 외부 일정에 달려 있다.)
2. **외부 설정에 종속된다.** 보존이 15일 미만으로 되돌아가거나 스토리지 압박으로
   줄면 과거 여행 날씨가 **조용히** 사라진다. → Pinvi 측에 **보존 지평 가드**를
   둔다(임계 **15일** 미만이면 실패하는 점검, §6-I, T-367).
3. **15일도 완전한 해법이 아니다.** 15일보다 늦게 열람되는 과거 여행은 여전히
   `no_data`다. 더 긴 보존이 필요해지면 이 절을 다시 연다 — 재논의를 막지 않는다.

> 참고: `kor-travel-map`의 `docs/etl/weather-feature-normalization.md`는 "PinVi는 별도
> weather DB를 만들지 않는다"고 적고 있다. **C를 택했으므로 이 문장은 계속 유효하다** —
> 소스만 바뀌고 "Pinvi는 날씨를 저장하지 않는다"는 원칙은 유지된다.

### 4.3 `retired` 상태의 근거 소멸

현재 `retired`는 "공개 parent feature가 아님"이라는 `kor-travel-map`의 lifecycle
판정이었다. `kor-travel-weather`는 feature를 모르므로 이 판정을 못 한다.

→ feature lifecycle은 **여전히 `kor-travel-map` feature batch**가 준다(이관 대상
아님). 따라서 `retired`는 weather 응답이 아니라 **선행 feature batch 결과**에서
가져온다. 실제로 `suppressed`/`missing`이 이미 그렇게 동작하므로 같은 자리로 옮기면
된다 — 상태 자체는 보존된다.

### 4.4 중기예보(`mid`) · 특보 표면

- `mid`: `forecast_style`에 어휘는 있으나 현재 KMA 커버리지가 없어 사실상 0행. G-1과
  함께 풀린다.
- 특보: `kor-travel-map`도 전용 엔드포인트(`/v1/features/weather/alerts`,
  `/v1/features/{id}/weather/forecast`)를 **이미 갖고 있다** — vendored OpenAPI 스냅샷에
  있다. 다만 Pinvi가 **소비하지 않았을** 뿐이다. 즉 `alerts[]`는 이관이 만들어 주는
  신규 능력이 아니라 **새로 소비하기로 하는 선택**이다(범위 밖, 후속 task).

### 4.6 `kind='weather'` feature는 그대로 남는다 (이원 구조)

`kor-travel-map`은 KMA 격자마다 weather-kind feature를 생성하고, Pinvi 지도는 그것을
`WeatherMarker`로 그린다(`FeatureMapView.tsx`). 이관 후에도 map은 이 feature 생산을
계속한다.

→ marker의 **존재·위치**는 map feature에서, marker에 채울 **값**은 weather 서비스에서
오는 구조가 된다. `FeatureMapView.tsx`가 선택된 weather feature에 대해 호출하는 단건
weather도 새 경로를 타야 한다. 이 분기를 T-362에서 명시적으로 다룬다 — 방치하면
"지도에 마커는 있는데 값이 안 뜬다"가 된다.

`kind` enum 자체(`feature_suggestion` CHECK, MCP tool registry, Admin kind 필터)는
map 소유이므로 건드리지 않는다.

### 4.7 영향 받는 파일 (이관 시 반드시 함께 보는 목록)

| 영역      | 파일                                                                                                                | 단계      |
| --------- | ------------------------------------------------------------------------------------------------------------------- | --------- |
| transport | `apps/api/app/clients/kor_travel_map.py` (사용자 3경로)                                                             | T-365     |
| transport | `apps/api/app/clients/kor_travel_map_admin.py` `get_feature_weather`                                                | T-364/365 |
| 라우터    | `apps/api/app/api/v1/features.py` (`normalize_asof_query`, `_weather_from_kor_travel_map`)                          | T-362     |
| 라우터    | `apps/api/app/api/v1/admin/features.py` (weather-values, `asof` 422)                                                | T-364     |
| 서비스    | `apps/api/app/services/trip_view_builder.py` (`_weather_resolution`, 10초 예산, fanout)                             | T-363     |
| 스키마    | `apps/api/app/schemas/{feature,trip,admin}.py`                                                                      | T-362~364 |
| 스키마    | `packages/schemas/src/{feature,trip,admin}.ts` (Zod 미러 + partition superRefine)                                   | T-362~364 |
| client    | `packages/api-client/src/endpoints/{feature,admin}.ts`, `query-keys.ts`                                             | T-362/364 |
| web       | `apps/web/components/trips/TripWeatherSummary.tsx` (분류기 — §3.1-(3))                                              | T-362/363 |
| web       | `apps/web/components/map/FeatureMapView.tsx`, `vworldPrimitives.tsx` (§4.6)                                         | T-362     |
| web       | Admin weather-values 탭 `FeatureDetailSubpage.tsx`                                                                  | T-364     |
| e2e       | `apps/web/e2e/trip-detail.e2e.ts` (단건 weather 요청 0회 단언)                                                      | T-363     |
| e2e       | `trip-feature-resolution-live-mutating.live.ts` + `PINVI_LIVE_WEATHER_*` env                                        | T-363     |
| 런북      | `docs/runbooks/live-mutating-e2e.md` ("weather batch POST 정확히 1회" 게이트)                                       | T-363     |
| 계약      | `apps/api/tests/contract/kor-travel-map-openapi-*.json` (SHA-256 핀) + `tests/unit/test_kor_travel_map_contract.py` | T-365     |
| 설정      | `pinvi_kor_travel_map_*` / `pinvi_kor_travel_weather_*`, `.env.example`                                             | T-360/365 |

> `pinvi_kor_travel_map_service_token`은 **제거하지 않는다** — feature batch가 계속
> 쓴다. weather 경로에서만 빠진다.

### 4.5 영향 없음이 확인된 것

- **일출/일몰**: KASI 기반 Pinvi 자체 소유. 무관.
- **모바일**: `apps/mobile`에 날씨 코드가 **없다**. 이관 작업 없음.
- **공개 beach view**: `latest_weather`/`upcoming_index_forecasts`는 불투명
  passthrough라 소스 교체와 독립.

---

## 5. 단계 전환

되돌릴 수 있는 순서로 쪼갠다. 상세는 execplan.

| 단계 | 내용                                                            | 되돌리기        |
| ---- | --------------------------------------------------------------- | --------------- |
| P0   | 설계·계약 고정 (**본 문서 + ADR-068**)                          | 문서만          |
| P1   | client + DTO 생성 + 계약 테스트. 배선 없음                      | 코드 미사용     |
| P2   | `weather_location_links` + 해석기. feature flag `off`           | 테이블만        |
| P3   | 단건 weather 표면을 flag로 전환                                 | flag `off`      |
| P4   | Trip view 전환                                                  | flag `off`      |
| P5   | Admin weather-values 전환 (셰입 변경 동반 — §3.1-(2))           | flag `off`      |
| P7   | 처리방침 갱신 + 카드 출처 표기 — **G-2를 푸는 작업** (§7-2)     | 문서 + UI       |
| P6   | **G-1 · G-2 · G-3 해소 후** 기본값 `on` + map weather 소비 제거 | flag `off` 복귀 |

**G-1(커버리지) · G-2(처리방침) · G-3(보존)이 P6 진입 게이트**다. P1~P5는 세 게이트와
무관하게 진행 가능하다.

- **G-1 · G-3은 `kor-travel-weather` 소관** — Pinvi가 할 수 있는 건 요청과 가드뿐이다.
- **G-2는 Pinvi 소관**이며 P7(T-366)이 그 작업이다. 번호는 뒤지만 **P6보다 먼저**
  끝나야 한다.
- **G-3은 지금 바로 요청해 두는 편이 낫다** — 보존은 소급되지 않으므로 늦을수록
  잃는 과거 구간이 길어진다(§7-1).

---

## 6. 검증 게이트

- **A. 경계 테스트** — Pinvi가 provider 원천을 파싱하지 않음을 고정. 어휘 통합
  함수의 입력은 `WeatherValueOut`뿐이어야 한다.
- **B. 번들 회귀 테스트** — `source_location_ids` 전체를 합치지 않으면 실패하도록
  고정(§3.3). 서울 좌표에서 KMA 행이 0이면 실패.
- **C. 카드 파티션** — `weather_cards` 키 집합 == `found.card_key` 참조 집합.
  Pydantic + Zod 양쪽 유지.
- **D. 예산** — view당 10초, location fanout 동시성 상한, 부모 취소 전파.
- **E. 계약 스냅샷** — `kor-travel-weather` `openapi.json`을 vendored snapshot으로 두고
  드리프트를 CI에서 깬다(현재 `kor-travel-map`에 적용 중인 방식과 동일).
- **F. 커버리지 게이트(G-1)** — 표본 좌표 집합에서 KMA `forecast_style ∈
{nowcast, ultra_short, short}` 행이 임계치 이상일 때만 통과. **이 게이트가 cutover를
  기계적으로 막는다.**
- **G. e2e** — Playwright는 N150에서만(ADR-051). `trip-detail.e2e.ts`의 "단건 weather
  요청 0회" 단언과 `live-mutating-e2e.md`의 "weather batch POST 정확히 1회" 게이트는
  P4에서 **새 호출 모양으로 다시 쓴다**(삭제가 아니라 재정의).
- **H. 처리방침 정합(G-2)** — 표시되는 provider 집합이 `data-policy.md`의 위탁·국외이전
  기재와 일치하는지 확인. 비KMA provider가 표시 대상에 들어오면 처리방침 갱신 없이는
  통과하지 않는다. **출처 표기가 카드에 실제로 렌더되는지**도 함께 고정한다(§7-2 결정).
- **I. 보존 지평 가드(G-3)** — `kor-travel-weather`의 실효 보존이 **15일 미만**이면
  **실패**한다. 외부 설정 회귀로 과거 여행 날씨가 조용히 사라지는 것을 막는 유일한
  장치다(§4.2 대가 2). 배포 전(현재 2일)에는 항상 실패한다 — 의도된 동작이다.

---

## 7. 사용자 결정 (2026-09-17 확정)

### 7-1. 과거 날씨 정책 → **C: `kor-travel-weather` 보존 연장** ✅

Pinvi는 스냅샷 테이블을 **만들지 않는다.** 보존은 사실을 소유한 서비스가 진다.
게이트 **G-3**, 상세와 감수하는 대가는 §4.2.

가장 중요한 실무 함의: **소급되지 않는다.** 연장 시점 이전 여행의 날씨는 영구
소실이므로, 연장이 늦어질수록 잃는 구간이 길어진다. **G-1보다 먼저 요청해 둘수록
손실이 줄어든다** — 커버리지(G-1)를 기다리는 동안에도 보존(G-3)은 병행할 수 있다.

### 7-2. 상용 provider 표시 → **처리방침 갱신 후 표시 + 출처 명시** ✅

순서를 고정한다. 건너뛸 수 없다.

1. `docs/compliance/data-policy.md`의 "날씨: 기상청" 위탁 기재와 "국외 이전 의무 발생
   안 함" 선언을 실제 provider 구성에 맞게 재작성한다.
2. 카드에 **출처(provider)를 표시**하는 UI를 구현한다 — 사용자가 기상청 값과 상용 값을
   구분할 수 있어야 한다.
3. 그 뒤에야 비KMA provider 값을 표시한다.

→ **T-366**이 1·2를 소유한다(G-2 해소).

### 7-3. 남은 판단 — `kor-travel-map` 쪽 정합

**`kor-travel-map` ADR-062**는 "weather는 feature의 속성"이라고 결정했고 weather 투자가
진행 중이다(T-VN-38/39). Pinvi가 소비를 끊는 것은 map의 결정을 되돌리는 게 아니라
**소비자 하나가 빠지는 것**이다. 다만 map에 그 사실을 알려 중복 투자를 막을지 여부는
사용자 판단으로 남아 있다.

---

## 8. 참고

- 서비스 정본 문서: `kor-travel-weather` `docs/weather-api.md`,
  `docs/architecture/rest-api.md`, `docs/integration-map.md`
- **`kor-travel-weather` ADR**: 072(bitemporal), 089(fact 식별), 074(append-only),
  062(보존)
- Pinvi 현재 계약: [`kor-travel-map-rest-api.md`](kor-travel-map-rest-api.md) §2.6/2.6a/2.6b
- 결정: **Pinvi ADR-068** (`docs/decisions.md`)

> ⚠️ **ADR 번호는 저장소마다 독립이다.** 이 문서에는 세 저장소의 ADR이 등장하며
> `ADR-062`만 해도 셋이 서로 다르다 — Pinvi 062(동의 이력), `kor-travel-map`
> 062(weather 공개 API), `kor-travel-weather` 062(보존). **항상 저장소 이름을 앞에
> 붙여 적는다**(`AGENTS.md` 관례).

- 실행: [`docs/execplan/t-359-weather-source-cutover.md`](../execplan/t-359-weather-source-cutover.md)
