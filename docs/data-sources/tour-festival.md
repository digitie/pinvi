# 관광/축제 데이터 소스

이 문서는 기상청 관광코스와 전국문화축제표준데이터 인수인계 기준이다. 관련 구현은 `apps/api/app/etl/tour/*`, `apps/api/app/etl/weather/client.py`, `dags/weather_air_quality.py`, `dags/public_cultural_festival.py`다.

## 기상청 추천 관광코스 CSV

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://www.data.go.kr/data/15056912/openapi.do` |
| 참고 문서 | `https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000002889827&fileDetailSn=1` |
| 원천 파일 | `기상청27_관광코스별_관광지_상세설명서.zip` 내부 `기상청27_관광코스별_관광지_지점정보.csv` |
| 구현 방식 | 자동 다운로드 없음. `TRIPMATE_KMA_TOUR_COURSE_SOURCE_PATH`에 배치한 CSV/ZIP을 적재 |
| DAG | `kma_recommended_tour_course_annual` |
| 수집 시각 | 매년 3월 1일 05:00 KST |

CSV 출력 필드:

| 필드 | 필수 | 저장/사용 방식 |
| --- | --- | --- |
| `테마분류` | Y | `TH01`-`TH05`, 내부 `theme_category` 매핑 |
| `코스 아이디` | Y | `course_id` |
| `관광지 아이디` | Y | `spot_id` |
| `지역 아이디` | 옵션 | provider region id |
| `관광지명` | Y | `spot_name` |
| `경도(도)`, `위도(도)` | Y | EPSG:4326 좌표 |
| `코스순서` | 옵션 | 정렬 |
| `이동시간` | 옵션 | 분 단위 정수 |
| `실내구분` | 옵션 | 실내/실외 |
| `테마명` | 옵션 | provider theme name |

내부 구현:

- encoding은 `cp949`, `ms949`, `utf-8-sig` 순서로 시도한다.
- raw는 `tour_course_raw_kma_point`, serving은 `kma_recommended_tour_course`에 저장한다.
- 좌표가 있으면 V-WORLD 법정동 경계 `ST_Covers`로 `legal_dong_code`, `sigungu_code`, `sido_code`를 채운다.
- V-WORLD reverse geocoding과 Juso 상세 주소 key 매핑은 사용하지 않는다.
- `theme_category` 매핑: `TH01 nature`, `TH02 culture_art`, `TH03 leisure`, `TH04 food`, `TH05 history_tradition`, 그 외 `unknown`.

## 기상청 관광코스별 상세 날씨

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://www.data.go.kr/data/15056912/openapi.do` |
| base URL | `http://apis.data.go.kr/1360000` |
| 구현 URL | `/TourStnInfoService1/getTourStnVilageFcst1` |
| TripMate 호출 | 사용자 저장 장소/여행 장소 주변 관광코스 cache 갱신 시 호출 |
| endpoint label | `getTourStnVilageFcst1` |

요청 파라미터:

| 이름 | 필수 | 구현값/설명 |
| --- | --- | --- |
| `ServiceKey` | Y | `TRIPMATE_DATA_GO_SERVICE_KEY` |
| `dataType` | Y | `JSON` |
| `CURRENT_DATE` | Y | 자동 계산 또는 override, `YYYYMMDD` |
| `HOUR` | Y | 자동 계산 또는 override, KST 현재 - 1시간의 `HH` |
| `COURSE_ID` | Y | KMA 관광코스 `course_id` |
| `pageNo`, `numOfRows` | 옵션 | pagination 내부 처리 |

출력 파라미터:

| 출력 필드 | 저장/사용 방식 |
| --- | --- |
| `spotId`, `spot_id`, `tourSpotId` | 관광지 id fallback |
| `category`, `categoryCode` | 날씨 category |
| `baseDate`, `baseTime` | 발표시각 |
| `fcstDate`, `fcstTime` | 예보 대상시각 |
| `fcstValue`, `obsrValue` | 값 |

category 정규화:

| code | 이름 | 내부 category | 단위 |
| --- | --- | --- | --- |
| `POP` | 강수확률 | `rain_probability` | `%` |
| `PTY` | 강수형태 | `precipitation_type` | 없음 |
| `PCP` | 강수량 | `precipitation` | `mm` |
| `REH` | 습도 | `humidity` | `%` |
| `SKY` | 하늘상태 | `sky` | 없음 |
| `TMP` | 기온 | `temperature` | `deg_c` |
| `TMN` | 일 최저기온 | `temperature_min` | `deg_c` |
| `TMX` | 일 최고기온 | `temperature_max` | `deg_c` |
| `WSD` | 풍속 | `wind_speed` | `m/s` |

## 전국문화축제표준데이터

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://www.data.go.kr/data/15013104/standard.do` |
| base URL | `https://api.data.go.kr/openapi` |
| 구현 URL | `https://api.data.go.kr/openapi/tn_pubr_public_cltur_fstvl_api` |
| TripMate dataset | `public_cultural_festival` |
| DAG | `public_cultural_festival_quarterly` |
| 공식 갱신 | 분기. 공공데이터포털 확인일 2026-04-28 기준 `갱신주기: 분기`, `수정일: 2026-02-10` |
| 병합 패턴 | 포털 안내상 개별 기관 데이터는 매월 초 전국 단위로 병합되며, 시점에 따라 일부 시차가 있다 |
| 수집 시각 | 2/5/8/11월 12일 04:35 KST |
| page size | 500 |

수집 주기 결정:

- 포털의 공식 갱신주기는 분기이므로 매월 full refresh하지 않는다.
- 포털이 개별 기관 데이터를 매월 초 병합한다고 안내하므로, 분기 첫 달의 초반 병합과 수정일 지연을 피하기 위해 2/5/8/11월 12일 새벽으로 둔다.
- 현재 포털 수정일이 2026-02-10인 점을 감안하면 12일 실행은 10일 전후 반영 지연을 흡수하기 위한 보수적인 기준이다.
- freshness target은 93일(`133920`분)로 두어 분기 갱신이 1~2일 늦어져도 즉시 장애로 보지 않는다.
- 로그인 화면과 지도는 ETL serving cache만 조회하고, 사용자 요청 때 data.go.kr API를 직접 호출하지 않는다.

요청 파라미터:

| 이름 | 필수 | 구현값/설명 |
| --- | --- | --- |
| `serviceKey` | Y | `TRIPMATE_DATA_GO_SERVICE_KEY` |
| `pageNo` | Y | 1부터 자동 증가 |
| `numOfRows` | Y | 500 |
| `type` | Y | `json` |

출력 파라미터와 저장:

| 출력 필드 | 저장/사용 방식 |
| --- | --- |
| `fstvlNm`/`축제명` | festival name, required |
| `fstvlStartDate`/`축제시작일자`, `fstvlEndDate`/`축제종료일자` | 행사 기간, status 계산 |
| `opar`/`개최장소` | venue |
| `fstvlCo`/`축제내용` | content |
| `mnnstNm`, `auspcInsttNm`, `suprtInsttNm` | 주관/주최/후원 |
| `phoneNumber` | 전화 |
| `homepageUrl` | URL 정규화 |
| `relateInfo` | 관련정보 |
| `rdnmadr`, `lnmadr` | 도로명/지번 주소 |
| `longitude`, `latitude` | 좌표 |
| `instt_code`, `instt_nm` | 제공기관 |
| `referenceDate` | 데이터기준일자 |

내부 구현:

- `source_record_id`는 축제명, 기간, 장소, 주소, 제공기관코드를 SHA-1 hash로 만든다.
- raw는 `tour_raw_public_cultural_festival`, serving은 `tour_serving_public_cultural_festival`에 저장한다.
- 공공데이터 응답 안에서 같은 `source_record_id`가 중복될 수 있으므로 한 번의 fetch 안에서는 마지막 row만 serving 적재 대상으로 삼고, `duplicate_row_count`로 기록한다.
- 주소 매핑 우선순위는 Juso 도로명 exact, Juso 지번 exact, V-WORLD 법정동 point-in-polygon 순서다.
- fuzzy address matching은 하지 않는다.
