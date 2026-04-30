# 주소/행정구역 데이터 소스

이 문서는 Juso 주소 DB, data.go.kr 법정동코드, V-WORLD 행정경계 SHP를 인수인계하기 위한 상세 기준이다. 관련 구현은 `apps/api/app/etl/juso/*`, `apps/api/app/etl/vworld/*`, `dags/juso_monthly_address.py`, `dags/legal_dong_code_standard.py`, `apps/api/app/cli/vworld_boundary.py`다.

## 전체 관계

| 데이터셋 | 역할 | 주요 테이블 |
| --- | --- | --- |
| `juso_road_address_korean` | 도로명주소/관련 지번 전체분 수집, 주소 exact match 기준 | `address_raw_juso_road_address`, `address_serving_juso_road_address`, `address_raw_juso_related_jibun`, `address_serving_juso_related_jibun` |
| `legal_dong_code_standard` | 10자리 법정동/시도/시군구 코드 canonical source | `address_raw_legal_dong_code`, `address_code_standard` |
| `vworld_boundary_upload` | 행정구역 polygon, 좌표 기반 법정동 판정 | `region_boundary_import_batch`, `region_raw_vworld_boundary`, `region_serving_boundary` |

## Juso 월간 도로명주소 DB

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://business.juso.go.kr/jst/jstAddressDownload` |
| 구현 base URL | `https://business.juso.go.kr` |
| 목록 API | `POST /api/jst/selectAttrbDBDwldList` |
| 다운로드 API | `GET /api/jst/download` |
| 공식 갱신 | 월간 전체분. 운영 경험상 매월 10일 이후 안정적으로 확인한다. |
| TripMate 수집 | `juso_monthly_address_dataset`, 매월 10-31일 04:00 KST. 같은 `source_year_month` 성공분이 있으면 skip한다. |
| 인증 | 구현상 별도 API key 없음. `User-Agent: TripMate/0.1` 사용. |
| timeout | 목록/다운로드 60초 |

목록 API 요청 파라미터:

| 이름 | 필수 | 구현값/설명 |
| --- | --- | --- |
| `rtlDtaDtlSn` | Y | `1`. 도로명주소 한글 데이터셋 상세 serial |
| `year` | Y | 조회 기준 연도. `source_year_month[:4]` |
| `month` | Y | 조회 기준 월. 선행 zero 없이 정수 문자열 |
| `expand` | Y | `Y` |

목록 API에서 사용하는 출력 필드:

| 출력 필드 | 사용 방식 |
| --- | --- |
| `results.allMonthFileList[]` | 월간 전체분 후보 목록 |
| `isExist` | `Y`인 row만 사용 |
| `fileTypeNm` | `ALLRNADR_KOR`인 row만 사용 |
| `fileNm` | 다운로드 저장 파일명과 `fileName` 요청값 |
| `tmprFileNm` | `realFileName` 요청값 |
| `crtrYm` | `source_year_month` |
| `ctpvClsfCd` | `ctprvnCd` 요청값 |
| `fileSn` | `intFileNo` 요청값. 없으면 `0` |
| `atflNo` | `intNum` 요청값. 없으면 `0` |

다운로드 API 요청 파라미터:

| 이름 | 필수 | 구현값/설명 |
| --- | --- | --- |
| `reqType` | Y | `ALLRNADR_KOR` |
| `ctprvnCd` | Y | 목록의 `ctpvClsfCd`, 없으면 빈 문자열 |
| `stdde` | Y | `YYYYMM` |
| `fileName` | Y | 목록의 `fileNm` |
| `realFileName` | Y | 목록의 `tmprFileNm` |
| `intFileNo` | Y | 목록의 `fileSn`, 없으면 `0` |
| `intNum` | Y | 목록의 `atflNo`, 없으면 `0` |
| `regYmd` | Y | `YYYY` |

압축 파일 내부 출력 파일:

| 파일 패턴 | 처리 |
| --- | --- |
| `rnaddrkor_*.txt` | 도로명주소 raw/serving으로 적재 |
| `jibun_rnaddrkor_*.txt` | 관련 지번 raw/serving으로 적재 |

도로명주소 TXT에서 보존/사용하는 주요 필드:

| 필드 | 사용 방식 |
| --- | --- |
| 도로명주소관리번호 | serving PK, 관련 지번 연결 key |
| 법정동코드 | `address_code_standard` FK 후보, 시도/시군구 파생 |
| 도로명코드 | 주소 FK/검색 기준 |
| 행정동코드 | nullable 보조 코드 |
| 시도명/시군구명/읍면동명/리명 | 표시명과 full legal dong name 구성 |
| 도로명, 건물본번/부번, 지하여부 | full road address 구성 |
| 산여부, 지번본번/부번 | 주소 snapshot 구성 |
| 우편번호, 이전도로명주소, 공동주택여부, 건축물대장건물명, 시군구용건물명, 비고 | 표시/감사용 보조 필드 |
| 효력일자, 변경사유코드 | `source_effective_date`, `source_change_reason_code` |

관련 지번 TXT에서 보존/사용하는 주요 필드:

| 필드 | 사용 방식 |
| --- | --- |
| 도로명주소관리번호 | 도로명주소와 연결 |
| 법정동코드, 도로명코드 | 주소 기준 코드 |
| 시도명/시군구명/읍면동명/리명 | full legal dong name 구성 |
| 산여부, 지번본번/부번, 건물본번/부번, 지하여부 | full jibun address 구성 |
| 비고 | raw/serving 보조 필드 |

구현 메모:

- zip-slip 방지를 위해 압축 해제 경로가 destination 밖으로 나가면 실패시킨다.
- source archive hash를 SHA-256으로 남긴다.
- 문자열 코드는 leading zero 보존을 위해 numeric으로 변환하지 않는다.

## data.go.kr 법정동코드

| 항목 | 내용 |
| --- | --- |
| 설명 URL | `https://www.data.go.kr/data/15063424/fileData.do` |
| 구현 URL | 설명 페이지 HTML에서 `contentUrl`을 추출한 뒤 다운로드 |
| 인증 | 다운로드 URL에 `serviceKey`가 없으면 `TRIPMATE_DATA_GO_SERVICE_KEY`를 query로 추가한다. 로그에는 `serviceKey=***`로 마스킹한다. |
| 공식 갱신 | 월간/수시성 파일 데이터. TripMate는 분기 확인 수집으로 운영한다. |
| TripMate 수집 | `legal_dong_code_standard_quarterly`, 2/5/8/11월 15일 04:30 KST |
| timeout | 페이지/다운로드 30초 |

요청 파라미터:

| 이름 | 필수 | 구현값/설명 |
| --- | --- | --- |
| `serviceKey` | 조건부 | 다운로드 URL에 없을 때만 추가. 값은 환경변수 |
| 기타 file download query | provider | data.go.kr 페이지의 `contentUrl`이 제공하는 값을 그대로 사용 |

CSV 출력 필드:

| 필드 | 필수 | 사용 방식 |
| --- | --- | --- |
| `법정동코드` | Y | PK, 10자리 문자열 |
| `시도명` | Y | 시도명 |
| `시군구명` | Y | 시군구명 nullable 구성 |
| `읍면동명` | Y | 읍면동명 nullable 구성 |
| `리명` | Y | 리명 nullable 구성 |
| `순위` | Y | `source_sort_order` |
| `생성일자` | Y | `source_created_date`, source effective date 후보 |
| `삭제일자` | Y | `source_deleted_date`, active/discontinued 판정 |
| `과거법정동코드` | Y | 과거 코드 연결 |

serving 파생 필드:

| 필드 | 설명 |
| --- | --- |
| `code_level` | `sido`, `sigungu`, `legal_dong` |
| `sido_code`, `sigungu_code`, `legal_dong_code` | 10자리 문자열. 시도/시군구는 뒤를 0으로 채운다. |
| `full_legal_dong_name` | 공백 join한 전체 법정동명 |
| `source_provider` | `data_go_legal_dong` |
| `source_status` | active/discontinued/missing fallback |
| `is_active`, `is_discontinued` | 삭제일자/상태 기반 |

구현 메모:

- CSV encoding은 `utf-8-sig`, `cp949` 순서로 시도한다.
- 기존 V-WORLD `LSCT_LAWDCD.zip` 3컬럼 CSV는 legacy/manual fallback으로만 둔다.
- `address_code_standard`는 Juso/V-WORLD/외부 장소 매핑의 canonical FK 기준이다.

## V-WORLD 행정경계 SHP

| 항목 | 내용 |
| --- | --- |
| 설명/원천 | V-WORLD 법정구역정보 SHP ZIP |
| 구현 방식 | 외부 자동 다운로드 없음. 운영자가 ZIP을 받아 CLI/API에 전달한다. |
| TripMate 수집 | `vworld_boundary_upload`, manual |
| 원천 좌표계 | EPSG:5179 |
| serving 좌표계 | EPSG:4326 |
| encoding | DBF `cp949` |

지원 ZIP 파일명과 layer:

| ZIP stem | boundary level | 설명 |
| --- | --- | --- |
| `N3A_G0010000` | `sido` | 행정경계 시도 |
| `N3A_G0100000` | `sigungu` | 행정경계 시군구 |
| `N3A_G0110000` | `legal_dong` | 행정경계 읍면동/법정동 |

필수 SHP 구성 파일:

| 파일 | 필수 |
| --- | --- |
| `.shp` | Y |
| `.shx` | Y |
| `.dbf` | Y |
| `.prj` | Y |

DBF 출력 필드:

| 필드 | 필수 | 사용 방식 |
| --- | --- | --- |
| `UFID` | Y | V-WORLD feature id |
| `BJCD` | Y | 행정구역 코드. 법정동코드와 매칭 시도 |
| `NAME` | Y | 경계명 |
| `DIVI` | Y | provider 분류 |
| `SCLS` | Y | provider 분류 |
| `FMTA` | Y | provider 면적/속성 |

구현 메모:

- `.prj`에 `Korea_Unified_Coordinate_System` 또는 `5179`가 없으면 실패한다.
- raw geometry는 EPSG:5179 MultiPolygon으로 저장한다.
- serving geometry는 EPSG:4326 MultiPolygon으로 변환한다.
- 좌표 기반 주소 매핑은 `ST_Covers(region_serving_boundary.geom, point)`와 가장 작은 면적 우선 정렬을 사용한다.
- 시도/시군구/법정동 코드는 `BJCD`와 `address_code_standard`를 exact match하고, 필요한 경우 이름 기반 보수 매칭을 제한적으로 사용한다.
