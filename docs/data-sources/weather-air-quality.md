# 날씨/대기질 데이터 소스

이 문서는 기상청(data.go.kr)과 AirKorea(data.go.kr) 연동을 인수인계하기 위한 상세 기준이다. 관련 구현은 `apps/api/app/etl/weather/client.py`, `apps/api/app/etl/weather/loader.py`, `apps/api/app/dagster_etl/registry.py`, `config/kma-mid-term-regions.json`이다.

## 공통 구현

| 항목 | 기상청 | AirKorea |
| --- | --- | --- |
| base URL | `http://apis.data.go.kr/1360000` | `http://apis.data.go.kr/B552584` |
| 인증 파라미터 | `ServiceKey` | `serviceKey` |
| 응답 타입 | `dataType=JSON` | `returnType=json` |
| pagination | `pageNo`, `numOfRows`, 최대 1000 row/page | `pageNo`, `numOfRows`, 최대 1000 row/page |
| timeout | 30초 | 30초 |
| raw 저장 | endpoint, 기준시각, request key, raw payload, response hash | endpoint, request key, raw payload, response hash |

공통 응답 wrapper:

- `response.header.resultCode/resultMsg`가 정상 코드가 아니면 실패 처리한다.
- `response.body.items.item`이 dict면 1건, list면 여러 건으로 해석한다.
- `totalCount`와 현재 누적 row 수를 비교해 pagination을 종료한다.

## 기상청 전국 해수욕장 날씨

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://www.data.go.kr/data/15102239/openapi.do` |
| 참고문서 ZIP | `https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000003562456&fileDetailSn=1` |
| API base URL | `http://apis.data.go.kr/1360000/BeachInfoservice` |
| 인증 파라미터 | `serviceKey` |
| 응답 타입 | `dataType=JSON` |
| 공식 갱신주기 표기 | data.go.kr 페이지는 `실시간`으로 표시한다. 서비스 설명은 초단기예보 1시간, 단기예보 3시간, 조석/일출일몰/파고/수온을 제공한다고 명시한다. |
| 확인일 | 2026-04-28 |
| 구현 파일 | `apps/api/app/etl/weather/beach.py`, `apps/api/app/dagster_etl/registry.py` |

TripMate dataset과 수집 주기:

| dataset | job | 수집 시각(KST) | 근거/패턴 |
| --- | --- | --- | --- |
| `kma_beach_catalog` | `kma_beach_catalog_annual` | 매년 5월 15일 04:00 | 참고문서 ZIP의 `위경도.xlsx`를 해수욕장 시즌 전 1회 갱신한다. |
| `kma_beach_ultra_short_forecast` | `kma_beach_ultra_short_forecast_hourly` | 6/7/8월 매시 45분 | 초단기예보 제공 간격 1시간에 맞춘다. 기준시각은 수집시각 -45분, 분은 00/30으로 내린다. |
| `kma_beach_village_forecast` | `kma_beach_village_forecast_3hourly` | 6/7/8월 02/05/08/11/14/17/20/23시 20분 | 단기예보 3시간 발표 패턴에 맞춘다. 기준시각은 수집시각 -20분 후 최근 발표시각이다. |
| `kma_beach_wave_height` | `kma_beach_wave_height_hourly` | 6/7/8월 매시 35분 | 관측성 파고 데이터는 `searchTime=YYYYMMDDHH00`로 직전 정시를 조회한다. |
| `kma_beach_water_temperature` | `kma_beach_water_temperature_hourly` | 6/7/8월 매시 40분 | 관측성 수온 데이터는 `searchTime=YYYYMMDDHH00`로 직전 정시를 조회한다. |
| `kma_beach_tide_sun` | `kma_beach_tide_sun_daily` | 6/7/8월 매일 05:10 | 조석은 활용가이드상 6~8월 제공이다. 일출/일몰은 일 단위 정보이므로 같은 일일 job에서 함께 수집한다. |

카탈로그 파일:

- 참고문서 ZIP 안의 `기상청48_전국해수욕장_날씨_조회서비스_위경도.xlsx`를 읽는다.
- 내부 확인 시 sheet header는 `순번`, `해수욕장`, `nx`, `ny`, `경도`, `위도`였다.
- 구현은 ZIP 안의 xlsx를 찾아 `xl/worksheets/sheet*.xml`과 `sharedStrings.xml`만 읽는 경량 parser를 사용한다.
- `순번`은 기상청 API의 `beach_num`으로 사용한다.
- `경도`, `위도`는 WGS84로 보고 `numeric(12,8)`과 PostGIS `POINT(4326)`으로 표준화한다.
- `nx`, `ny`는 기상청 DFS 격자로 그대로 보존한다.

주소/장소 저장:

- 카탈로그는 `places`와 `weather_beach_location`에 함께 저장한다.
- 법정동은 V-WORLD `region_serving_boundary`의 법정동 경계에 대해 `ST_Covers(geom, point)`로 먼저 판정한다. 해수욕장 좌표가 모래사장/해상 쪽에 있어 경계 밖으로 떨어지는 경우가 있어, 실패 시 약 5km(`0.05도`) 이내 가장 가까운 법정동 경계를 보조 매핑으로 사용하고 `address_mapping_method='postgis_nearest_boundary_5km'`로 남긴다.
- 도로명주소코드와 도로명주소관리번호는 원천 xlsx에 없으므로 좌표만으로 생성하지 않는다. 같은 법정동 안에서 `address_serving_juso_road_address.sigungu_building_name` 또는 `building_registry_name`이 해수욕장명과 정확히 1건 일치할 때만 `road_name_code`, `road_address_management_no`를 채운다.
- 일치하지 않으면 `road_name_code`, `road_address_management_no`는 null로 두고, `address_mapping_method='postgis_point_in_polygon'`과 `address_resolution_status='coordinate_only'`로 남긴다.
- 장소 카테고리는 `01050100`(`관광 > 자연명소 > 해수욕장`)을 사용한다.

Endpoint와 요청 파라미터:

| endpoint | 설명 | 필수 파라미터 | 옵션 파라미터 | TripMate 기준시각 |
| --- | --- | --- | --- | --- |
| `getUltraSrtFcstBeach` | 해수욕장 초단기예보 | `serviceKey`, `base_date`, `base_time`, `beach_num` | `numOfRows`, `pageNo`, `dataType` | 수집시각 -45분, `HH00` 또는 `HH30` |
| `getVilageFcstBeach` | 해수욕장 단기예보 | `serviceKey`, `base_date`, `base_time`, `beach_num` | `numOfRows`, `pageNo`, `dataType` | 수집시각 -20분 후 02/05/08/11/14/17/20/23시 중 최근값 |
| `getWhBuoyBeach` | 해수욕장 파고 | `serviceKey`, `beach_num`, `searchTime` | `numOfRows`, `pageNo`, `dataType` | 직전 정시 `YYYYMMDDHH00` |
| `getTwBuoyBeach` | 해수욕장 수온 | `serviceKey`, `beach_num`, `searchTime` | `numOfRows`, `pageNo`, `dataType` | 직전 정시 `YYYYMMDDHH00` |
| `getTideInfoBeach` | 해수욕장 조석 | `serviceKey`, `base_date`, `beach_num` | `numOfRows`, `pageNo`, `dataType` | 수집일 `YYYYMMDD` |
| `getSunInfoBeach` | 해수욕장 일출/일몰 | `serviceKey`, `Base_date`, `beach_num` | `numOfRows`, `pageNo`, `dataType` | 수집일 `YYYYMMDD`. Swagger의 요청 키 대소문자(`Base_date`)를 그대로 사용한다. |

공통 옵션:

| 이름 | 필수 | 구현값/설명 |
| --- | --- | --- |
| `serviceKey` | Y | `TRIPMATE_DATA_GO_SERVICE_KEY`. 로그, DB payload, 문서에 원문 저장 금지 |
| `dataType` | N | 구현은 `JSON` 고정 |
| `pageNo` | N | pagination 내부 자동 증가 |
| `numOfRows` | N | 구현상 최대 1000 |

출력 파라미터와 저장:

| endpoint | 출력 필드 | 저장/정규화 |
| --- | --- | --- |
| `getUltraSrtFcstBeach`, `getVilageFcstBeach` | `beachNum`, `baseDate`, `baseTime`, `category`, `fcstDate`, `fcstTime`, `fcstValue`, `nx`, `ny` | `weather_raw_beach`에 요청 단위 raw 저장, `weather_serving_beach`에 category별 row 저장. `category`는 기존 단기예보 category spec(`TMP`, `POP`, `SKY` 등)으로 `normalized_category`, `unit`을 보강한다. |
| `getWhBuoyBeach` | `beachNum`, `tm`, `wh` | category `WH`, `normalized_category='wave_height'`, unit `m`, `observed_at=tm` |
| `getTwBuoyBeach` | `beachNum`, `tm`, `tw` | category `TW`, `normalized_category='water_temperature'`, unit `deg_c`, `observed_at=tm` |
| `getTideInfoBeach` | `beachNum`, `baseDate`, `tiStnld`, `tiTime`, `tiType`, `tilevel` | category `TIDE`, `normalized_category='tide_level'`, unit `cm`, `station_name=tiStnld` |
| `getSunInfoBeach` | `beachNum`, `baseDate`, `sunrise`, `sunset` | `SUNRISE`, `SUNSET` 두 row로 펼쳐 저장한다. 값은 원문 시간 문자열로 보존하고 가능한 경우 KST `observed_at`도 채운다. |

파고/수온/조위/일출일몰 endpoint가 `-`, `:` 또는 빈 시각처럼 무자료 표시를 반환하면 원문은 `weather_raw_beach`에 남기되 `weather_serving_beach`에는 저장하지 않는다. 2026-04-30 정합성 점검에서 `getTideInfoBeach`, `getSunInfoBeach`가 전 해수욕장에 무자료 표시를 반환한 사례가 확인되어 조회용 serving 데이터에서 제외했다.

주요 저장 테이블:

- `weather_beach_location`: provider `kma`, `beach_num`, `map_feature_id`, `nx/ny`, EPSG:4326 좌표, 법정동/도로명주소 매핑, 원천 파일명/hash/row 번호를 저장한다.
- `weather_raw_beach`: endpoint, beach number, request params, response hash, 원문 payload, `collected_at`을 저장한다. 같은 응답 hash는 중복 저장하지 않는다.
- `weather_serving_beach`: 앱/API용 정규화 row다. unique 기준은 `provider + endpoint + beach_num + source_record_key + category_code`다.
- 해수욕장 날씨 serving row는 “해수욕장 1곳 = 1행”이 아니라 `해수욕장 × endpoint × category × forecast/observed time` 단위다. 단기예보 1회만으로도 대략 `해수욕장 수 × 14개 category × 3일 내외 시간 슬롯` 규모가 되므로 수십만 행이 정상 범위다.

운영 주의:

- 해수욕장 날씨 API는 전국 해수욕장 수만큼 반복 호출하므로 사용자 요청마다 직접 호출하지 않는다.
- 6~8월 외에는 기본 job가 동작하지 않는다. 비시즌 미리보기나 관리자 수동 재수집이 필요하면 Dagster에서 수동 trigger한다.
- 위치 카탈로그 다운로드는 인증키 없이 참고문서 ZIP을 받지만, 날씨 endpoint 호출은 data.go.kr service key를 외부로 전송한다.

## 기상청 단기/초단기 예보

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://www.data.go.kr/data/15084084/openapi.do` |
| 서비스 | 기상청 단기예보 조회서비스 |
| TripMate dataset | `weather_short_term` |
| job | `weather_short_term_sigungu_grid` |
| 수집 시각 | 30분마다 |
| 수집 범위 | `weather_short_term_grid_mapping`의 active 시군구 대표 격자 |

Endpoint와 구현 URL:

| endpoint | 구현 URL | 용도 |
| --- | --- | --- |
| `getUltraSrtNcst` | `/VilageFcstInfoService_2.0/getUltraSrtNcst` | 초단기실황 |
| `getUltraSrtFcst` | `/VilageFcstInfoService_2.0/getUltraSrtFcst` | 초단기예보 |
| `getVilageFcst` | `/VilageFcstInfoService_2.0/getVilageFcst` | 단기예보 |

요청 파라미터:

| 이름 | 필수 | 구현값/설명 |
| --- | --- | --- |
| `ServiceKey` | Y | `TRIPMATE_DATA_GO_SERVICE_KEY` |
| `dataType` | Y | `JSON` |
| `base_date` | Y | 자동 계산 또는 호출자 override, `YYYYMMDD` |
| `base_time` | Y | 자동 계산 또는 호출자 override, `HHMM` |
| `nx` | Y | 기상청 DFS X 격자 |
| `ny` | Y | 기상청 DFS Y 격자 |
| `pageNo` | 옵션 | pagination 내부 자동 증가 |
| `numOfRows` | 옵션 | 구현상 최대 1000 |

기준시각 계산:

| endpoint | 구현 기준 |
| --- | --- |
| `getUltraSrtNcst` | 현재 KST - 1시간, `HH00` |
| `getUltraSrtFcst` | 현재 KST - 45분, 분은 00 또는 30 |
| `getVilageFcst` | 현재 KST - 20분 후 02/05/08/11/14/17/20/23시 중 가장 최근 발표시각 |

출력 파라미터와 저장:

| 출력 필드 | 저장/사용 방식 |
| --- | --- |
| `baseDate`, `baseTime` | raw/serving 기준 발표시각 |
| `fcstDate`, `fcstTime` | 예보 대상시각. 실황은 없으면 base로 대체 |
| `category` | `POP`, `PCP`, `PTY`, `REH`, `RN1`, `SNO`, `T1H`, `TMP`, `TMN`, `TMX`, `UUU`, `VVV`, `VEC`, `WSD`, `SKY`, `LGT` 등 |
| `obsrValue`, `fcstValue` | 값. serving `value` |
| `nx`, `ny` | 요청 격자와 함께 저장 |

내부 정규화:

- WGS84 좌표는 `pykma.wgs84_to_kma_grid()`로 DFS 격자에 변환한다. TripMate에는 KMA용 adapter/gateway 래퍼를 두지 않고, 기상청 단기/중기/특보 data.go.kr 호출은 `pykma.KmaClient`와 `pykma.DataGoKrClient` 공개 API를 직접 사용한다.
- 시군구 대표 격자는 V-WORLD 시군구 경계의 `ST_PointOnSurface`를 사용한다.
- serving category는 `category_name`, `normalized_category`, `unit`으로 보강한다.

## 기상청 기상특보/정보/속보

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://www.data.go.kr/data/15000415/openapi.do` |
| TripMate dataset | `weather_kma_alert` |
| job | `weather_kma_alert` |
| 수집 시각 | 30분마다 |
| 조회 window | job logical date 기준으로 loader 호출 시 `from_date`, `to_date`를 넘긴다. |

Endpoint와 요청 파라미터:

| endpoint | 구현 URL | 필수 파라미터 | 설명 |
| --- | --- | --- | --- |
| `getWthrWrnList` | `/WthrWrnInfoService/getWthrWrnList` | `ServiceKey`, `dataType=JSON`, `fromTmFc`, `toTmFc` | 기상특보 |
| `getWthrInfoList` | `/WthrWrnInfoService/getWthrInfoList` | 동일 | 기상정보 |
| `getWthrBrkNewsList` | `/WthrWrnInfoService/getWthrBrkNewsList` | 동일 | 기상속보 |

출력 파라미터와 저장:

| 출력 필드 | 저장/사용 방식 |
| --- | --- |
| `stnId` | 특보구역/발표기관 코드. `weather_kma_alert_station_code`에도 upsert |
| `stnNm` | station name 보강 |
| `title` | serving title |
| `tmFc` | 발표시각 |
| `tmSeq` | 발표 sequence |
| 기타 원문 | `raw_payload` 보존 |

## 기상청 중기예보

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://www.data.go.kr/data/15059468/openapi.do` |
| TripMate dataset | `weather_mid_term` |
| job | `weather_mid_term_nationwide` |
| 수집 시각 | 매일 06:20, 18:20 KST |
| region 기준 | `config/kma-mid-term-regions.json` |

Endpoint와 요청 파라미터:

| endpoint | 구현 URL | 필수 파라미터 | 설명 |
| --- | --- | --- | --- |
| `getMidFcst` | `/MidFcstInfoService/getMidFcst` | `ServiceKey`, `dataType=JSON`, `stnId`, `tmFc` | 전국/권역 중기 전망 |
| `getMidLandFcst` | `/MidFcstInfoService/getMidLandFcst` | `ServiceKey`, `dataType=JSON`, `regId`, `tmFc` | 육상 중기예보 |
| `getMidTa` | `/MidFcstInfoService/getMidTa` | `ServiceKey`, `dataType=JSON`, `regId`, `tmFc` | 중기 기온 |

옵션/자동 계산:

| 이름 | 구현 방식 |
| --- | --- |
| `tmFc` | 현재 KST - 40분 기준. 06시 이후 `YYYYMMDD0600`, 18시 이후 `YYYYMMDD1800`, 새벽이면 전일 18시 |
| `pageNo`, `numOfRows` | pagination 내부 자동 처리 |

출력 파라미터와 저장:

| 출력 필드 | 저장/사용 방식 |
| --- | --- |
| `tmFc` | 발표시각 |
| `wfSv` | 중기 전망 요약 |
| `wf3Am`/`wf3Pm` ... `wf10` | 예보 slot별 날씨 요약 |
| `rnSt3Am`/`rnSt3Pm` ... `rnSt10` | 예보 slot별 강수확률 |
| `taMin3` ... `taMin10`, `taMax3` ... `taMax10` | 최저/최고 기온 |
| region config | `region_kind`, `provider_region_id`, `region_name`, 주소 매핑 우선순위 |

구현 메모:

- 중기예보 `regId`는 법정동코드나 DFS grid가 아니라 기상청 예보구역코드다.
- TripMate 주소 코드와의 연결은 `weather_mid_region_address_mapping`에 별도 저장한다.

## AirKorea 측정소 목록

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://www.data.go.kr/data/15073877/openapi.do` |
| TripMate dataset | `air_quality_station` |
| job | `air_quality_station_daily` |
| 수집 시각 | 매일 04:20 KST |
| 수집 범위 | 서울, 부산, 대구, 인천, 광주, 대전, 울산, 세종, 경기, 강원, 충북, 충남, 전북, 전남, 경북, 경남, 제주 |

요청 파라미터:

| 이름 | 필수 | 구현값/설명 |
| --- | --- | --- |
| `serviceKey` | Y | `TRIPMATE_DATA_GO_SERVICE_KEY` |
| `returnType` | Y | `json` |
| `addr` | 옵션 | 시도명. 구현은 시도별 반복 호출 |
| `pageNo`, `numOfRows` | 옵션 | pagination 내부 처리 |

출력 파라미터:

| 출력 필드 | 저장/사용 방식 |
| --- | --- |
| `stationName` | 측정소명, required |
| `mangName` | 측정망명 |
| `addr` | 주소, required |
| `dmX`, `dmY` | 구현 smoke 기준 `dmX=위도`, `dmY=경도`로 해석 |
| `item` | 측정항목 |
| `year` | 설치년도 |

내부 구현:

- `dmY`, `dmX`로 EPSG:4326 point를 만들고 V-WORLD 법정동 경계 `ST_Covers`로 매핑한다.
- 매핑 실패 시 serving `mapping_method='unmapped'`로 남긴다.

## AirKorea 미세먼지/오존 예보통보

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://www.data.go.kr/data/15073861/openapi.do` |
| TripMate dataset | `air_quality_forecast` |
| job | `air_quality_forecast_daily` |
| 수집 시각 | 매일 05:15, 11:15, 17:15, 23:15 KST |
| 수집 코드 | `PM10`, `PM25`, `O3` |

요청 파라미터:

| 이름 | 필수 | 구현값/설명 |
| --- | --- | --- |
| `serviceKey` | Y | `TRIPMATE_DATA_GO_SERVICE_KEY` |
| `returnType` | Y | `json` |
| `InformCode` | 옵션 | 구현은 `PM10`, `PM25`, `O3` 반복 |
| `pageNo`, `numOfRows` | 옵션 | pagination 내부 처리 |

출력 파라미터:

| 출력 필드 | 저장/사용 방식 |
| --- | --- |
| `informCode` | 예보 항목. 없으면 요청 `InformCode` 사용 |
| `dataTime` | 발표시각. 없으면 수집시각 isoformat |
| `informData` | 예보 날짜 |
| `informOverall` | 종합 예보 문구 |
| `informCause` | 발생 원인 |
| `informGrade` | 권역별 등급 |
| `actionKnack` | 행동요령 |

## AirKorea 시도별 실시간 측정값

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://www.data.go.kr/data/15073861/openapi.do` |
| TripMate dataset | `air_quality_sido_measurement` |
| job | `air_quality_sido_measurement_hourly` |
| 수집 시각 | 매시 25분 |

요청 파라미터:

| 이름 | 필수 | 구현값/설명 |
| --- | --- | --- |
| `serviceKey` | Y | `TRIPMATE_DATA_GO_SERVICE_KEY` |
| `returnType` | Y | `json` |
| `sidoName` | Y | 시도명 반복 |
| `ver` | Y | `1.3` |
| `pageNo`, `numOfRows` | 옵션 | pagination 내부 처리 |

출력 파라미터:

| 출력 필드 | 저장/사용 방식 |
| --- | --- |
| `stationName` | 측정소명, required |
| `dataTime` | 측정시각, required |
| `mangName` | 측정망명 |
| `khaiValue`, `khaiGrade` | 통합대기환경 수치/등급 |
| `pm10Value`, `pm10Grade`, `pm10Flag` | PM10 |
| `pm25Value`, `pm25Grade`, `pm25Flag` | PM2.5 |
| `no2Value`, `no2Grade`, `no2Flag` | NO2 |
| `o3Value`, `o3Grade`, `o3Flag` | O3 |
| `coValue`, `coGrade`, `coFlag` | CO |
| `so2Value`, `so2Grade`, `so2Flag` | SO2 |

운영 주의:

- AirKorea 호출 한도는 낮게 잡고 실패 retry가 반복되면 job 주기를 완화한다.
- 대기질 측정값은 실시간성 데이터라 UI는 stale 표시를 해야 한다.
