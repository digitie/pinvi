# 한국도로공사 휴게소 데이터 소스

이 문서는 한국도로공사 OpenAPI 인수인계 기준이다. 관련 구현은 `apps/api/app/core/kex.py`, `apps/api/app/etl/rest_area/loader.py`, `apps/api/app/dagster_etl/registry.py`, `docs/architecture/rest-area-schema.md`다.

## 공통

| 항목 | 내용 |
| --- | --- |
| base URL | `https://data.ex.co.kr/openapi` |
| 인증 파라미터 | `key` |
| 응답 타입 | `type=json` |
| 호출 라이브러리 | `pykex`의 `KexClient` 직접 사용 |
| 환경변수 | `TRIPMATE_KEX_EX_API_KEY`, fallback `TRIPMATE_EXPRESSWAY_API_KEY` |
| timeout | `TRIPMATE_KEX_TIMEOUT_SECONDS`, 기본 10초 |
| page size | `pykex` 호출당 최대 1000 |
| pagination guard | 1000 page |
| 응답 row | root `list` |
| 실패 처리 | `pykex`가 한국도로공사 오류 코드를 예외로 분류 |

공통 요청 파라미터:

| 이름 | 필수 | 구현값/설명 |
| --- | --- | --- |
| `key` | Y | `KexClient`가 한국도로공사 API key로 주입 |
| `type` | Y | `json` |
| `numOfRows` | Y | 최대 1000 |
| `pageNo` | Y | 1부터 자동 증가 |

## `rest_area_master`

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://data.ex.co.kr/openapi/basicinfo/openApiInfoM?apiId=0615` |
| 공공데이터포털 | `https://www.data.go.kr/data/15062047/openapi.do` |
| 구현 URL | `https://data.ex.co.kr/openapi/business/serviceAreaRoute` |
| job | `rest_area_master_monthly` |
| 수집 시각 | 매월 1일 04:10 KST |
| source API id | `0615` |

출력 파라미터:

| 출력 필드 | 저장/사용 방식 |
| --- | --- |
| `serviceAreaCode2` | TripMate 휴게소 안정 join key `svar_cd` |
| `serviceAreaName` | 휴게소명, required |
| `serviceAreaCode` | provider 보조 code |
| `direction` | 방향 |
| `routeCode`, `routeName` | 노선 코드/명 |
| `svarAddr` | 주소 |
| `brand` | 브랜드 |
| `convenience` | 편의시설 원문 |
| `telNo` | 전화번호 |
| `maintenanceYn`, `truckSaYn` | 정비/화물차 관련 여부 |
| `batchMenu` | 대표 음식 |
| `xValue`, `yValue` | 경도/위도 후보. EPSG:4326으로 간주해 저장 |

내부 구현:

- 매 수집 시 기존 serving master를 비활성화한 뒤 이번 snapshot row를 upsert한다.
- raw는 `rest_area_raw_master`, serving은 `rest_area_serving_master`에 저장한다.
- `serviceAreaCode2` 또는 `serviceAreaName`이 없으면 serving에서 skip한다.

## `rest_area_oil_price`

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://data.ex.co.kr/openapi/basicinfo/openApiInfoM?apiId=0312` |
| 구현 URL | `https://data.ex.co.kr/openapi/business/curStateStation` |
| job | `rest_area_oil_price_daily` |
| 수집 시각 | 매일 06:10, 18:10 KST |
| source API id | `0312` |

출력 파라미터:

| 출력 필드 | 저장/사용 방식 |
| --- | --- |
| `serviceAreaCode2` | master FK. 없거나 master에 없으면 serving skip |
| `serviceAreaCode` | provider 보조 code |
| `serviceAreaName` | 주유소/휴게소명 |
| `routeCode`, `routeName`, `direction` | 노선/방향 |
| `oilCompany` | 정유사 |
| `lpgYn` | LPG 여부 |
| `gasolinePrice` | 휘발유 가격 |
| `diselPrice` | 경유 가격. provider 오탈자 `disel` 그대로 사용 |
| `lpgPrice` | LPG 가격 |

내부 구현:

- raw는 `rest_area_raw_oil_price`에 항상 저장한다.
- serving은 master FK가 맞는 row만 `rest_area_serving_oil_price`에 유종별로 펼쳐 저장한다.
- 가격 단위는 `KRW_PER_LITER`다.
- master FK 불일치는 JSONL 로그로 남긴다. 기본 경로는 `/opt/tripmate/.tmp/dagster-logs/etl/rest_area_fk_mismatch`다.
- 2026-04-26 live smoke 기준 `curStateStation`의 `serviceAreaCode2`가 master와 교집합이 없는 문제가 관측되어 raw 보존 + serving skip 정책을 유지한다.

## `rest_area_svcs`

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://data.ex.co.kr/openapi/basicinfo/openApiInfoM?apiId=0316` |
| 구현 URL | `https://data.ex.co.kr/openapi/business/conveniServiceArea` |
| job | `rest_area_service_monthly` |
| 수집 시각 | 매월 1일 04:30 KST |
| source API id | `0316` |

출력 파라미터:

| 출력 필드 | 저장/사용 방식 |
| --- | --- |
| `serviceAreaCode2` | master FK. 없거나 master에 없으면 serving skip |
| `serviceAreaCode` | provider 보조 code |
| `routeCode`, `routeName`, `direction` | 노선/방향 |
| `convenience` | 편의시설 문자열. 구분자로 나누어 service row 생성 |

내부 구현:

- raw는 `rest_area_raw_service`에 저장한다.
- serving은 `rest_area_serving_service`에 편의시설 단위로 펼쳐 저장한다.
- 같은 snapshot date의 기존 service serving row는 삭제 후 재생성한다.
- master FK 불일치는 oil price와 같은 JSONL 정책을 따른다.

## 휴게소 날씨 후보

- 한국도로공사 휴게소별 날씨 API는 문서화 후보로 남아 있다.
- 설명 URL: `https://data.ex.co.kr/openapi/basicinfo/openApiInfoM?apiId=0508`
- 현재 TripMate 구현은 이 API를 호출하지 않는다.
