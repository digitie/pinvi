# 공공 장소 ETL 및 표준 장소 적재 스키마

## 목적

이 문서는 수목원, 관광안내소, 휴양림, 박물관, 미술관, 캠핑장처럼 공공데이터포털에서 가져오는 장소성 데이터를 TripMate 내부 표준 장소 DB에 적재하는 기준을 설명한다.

목표는 다음과 같다.

- 공공데이터 원천 레코드는 재처리와 diff 검증을 위해 보존한다.
- 사용자 검색, 지도, 여행 장소 연결은 `python-krtour-map` feature 계약을 기준으로 한다.
- 모든 장소에 공통으로 쓰이는 필드는 typed column으로 승격한다.
- 특정 장소 유형에만 의미 있는 필드는 JSONB로 보관한다.
- 장소 자동 병합은 보수적으로 하고, 같은 공공데이터 dataset과 같은 source id만 멱등 upsert 기준으로 사용한다.

## 데이터 소스

| dataset key | 출처 | 방식 | 공식 갱신 주기 | TripMate 수집 주기 |
| --- | --- | --- | --- | --- |
| `public_arboretum_basic` | 한국수목원정원관리원_수목원_기본관람정보 | 공공데이터포털 파일 다운로드 CSV/ZIP | 수시(1회성 데이터) | 매년 7월 5일 04:05 |
| `public_tourist_information_center` | 전국관광안내소표준데이터 | data.go.kr 표준 OpenAPI `tn_pubr_public_trsmic_api` | 연간, 개별 지자체 데이터는 월초 병합 가능 | 매년 7월 5일 04:10 |
| `public_recreation_forest` | 전국휴양림표준데이터 | data.go.kr 표준 OpenAPI `tn_pubr_public_rcrfrst_api` | 반기 | 1월/7월 15일 04:15 |
| `public_museum_art_gallery` | 전국박물관미술관정보표준데이터 | data.go.kr 표준 OpenAPI `tn_pubr_public_museum_artgr_info_api` | 연간 | 매년 7월 15일 04:25 |
| `public_campground` | 한국관광공사_고캠핑 정보 조회서비스_GW | `http://apis.data.go.kr/B551011/GoCamping/basedList` | 실시간 | 매일 04:45 |

수목원 파일은 공공데이터포털 `fileData.do` 페이지의 JSON-LD `contentUrl`에서 실제 `fileDownload.do` URL을 추출해 내려받는다. 운영 환경에서 포털 다운로드 정책이 바뀌면 `TRIPMATE_ARBORETUM_BASIC_CSV_URL` 또는 `TRIPMATE_ARBORETUM_BASIC_CSV_PATH`로 직접 CSV/ZIP 경로를 주입할 수 있다.

캠핑장 데이터는 2026-04-29부터 한국관광공사 고캠핑 OpenAPI를 기본 소스로 사용한다. 과거 `https://file.localdata.go.kr/file/general_campgrounds/info` CSV 방식은 WSL2 검증에서 403을 반환했으므로 기본 수집 경로에서 제외했다.

인증:

- Go Camping, 전국문화축제표준데이터, 전국관광안내소표준데이터, 전국휴양림표준데이터, 전국박물관미술관정보표준데이터는 `TRIPMATE_DATA_GO_SERVICE_KEY`를 사용한다.
- 2026-04-29에 운영자가 제공한 data.go.kr 인증키를 로컬 검증 환경의 `.env`와 `apps/api/.env`에 반영했다. 인증키 원문은 Git, 문서, 로그에 저장하지 않는다.

로컬 WSL2 검증에서는 data.go.kr 표준 OpenAPI가 인증키 없이 연결 리셋될 수 있고, localdata CSV URL은 403이 발생할 수 있다. 이 경우 코드를 임의로 우회하지 말고 운영 인증키, 네트워크, 상류 방화벽 정책을 먼저 확인한다. 스키마, 정규화, 멱등성은 mock transport와 fixture 기반 테스트로 검증하고, 운영 반영 전에는 실제 인증키가 주입된 Dagster 환경에서 1건 smoke run을 별도로 수행한다.

2026-04-27 WSL2 smoke 결과와 2026-04-29 조치:

- `public_arboretum_basic`: 공공데이터포털 파일 다운로드 성공, 70건 적재 성공, smoke DB에 법정동 경계가 없어 법정동 매핑 0건.
- `public_recreation_forest`, `public_museum_art_gallery`: 기존 키로 `SERVICE KEY IS NOT REGISTERED ERROR`를 반환했다. 2026-04-29에 새 data.go.kr 키를 반영했으며, Dagster smoke run으로 재검증한다.
- `public_campground`: LocalData CSV URL이 403을 반환했다. 2026-04-29에 Go Camping API로 전환했으며, 동일한 `TRIPMATE_DATA_GO_SERVICE_KEY`로 재검증한다.

## DB 테이블

### `place_categories`

TripMate 8자리 장소 카테고리 코드 테이블이다. 이번 구현에서는 요청된 장소군에 필요한 최소 카테고리를 seed한다.

- 수목원: `01030100`, `01030101`, `01030102`, `01030103`
- 관광안내소: `01060000`, `01060100`, `01060101`
- 휴양림: `03030000`, `03030101`, `03030201`, `03030301`
- 박물관: `01040100`, `01040101`, `01040102`, `01040103`
- 미술관·갤러리: `01040200`, `01040201`, `01040202`
- 캠핑장: `03060000`, `03060101`, `03060102`, `03060201`, `03060202`

마이그레이션 seed가 기본이며, 테스트 fixture처럼 테이블이 truncate되는 환경을 고려해 loader도 필요한 카테고리를 보강한다.

### Feature projection

공공 장소 ETL row를 feature로 승격하는 DTO, source trace, 저장 schema는 `python-krtour-map`의 [Feature model](https://github.com/digitie/python-krtour-map/blob/main/docs/feature-model.md)과 [Postgres schema](https://github.com/digitie/python-krtour-map/blob/main/docs/postgres-schema.md)을 따른다.

공공데이터포털 데이터는 장기 저장 가능한 공공 원천으로 보고 raw payload를 보관할 수 있다. Kakao/Naver/Google 같은 상업 provider raw 전체와는 정책이 다르다.

공공데이터에는 전역 고유 ID가 없는 경우가 많으므로 `source_entity_id`는 dataset key, 장소명, 주소, 좌표, 제공기관코드 또는 관리기관명을 조합해 만든다. 같은 데이터셋의 같은 source id는 같은 feature로 upsert한다.

주의할 점:

- 공공데이터에 안정적인 전역 ID가 없는 데이터셋은 상류에서 장소명, 주소, 좌표를 정정하면 source id가 바뀔 수 있다.
- 이 경우 기존 feature를 무리하게 자동 병합하지 않고 새 source trace로 적재한다.
- 나중에 운영 화면에서 중복 후보를 검토하거나, dataset별 더 안정적인 원천 ID가 확인되면 그 필드만 source id 생성 규칙에 추가한다.
- 좌표나 주소가 조금 바뀐 레코드를 이름 유사도만으로 자동 병합하면 서로 다른 장소를 합칠 위험이 있으므로 현재는 하지 않는다.
- 공식 홈페이지가 있으면 `Feature.urls.homepage` 또는 `Feature.detail.links`로 정규화한다. URL이 `www.example.com`처럼 scheme 없이 들어오면 `https://`를 붙인다.

## JSONB 사용 기준

`Feature.detail`은 특정 장소군에서만 의미 있는 정보를 보관한다.

예:

- 수목원: 대표수종, 교육체험프로그램, 무장애 관광 여부, 입장료
- 휴양림: 휴양림면적, 수용인원수, 입장료, 숙박가능여부, 주요시설명
- 박물관/미술관: 관람료, 휴관정보, 소개, 교통안내, 평일/공휴일 관람시간
- 캠핑장: 야영사이트수, 부지면적, 주차장면수, 편의시설, 안전시설, 이용요금

구조적 판단:

- JSONB는 long-tail 속성을 저장하기에 적합하다.
- 검색, 필터, 정렬, join에 자주 쓰는 값은 JSONB에만 두면 안 된다.
- 현재 지도/검색 핵심 값인 이름, 주소, 좌표, 법정동코드, 카테고리, 전화번호, 운영상태는 typed column으로 승격했다.
- JSONB 내부 값을 자주 필터링해야 하는 요구가 생기면 그 필드만 typed column 또는 별도 detail table로 승격한다.
- JSONB 전체에 무조건 GIN index를 만들지 않는다. 쓰기 비용과 index bloat가 생길 수 있으므로, 실제 query가 생긴 뒤 표현식 index 또는 부분 GIN index를 추가한다.

## 카테고리 매핑

수목원:

- `국립` 포함: `01030101`
- `공립`, `시립`, `도립`, `군립`, `구립`, `공영` 포함: `01030102`
- `사립`, `사유`, `민간` 포함: `01030103`
- 그 외: `01030100`

관광안내소:

- 전국관광안내소표준데이터는 `01060101`(관광 > 관광안내 > 관광안내소 > 공공 관광안내소)로 고정한다.
- 원천의 `안내소위치명`, 운영시간, 외국어 안내 가능 여부, 부가서비스 정보는 `Feature.detail`에 보관한다.

휴양림:

- `국유림`, `국립`, `산림청` 포함: `03030101`
- `공유림`, `공립`, `시유림`, `도유림`, `군유림`, `지자체` 포함: `03030201`
- `사유림`, `사립`, `민간` 포함: `03030301`
- 그 외: `03030000`

박물관/미술관:

- `갤러리`, `화랑` 포함: `01040202`
- `미술관` 포함: `01040201`
- `국립`, `공립`, `시립`, `도립`, `군립`, `구립` 포함: `01040101`
- `사립` 포함: `01040102`
- `테마`, `민속`, `자연사`, `과학` 포함: `01040103`
- 그 외 박물관: `01040100`

캠핑장:

- `글램핑` 포함: `03060201`
- `카라반`, `캠핑카` 포함: `03060202`
- `자동차`, `오토` 포함: `03060102`
- `야영`, `캠핑` 포함: `03060101`
- 그 외: `03060000`

## 좌표와 주소 매핑

수목원, 휴양림, 박물관, 미술관은 위도/경도를 EPSG:4326으로 받는 것을 기본으로 한다.

Go Camping API는 `mapX`, `mapY`를 EPSG:4326 경도/위도로 제공한다. 과거 LocalData CSV처럼 “보정계수 안 들어간 Bessel 중부원점TM(EPSG:5174)” 좌표가 들어온 row도 ETL은 `pyproj`로 EPSG:5174 좌표를 EPSG:4326으로 변환한 뒤 `python-krtour-map` feature 좌표로 저장할 수 있다.

주소 문자열로 Juso key fuzzy matching은 하지 않는다. 현재 기준은 좌표 기반 법정동 매핑이다. 도로명코드, 도로명주소관리번호 연결은 후속 기능에서 명확한 Juso key 매칭 정책이 생기면 추가한다.

## Dagster job

파일: `apps/api/app/dagster_etl/registry.py`

- `public_arboretum_basic_annual`
- `public_tourist_information_center_annual`
- `public_recreation_forest_semiannual`
- `public_museum_art_gallery_annual`
- `public_campground_daily`

각 job는 기존 ETL 공통 실행 로그를 사용한다.

- 성공: `etl_run_logs.status = success`
- 실패: retry 설정에 따라 재시도
- retry 소진: 관리자 알림과 권리자 Telegram 시스템 알림 대상

설정 파일:

- 기본: `config/etl-datasets.json`
- soak 검증: `config/etl-datasets.soak.json`

## 검증 기준

테스트 파일:

- `apps/api/tests/test_public_data_place_loader.py`
- `apps/api/tests/test_model_metadata.py`
- `apps/api/tests/test_migration_contract.py`
- `apps/api/tests/test_dagster_etl.py`
- `apps/api/tests/test_etl_config.py`

검증한 내용:

- data.go.kr 표준 OpenAPI pagination과 query parameter
- 공공데이터포털 파일 다운로드 페이지의 `contentUrl` 추출
- 전국관광안내소표준데이터의 공식 OpenAPI path `tn_pubr_public_trsmic_api`
- ZIP 내부 cp949 CSV 읽기
- 휴양림 row를 `python-krtour-map` feature로 승격하고 특화 필드는 `Feature.detail`에 보존
- 같은 source row 반복 적재 시 raw/source record 중복 방지
- 수목원, 관광안내소, 휴양림, 박물관, 미술관, 캠핑장 카테고리 매핑
- 캠핑장 EPSG:5174 좌표를 EPSG:4326으로 변환
- 폐업 캠핑장은 신규 검색 노출에서 제외
- 좌표 기반 법정동 point-in-polygon 매핑
- 장소 geometry SRID와 GiST index
- FK column covering index
- Dagster job schedule, retry, KST start date
