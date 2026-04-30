# TripMate MCP 도구 설계

이 문서는 TripMate 데이터를 외부 AI 도구가 안전하게 조회하거나 보조 입력할 수 있도록 만들 MCP 도구의 기준이다. 현재 저장소에는 MCP 서버 런타임이 없으므로 이 문서는 설계와 TODO 기준이며, 실제 구현은 별도 작업으로 진행한다.

## 공통 원칙

- MCP는 TripMate 앱 DB를 직접 수정할 수 있으므로 기본 동작은 read-only 또는 draft 생성으로 시작한다.
- 장소, 주소, provider 원문처럼 사용자 화면에 영향을 주는 데이터는 즉시 확정 저장하지 않고 `pending` 또는 검수 대상 상태를 둔다.
- 비밀값은 MCP 설정 파일이나 환경변수로만 주입한다. YouTube API key, DB URL, provider key를 tool 응답이나 로그에 노출하지 않는다.
- 모든 datetime은 KST(`Asia/Seoul`) 기준으로 해석하고 저장한다.
- 좌표는 EPSG:4326 `longitude`, `latitude` 순서로 표준화한다.
- 주소 매핑은 기존 TripMate 주소 체계를 따른다. 도로명주소 exact, 지번주소 exact, V-WORLD 법정동 point-in-polygon 순서이며 fuzzy matching은 기본값으로 사용하지 않는다.
- MCP tool 응답은 사람이 검토하기 쉬운 요약과 machine-readable JSON을 함께 반환한다.
- 긴 원문, 영상 자막 전문, 댓글 전문은 장기 저장하지 않는다. 필요한 경우 후보 추출 근거 요약과 출처 링크만 보존한다.

## `youtube_place_import` MCP

목적:

- YouTube 영상 URL, 영상 ID, 설명란, 자막에서 장소 후보를 추출한다.
- 후보 장소를 TripMate 표준 장소(`places`) 또는 장소 후보 검수 테이블에 연결할 수 있게 한다.
- 여행 계획 작성자가 영상 기반 추천 장소를 빠르게 검토하도록 돕는다.
- 상세 아키텍처와 Gemini YouTube URL 직접 분석 방식은 `docs/architecture/youtube-travel-intelligence.md`를 따른다.

입력 후보:

| 필드 | 설명 |
| --- | --- |
| `video_url` | YouTube 영상 URL |
| `video_id` | URL 대신 전달할 수 있는 영상 ID |
| `trip_id` | 특정 여행에 연결할 때 사용. 선택 |
| `created_by_user_id` | 후보를 만든 사용자. 선택이지만 쓰기 작업에는 필요 |
| `dry_run` | 기본값 `true`. DB 저장 없이 후보만 반환 |

처리 단계:

1. 영상 metadata와 설명란을 읽는다.
2. 가능한 경우 자막/챕터를 읽는다.
3. Gemini API에는 전체 파일 다운로드 대신 공개 YouTube URL을 `file_data.file_uri`로 전달하는 방식을 우선한다.
4. 장소명, 주소, 전화번호, URL, 좌표처럼 장소 후보가 될 수 있는 값을 추출한다.
5. 추출 후보를 Kakao/Naver/Google 같은 일반 장소 provider에 즉시 질의하지 않는다. provider 정책이 정리되기 전까지는 내부 주소 DB와 기존 장소 DB만 사용한다.
6. 주소 문자열이 있으면 Juso 도로명/지번 exact match를 시도한다.
7. 좌표가 있으면 V-WORLD 법정동 경계 point-in-polygon으로 법정동코드를 찾는다.
8. 기존 `map_features`와 같은 이름/주소/좌표 후보가 있으면 연결 후보로 표시한다.
9. `dry_run=false`이고 권한이 확인된 경우에만 장소 후보를 pending 상태로 저장한다.

저장 정책:

- 영상 원문 자막 전문은 저장하지 않는다.
- 저장 가능한 값은 `video_id`, `video_url`, 영상 제목, 채널명, 후보 장소명, 후보 주소/좌표, 추출 근거 요약, 생성시각, 생성자, 검수 상태다.
- 영상 설명란이나 자막에서 가져온 긴 문장은 원문 저장 대신 짧은 근거 요약으로 저장한다.

의사결정 필요:

- 자동 모니터링에는 시스템/관리자 Gemini key를 쓸지, 사용자 개인 Gemini key만 허용할지 결정해야 한다.
- YouTube Data API를 사용할지, 사용자가 제공한 URL에서 접근 가능한 공개 metadata/caption만 사용할지 결정해야 한다.
- 댓글까지 읽을지 여부는 별도 결정이 필요하다. 기본값은 댓글 미수집이다.
- 후보 장소를 바로 `places`에 넣을지, 별도 `place_import_candidates` 테이블에 넣은 뒤 검수할지 결정해야 한다. 추천 기본값은 별도 후보 테이블이다.
- 대표 프레임 이미지를 공개 UI에 노출할지, 관리자 검수 화면에서만 쓸지 결정해야 한다.
- 저작권/약관 관점에서 자막·설명 원문 저장 범위를 재확인해야 한다.

## `address_code_lookup` MCP

목적:

- TripMate 기준 주소 DB에서 법정동코드, 도로명코드, 행정동코드, 도로명주소관리번호를 조회한다.
- 다른 AI 작업자가 주소/좌표 매핑을 반복해서 새로 설계하지 않도록 한다.

입력 후보:

| 필드 | 설명 |
| --- | --- |
| `road_address` | 도로명주소 exact lookup |
| `jibun_address` | 지번주소 exact lookup |
| `legal_dong_code` | 법정동코드 direct lookup |
| `road_name_code` | 도로명코드 direct lookup |
| `road_address_management_no` | 도로명주소관리번호 direct lookup |
| `longitude`, `latitude` | 좌표 기반 법정동 point-in-polygon lookup |
| `include_discontinued` | 폐지 주소 포함 여부. 기본값 `false` |

출력 후보:

| 필드 | 설명 |
| --- | --- |
| `legal_dong_code` | TripMate 주소 체계의 기본 법정동코드 |
| `road_name_code` | 도로명코드 |
| `administrative_dong_code` | 행정동코드 |
| `road_address_management_no` | 도로명주소관리번호 |
| `sido_code`, `sigungu_code` | 상위 행정구역 코드 |
| `full_legal_dong_name` | 전체 법정동명 |
| `matched_by` | `road_exact`, `jibun_exact`, `code_exact`, `point_in_polygon`, `not_found` |
| `source_year_month` | 주소 데이터 기준월 |
| `is_active` | 현재 주소 여부 |

운영 기준:

- 기본 lookup은 read-only다.
- 폐지 주소는 기본 검색에서 숨긴다.
- 좌표 lookup은 `region_serving_boundary`의 serving EPSG:4326 geometry를 사용한다.
- 주소 문자열 fuzzy matching은 하지 않는다.
- 대량 조회가 필요하면 single lookup tool이 아니라 batch tool을 별도로 만든다.

의사결정 필요:

- MCP가 운영 DB를 직접 조회할지, read-only replica 또는 export snapshot을 조회할지 결정해야 한다.
- 내부 관리자만 사용할지, 개발 보조 도구로 로컬 DB에만 붙일지 결정해야 한다.
- 주소 후보가 여러 개 나올 때 응답에 후보 목록을 줄지, exact match 실패로 처리할지 결정해야 한다.

## 구현 TODO

- MCP 서버 런타임 선택: Python `mcp` SDK 또는 Node 기반 MCP server.
- `apps/api` 내부로 둘지, 장기 provider library와 함께 별도 repository로 둘지 결정.
- read-only DB 계정과 최소 권한 정책 마련.
- `youtube_place_import`용 후보 테이블 설계.
- `address_code_lookup` contract test와 fixture 작성.
- MCP tool별 audit log와 rate limit 추가.
