# 공공 장소 데이터 소스

이 문서는 공공데이터포털/LocalData 기반 표준 장소 적재 인수인계 기준이다. 관련 구현은 `apps/api/app/etl/places/public_data_places.py`, `apps/api/app/dagster_etl/registry.py`, `docs/architecture/public-place-etl-schema.md`, `docs/architecture/place-schema.md`다.

## 공통 적재 방식

| 항목 | 내용 |
| --- | --- |
| 표준 OpenAPI base URL | `https://api.data.go.kr/openapi` |
| 표준 OpenAPI 공통 파라미터 | `serviceKey`, `pageNo`, `numOfRows`, `type=json` |
| page size | 표준 API 1000 |
| file page 방식 | data.go.kr HTML에서 `contentUrl`을 찾아 CSV/ZIP 다운로드 |
| Go Camping 방식 | `http://apis.data.go.kr/B551011/GoCamping/basedList` 직접 호출 |
| localdata 방식 | 과거 고정 CSV URL 직접 다운로드 방식. 2026-04-29부터 기본 수집 경로에서 제외 |
| raw 저장 | `source_records`에 dataset key, provider, source_entity_id, raw payload hash |
| 표준 장소 | `map_features`, `place_details`, `map_feature_provider_refs`, `map_feature_source_links`, `map_feature_web_links` |
| 좌표 기준 | EPSG:4326 `longitude`, `latitude`; 과거 LocalData CSV 일부 TM 좌표는 EPSG:5174에서 변환 가능 |

공통 필수 출력 필드:

| 내부 후보 필드 | 설명 |
| --- | --- |
| `name` | 장소명. 없으면 row skip |
| `longitude`, `latitude` | 좌표. 둘 다 없으면 row skip |
| `road_address` 또는 `jibun_address` | 주소 snapshot. 둘 다 없어도 좌표가 있으면 장소 생성 가능 |
| `source_record_id` | provider id가 있으면 사용, 없으면 dataset/name/address/좌표/provider code hash |

공통 정규화:

- HTML tag 제거, HTML entity decode, 공백 collapse를 적용한다.
- `homepage_url`은 scheme이 없고 도메인처럼 보이면 `https://`를 붙인다.
- 좌표가 있으면 V-WORLD 법정동 경계 `ST_Covers`로 `legal_dong_code`, `sigungu_code`, `sido_code`를 채운다.
- 운영상태가 `closed`면 `is_searchable=false`, `is_map_visible=false`로 둔다.
- source-specific long-tail 필드는 `place_details.extra`에 둔다.

인증:

- Go Camping, 전국문화축제표준데이터, 전국관광안내소표준데이터, 전국휴양림표준데이터, 전국박물관미술관정보표준데이터는 모두 `TRIPMATE_DATA_GO_SERVICE_KEY`를 사용한다.
- 2026-04-29에 운영자가 제공한 data.go.kr 인증키를 로컬 `.env`와 `apps/api/.env`에 반영했다. 인증키 원문은 Git, 문서, 로그에 저장하지 않는다.
- 표준 OpenAPI는 정상 키에서도 간헐적 TCP reset이 관측됐다. 구현은 요청 단위 짧은 retry 후 실패를 Dagster retry로 넘긴다.

## `public_arboretum_basic`

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://www.data.go.kr/data/15109934/fileData.do?recommendDataYn=Y` |
| source mode | `data_go_file_page` |
| 구현 다운로드 | 설명 페이지 HTML의 `contentUrl` |
| job | `public_arboretum_basic_annual` |
| 공식 갱신 | 저빈도 파일 데이터 |
| TripMate 수집 | 매년 7월 5일 04:05 KST |
| override | `TRIPMATE_ARBORETUM_BASIC_CSV_PATH` 또는 `TRIPMATE_ARBORETUM_BASIC_CSV_URL`이 있으면 그 값을 우선 사용 |

요청 파라미터:

| 이름 | 필수 | 구현값/설명 |
| --- | --- | --- |
| data.go.kr file query | provider | `contentUrl`에 포함된 query 그대로 사용 |
| `serviceKey` | 조건부 | 현재 일반 file page client는 별도 추가하지 않음. 필요 시 source URL 자체에 포함 |

출력 파라미터:

| 후보 필드 | 저장/사용 방식 |
| --- | --- |
| `수목원아이디`, `arboretumId` | source id 후보 |
| `수목원명`, `arboretumNm`, `name`, `명칭` | 장소명 |
| `전체주소`, `주소`, `소재지도로명주소`, `roadAddress`, `rdnmadr` | 도로명 주소 |
| `소재지지번주소`, `jibunAddress`, `lnmadr` | 지번 주소 |
| `경도`, `longitude`, `lon`, `lng` | 경도 |
| `위도`, `latitude`, `lat` | 위도 |
| `전화번호`, `대표전화`, `연락처`, `telephoneNumber` | 전화 |
| `홈페이지`, `홈페이지주소`, `홈페이지 URL`, `homepageUrl` | 웹 링크 |
| `수목원구분`, `운영주체`, `설립구분`, `구분` | 카테고리 세분화 |
| `데이터기준일자`, `referenceDate`, `기준일자` | source version |
| `입장료`, `개관일`, `휴관일`, `대표수종`, `교육체험프로그램` | source-specific attributes |

카테고리:

| 조건 | category |
| --- | --- |
| 국립 | `01030101` |
| 공립/시립/도립/군립/구립/공영 | `01030102` |
| 사립/사유/민간 | `01030103` |
| 기본 | `01030100` |

## `public_tourist_information_center`

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://www.data.go.kr/data/15013112/standard.do` |
| 구현 URL | `https://api.data.go.kr/openapi/tn_pubr_public_trsmic_api` |
| source mode | `data_go_standard_api` |
| job | `public_tourist_information_center_annual` |
| 공식 갱신 | 연간. 개별 기관 파일은 월초 병합으로 시차가 있을 수 있음 |
| TripMate 수집 | 매년 7월 5일 04:10 KST |

요청 파라미터:

| 이름 | 필수 | 구현값 |
| --- | --- | --- |
| `serviceKey` | Y | `TRIPMATE_DATA_GO_SERVICE_KEY` |
| `pageNo` | Y | 자동 증가 |
| `numOfRows` | Y | 1000 |
| `type` | Y | `json` |

출력 파라미터:

| 필드 | 저장/사용 방식 |
| --- | --- |
| `trsmicNm`, `관광안내소명` | 장소명 |
| `trsmicLcNm`, `안내소위치명` | 위치 설명, source-specific attributes |
| `ctprvnNm`, `시도명`; `signguNm`, `시군구명` | 원천 지역명, source-specific attributes |
| `trsmicIntrcn`, `안내소소개` | source-specific attributes |
| `additServiceInfo`, `부가서비스정보` | source-specific attributes |
| `rstde`, `휴무일` | source-specific attributes |
| 하절기/동절기 운영시작·종료시각 | source-specific attributes |
| `avrgWorkNmprCo`, `평균근무인원수` | source-specific attributes |
| `engGuidanceYn`, `jpnGuidanceYn`, `chnGuidanceYn`, `guidanceLanguage` | source-specific attributes |
| `trsmicPhoneNumber`, `phoneNumber`, `안내소전화번호` | 전화 |
| `rdnmadr`, `소재지도로명주소` | 도로명 주소 |
| `lnmadr`, `소재지지번주소` | 지번 주소 |
| `institutionNm`, `운영기관명` | source-specific attributes |
| `homepageUrl`, `홈페이지주소` | 웹 링크 |
| `longitude`, `경도`; `latitude`, `위도` | 좌표 |
| `referenceDate`, `데이터기준일자` | source version |

카테고리:

| 조건 | category |
| --- | --- |
| 모든 row | `01060101` |

운영 주의:

- 관광안내소는 지도에 올릴 수 있는 공공 장소이므로 `map_features(feature_type='place')`와 `place_details(place_kind='tourist_spot')`로 적재한다.
- 도로명코드/도로명주소관리번호는 아직 주소 문자열 기반 fuzzy matching을 하지 않으므로 채우지 않는다. 좌표가 있으면 법정동 경계 point-in-polygon으로 `legal_dong_code`만 매핑한다.
- 관리자 데이터 브라우저는 SQLAlchemy metadata 기반으로 테이블을 나열하므로 별도 UI 등록 없이 `map_features`, `place_details`, `source_records`, `map_feature_provider_refs`에서 조회된다.

## `public_recreation_forest`

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://www.data.go.kr/data/15013111/standard.do` |
| 구현 URL | `https://api.data.go.kr/openapi/tn_pubr_public_rcrfrst_api` |
| source mode | `data_go_standard_api` |
| job | `public_recreation_forest_semiannual` |
| 공식 갱신 | 반기 |
| TripMate 수집 | 1/7월 15일 04:15 KST |

요청 파라미터:

| 이름 | 필수 | 구현값 |
| --- | --- | --- |
| `serviceKey` | Y | `TRIPMATE_DATA_GO_SERVICE_KEY` |
| `pageNo` | Y | 자동 증가 |
| `numOfRows` | Y | 1000 |
| `type` | Y | `json` |

출력 파라미터:

| 필드 | 저장/사용 방식 |
| --- | --- |
| `rcrfrstNm`, `휴양림명` | 장소명 |
| `rdnmadr`, `소재지도로명주소` | 도로명 주소 |
| `lnmadr`, `소재지지번주소` | 지번 주소 |
| `longitude`, `경도`; `latitude`, `위도` | 좌표 |
| `telephoneNumber`, `휴양림전화번호` | 전화 |
| `homepageUrl`, `홈페이지주소` | 웹 링크 |
| `rcrfrstType`, `휴양림구분` | 카테고리 세분화 |
| `referenceDate`, `데이터기준일자` | source version |
| `rcrfrstAr`, `aceptncCo`, `admfee`, `stayngPosblYn`, `mainFcltyNm` | source-specific attributes |

카테고리:

| 조건 | category |
| --- | --- |
| 국유림/국립/산림청 | `03030101` |
| 공유림/공립/시유림/도유림/군유림/지자체 | `03030201` |
| 사유림/사립/민간 | `03030301` |
| 기본 | `03030000` |

## `public_museum_art_gallery`

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://www.data.go.kr/data/15017323/standard.do` |
| 구현 URL | `https://api.data.go.kr/openapi/tn_pubr_public_museum_artgr_info_api` |
| source mode | `data_go_standard_api` |
| job | `public_museum_art_gallery_annual` |
| 공식 갱신 | 연간 |
| TripMate 수집 | 매년 7월 15일 04:25 KST |

요청 파라미터:

| 이름 | 필수 | 구현값 |
| --- | --- | --- |
| `serviceKey` | Y | `TRIPMATE_DATA_GO_SERVICE_KEY` |
| `pageNo` | Y | 자동 증가 |
| `numOfRows` | Y | 1000 |
| `type` | Y | `json` |

출력 파라미터:

| 필드 | 저장/사용 방식 |
| --- | --- |
| `fcltyNm`, `시설명` | 장소명 |
| `rdnmadr`, `소재지도로명주소` | 도로명 주소 |
| `lnmadr`, `소재지지번주소` | 지번 주소 |
| `longitude`, `경도`; `latitude`, `위도` | 좌표 |
| `operPhoneNumber`, `phoneNumber`, `운영기관전화번호`, `관리기관전화번호` | 전화 |
| `homepageUrl`, `운영홈페이지` | 웹 링크 |
| `fcltyType`, `박물관미술관구분` | 카테고리 세분화 |
| `referenceDate`, `데이터기준일자` | source version |
| 운영시간/휴관/요금/소개/교통 필드 | source-specific attributes |

카테고리:

| 조건 | category |
| --- | --- |
| 갤러리/화랑 | `01040202` |
| 미술관 | `01040201` |
| 국립/공립/시립/도립/군립/구립 | `01040101` |
| 사립 | `01040102` |
| 테마/민속/자연사/과학 | `01040103` |
| 기본 박물관 | `01040100` |

## `public_campground`

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://www.data.go.kr/data/15101933/openapi.do` |
| 구현 URL | `http://apis.data.go.kr/B551011/GoCamping/basedList` |
| source mode | `go_camping_api` |
| job | `public_campground_daily` |
| 공식 갱신 | 실시간 |
| TripMate 수집 | 매일 04:45 KST |

요청 파라미터:

| 이름 | 필수 | 구현값/설명 |
| --- | --- | --- |
| `serviceKey` | Y | `TRIPMATE_DATA_GO_SERVICE_KEY` |
| `pageNo` | N | 자동 증가. 기본 1 |
| `numOfRows` | N | 1000 |
| `MobileOS` | Y | `ETC` |
| `MobileApp` | Y | `TripMate` |
| `_type` | N | `json` |

출력 파라미터:

| 필드 | 저장/사용 방식 |
| --- | --- |
| `contentId` | source id |
| `facltNm`, `사업장명`, `야영(캠핑)장명`, `bplcNm`, `campingNm` | 장소명 |
| `addr1`, `addr2`, `소재지도로명주소`, `도로명전체주소`, `rdnmadr` | 도로명 주소 |
| `소재지전체주소`, `소재지지번주소`, `lnmadr` | 지번 주소 |
| `mapX`, `longitude`, `경도`; `mapY`, `latitude`, `위도` | EPSG:4326 좌표 |
| `좌표정보(x)`, `좌표정보X`, `x`; `좌표정보(y)`, `좌표정보Y`, `y` | 과거 LocalData EPSG:5174 후보 좌표. 4326으로 변환 |
| `tel`, `소재지전화`, `야영장전화번호`, `전화번호`, `telNo` | 전화 |
| `homepage`, `홈페이지`, `홈페이지주소`, `homepageUrl` | 웹 링크 |
| `induty`, `lctCl`, `facltDivNm`, `야영(캠핑)장구분`, `업태구분명`, `상세영업상태명` | 카테고리/운영상태 판단 |
| `인허가일자`, `허가일자` | `opened_on` 후보 |
| `폐업일자` | `closed_on` |
| `manageSttus`, `영업상태명`, `상세영업상태명`, `영업상태구분코드` | operation status |
| `modifiedtime`, `createdtime` | source version |
| 사이트수/면적/수용인원/주차/편의시설/안전시설/요금/관리기관/이미지/예약 URL | source-specific attributes |

카테고리:

| 조건 | category |
| --- | --- |
| 글램핑 | `03060201` |
| 카라반/캠핑카 | `03060202` |
| 자동차/오토 | `03060102` |
| 야영/캠핑 | `03060101` |
| 기본 | `03060000` |

운영상태:

| 조건 | 내부 상태 |
| --- | --- |
| 폐업/취소/말소/직권폐쇄 | `closed` |
| 휴업/중지 | `temporarily_closed` |
| 영업/정상/운영 | `operating` |
| 기타 | `unknown` |

운영 주의:

- 과거 `https://file.localdata.go.kr/file/general_campgrounds/info` CSV 방식은 WSL2 검증에서 403을 반환했다. 현재 기본 수집 경로는 Go Camping API다.
- 표준 OpenAPI가 `SERVICE KEY IS NOT REGISTERED ERROR`를 반환하면 `TRIPMATE_DATA_GO_SERVICE_KEY` 값 자체보다 먼저 해당 서비스의 활용신청/승인 상태를 확인한다.
