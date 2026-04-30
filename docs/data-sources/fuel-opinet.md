# OpiNet 유가 데이터 소스

이 문서는 OpiNet 유가 API 인수인계 기준이다. 관련 구현은 `apps/api/app/etl/opinet/client.py`, `apps/api/app/etl/opinet/loader.py`, `dags/opinet_fuel.py`, `docs/architecture/fuel-schema.md`, `docs/architecture/opinet-region-mapping.md`다.

## 공통

| 항목 | 내용 |
| --- | --- |
| base URL | `https://www.opinet.co.kr/api` |
| 인증 파라미터 | `certkey` |
| 응답 타입 | `out=json` |
| 환경변수 | `TRIPMATE_OPINET_API_KEY` |
| timeout | 30초 |
| 응답 root | `RESULT.OIL` |
| raw 저장 | endpoint, provider region/fuel code, raw payload, response hash, collected_at |

지원 유종:

| provider code | provider name | 내부 `fuel_type` |
| --- | --- | --- |
| `B027` | 휘발유 | `gasoline` |
| `B034` | 고급휘발유 | `premium_gasoline` |
| `D047` | 경유 | `diesel` |
| `K015` | LPG | `lpg` |

## `fuel_region_code`

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://www.opinet.co.kr/user/custapi/openApiInfoDtl.do?apiId=5` |
| 구현 URL | `https://www.opinet.co.kr/api/areaCode.do` |
| DAG | `opinet_region_code_quarterly` |
| 수집 시각 | 1/4/7/10월 1일 04:00 KST |
| 목적 | OpiNet 시도/시군구 provider code를 TripMate 법정동 시도/시군구 코드와 매핑 |

요청 파라미터:

| 이름 | 필수 | 구현값/설명 |
| --- | --- | --- |
| `certkey` | Y | OpiNet API key |
| `out` | Y | `json` |
| `area` | 옵션 | 없으면 시도 목록, 있으면 해당 시도의 시군구 목록 |

출력 파라미터:

| 출력 필드 | 저장/사용 방식 |
| --- | --- |
| `AREA_CD` | provider region code |
| `AREA_NM` | provider region name |

내부 구현:

- 1차로 `area` 없이 시도 목록을 받고, 각 시도 `AREA_CD`로 시군구 목록을 다시 조회한다.
- `fuel_raw_opinet_region_code`에 원문 row를 보존한다.
- `fuel_serving_opinet_region_code`에는 `provider_region_code`, `provider_region_name`, `region_level`, `parent_provider_region_code`, `address_code_standard_code`, `mapping_status`, `confidence`를 저장한다.
- 지역명 정규화와 `address_code_standard`를 사용해 provider code를 법정동 시도/시군구 코드에 연결한다.

## `fuel_avg_price`

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://www.opinet.co.kr/user/custapi/openApiInfoDtl.do?apiId=4` |
| 구현 URL | `https://www.opinet.co.kr/api/avgAllPrice.do` |
| DAG | `opinet_avg_price_daily` |
| 수집 시각 | 매일 05:20, 13:20, 21:20 KST |
| 목적 | 전국 평균 유가 snapshot |

요청 파라미터:

| 이름 | 필수 | 구현값/설명 |
| --- | --- | --- |
| `certkey` | Y | OpiNet API key |
| `out` | Y | `json` |

출력 파라미터:

| 출력 필드 | 저장/사용 방식 |
| --- | --- |
| `PRODCD` | 유종 code. 지원 유종만 serving 반영 |
| `PRICE` | 평균 가격, `KRW_PER_LITER` |
| `TRADE_DT` | 거래/기준일. 없으면 수집시각의 KST 날짜 |
| `DIFF` | 전일/전회 대비 차이 |

내부 구현:

- raw는 `fuel_raw_avg_price`에 저장한다.
- serving은 `region_key='national'`, `fuel_type`, `trade_date` 기준으로 upsert한다.
- `TRADE_DT`가 없으면 `collected_at`에서 `YYYYMMDD`를 만들고, timestamp도 수집시각으로 둔다.

## `fuel_lowest_station`

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://www.opinet.co.kr/user/custapi/openApiInfoDtl.do?apiId=2` |
| 구현 URL | `https://www.opinet.co.kr/api/lowTop10.do` |
| DAG | `opinet_lowest_station_daily` |
| 수집 시각 | 매일 05:40, 13:40, 21:40 KST |
| 목적 | 매핑된 전국 시군구별 최저가 주유소 후보 cache |

요청 파라미터:

| 이름 | 필수 | 구현값/설명 |
| --- | --- | --- |
| `certkey` | Y | OpiNet API key |
| `out` | Y | `json` |
| `area` | Y | OpiNet 시군구 provider code |
| `prodcd` | Y | `B027`, `B034`, `D047`, `K015` |
| `cnt` | Y | 기본 20 |

출력 파라미터:

| 출력 필드 | 저장/사용 방식 |
| --- | --- |
| `PRICE` | 가격, required |
| `UNI_ID` | station id 후보 1순위 |
| `OS_NM` | 주유소명, station id fallback 후보 |
| `POLL_DIV_CD` | 상표/폴 code |
| `VAN_ADR` | 지번 주소 |
| `NEW_ADR` | 도로명 주소 |
| `GIS_X_COOR`, `GIS_Y_COOR` | provider 좌표 원문. 현재 좌표계 변환/지도 표시는 확정하지 않음 |

내부 구현:

- 수집 대상 시군구는 `fuel_serving_opinet_region_code`에서 매핑 성공한 provider code 목록이다.
- `station_id`는 `UNI_ID`, `OS_NM`, `VAN_ADR`, `NEW_ADR`, raw hash 순서로 fallback한다.
- serving은 `provider_region_code + fuel_type + station_id` 기준으로 upsert한다.
- OpiNet 좌표는 원문 보존만 하고, TripMate 표준 장소 좌표로 승격하지 않는다.

## 실패/보안 처리

- API key가 없으면 provider 호출 전에 명시적으로 실패한다.
- 실패 로그와 Telegram outbox에는 `certkey` 원문을 남기지 않는다.
- 사용자 화면은 serving cache를 조회해야 하며, 사용자 요청마다 OpiNet을 직접 호출하지 않는다.
