# Claude Code 운영 검증 인계

2026-11-06 최신 운영 댓글 기준 #650은 해결·CLOSED이며 Map #1450도 초회 적재·SRCH028 검증을 마쳤다. 남은 범위는 #621/#686 운영 확인, Map #1440 과거 날씨와 #1450 갱신 정책 결정이다. Codex는 WSL 작업·검증·머지, Claude Code는 운영 진단·필요한 적재·최종 UI 검증을 담당한다. 아래 머지 SHA는 운영 배포 완료를 뜻하지 않는다.

## 머지 내역과 실행 기준

Pinvi는 이 문서를 포함한 [PR693](https://github.com/digitie/pinvi/pull/693)의 실제 mergeCommit full SHA를 운영 검증 기준으로 고정한다. API PR695/a3129a957cd9fb13913faffebbd58241fb3fecd2와 frontend 묶음이 모두 포함돼야 한다. 기존 별도 서비스의 최소 포함 기준은 Map `27033b116d8d7328689b19a20de830417937dd73`, Geo는 `305777d561a98588e310756981d3a984908be2ee`, Weather는 `d8534aeae8852f9c514e39d625ea7dded956f3ed`다. 운영 시작 시 각 서비스의 실제 실행 image digest/revision·worker 시작 시각과 이 변경의 포함 여부를 확인한다. Pinvi revision만으로 Map/Geo/Weather의 실행 버전을 대신하지 않는다. 이후 릴리스를 쓰면 실제 전체 SHA와 변경 포함 관계를 기록한다.

| 병합 PR                                                                                         | 내용                                                                                     | merge SHA  |
| ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- | ---------- |
| [pinvi #665](https://github.com/digitie/pinvi/pull/665)                                         | 탐색·여행 지도에 경로·영역 레이어와 상세 선택 추가                                       | `613a0553` |
| [pinvi #677](https://github.com/digitie/pinvi/pull/677)                                         | 지도 선택·모바일 맞춤·팝업과 상세 병렬 보강 회귀 수정                                    | `0b8bb6a5` |
| [pinvi #678](https://github.com/digitie/pinvi/pull/678)                                         | 보안: 공유 토큰을 로그인 복귀 경로에서 제거(#671)·로그아웃이 access JWT까지 끊는다(#672) | `9e8459eb` |
| [pinvi #679](https://github.com/digitie/pinvi/pull/679)                                         | 날짜 날씨 핵심 지표·단위 표시와 관리자 날씨 소스 정합성                                  | `12837366` |
| [pinvi #680](https://github.com/digitie/pinvi/pull/680)                                         | fix: enforce permanent bounded request limits for configured users                       | `bbabe45a` |
| [pinvi #681](https://github.com/digitie/pinvi/pull/681)                                         | feat: retain trash for 30 days and collect attachment objects safely                     | `cb3b2f69` |
| [pinvi #683](https://github.com/digitie/pinvi/pull/683)                                         | feat(admin): reconcile uncertain Map approvals with bound attempts                       | `a1b2f532` |
| [pinvi #687](https://github.com/digitie/pinvi/pull/687)                                         | fix(api): isolate quota errors and synchronize day rise-set safely                       | `6f47dad5` |
| [pinvi #688](https://github.com/digitie/pinvi/pull/688)                                         | feat: Telegram 일정 전송과 KST 일간·주간 브리프                                          | `5602cf3d` |
| [pinvi #689](https://github.com/digitie/pinvi/pull/689)                                         | feat: 여행 기상특보 Telegram 알림                                                        | `22d35778` |
| [pinvi #690](https://github.com/digitie/pinvi/pull/690)                                         | feat: 여행 인쇄·PDF 저장·ICS 내보내기와 공유 진입 정합성                                 | `efc01aff` |
| [pinvi #691](https://github.com/digitie/pinvi/pull/691)                                         | geometry anchor 전달·운영 인계 보완                                                      | `ff5c2386` |
| [pinvi #692](https://github.com/digitie/pinvi/pull/692)                                         | Claude Code의 SRCH028 운영 성공·scripted 복귀                                            | `d02a35d5` |
| [pinvi #694](https://github.com/digitie/pinvi/pull/694)                                         | 소유 서버 lock 해제까지 hotswap cleanup 관찰                                             | `a5a21547` |
| [pinvi #695](https://github.com/digitie/pinvi/pull/695)                                         | Map 계약·HTTP 관측·날씨 배경화·rate/pool 복원력                                          | `a3129a95` |
| [maplibre-vworld-react #31](https://github.com/digitie/maplibre-vworld-react/pull/31)           | 선택 SVG 위치 보존·실제 병합본 tarball 소비                                              | `9c46c571` |
| [kor-travel-map #1448](https://github.com/digitie/kor-travel-map/pull/1448)                     | MCST SDK 승인형 CSV와 데이터셋별 적재 결과를 반영                                        | `dd0238c3` |
| [kor-travel-map #1451](https://github.com/digitie/kor-travel-map/pull/1451)                     | fix(admin): safely reconcile uncertain feature commands                                  | `27033b11` |
| [kor-travel-geo #623](https://github.com/digitie/kor-travel-geo/pull/623)                       | test(search): 공식 Juso 원천으로 Pinvi 전체 주소 회귀 확인                               | `305777d5` |
| [kor-travel-weather #201](https://github.com/digitie/kor-travel-weather/pull/201)               | feat: 명시적 기상특보 이벤트 조회 계약                                                   | `d8534aea` |
| [kor-travel-docker-manager #582](https://github.com/digitie/kor-travel-docker-manager/pull/582) | fix(pinvi): deliver bounded user rate limit settings                                     | `20868ab3` |

#678은 다른 Code가 처리한 #671/#672이며 기존 병합을 포함했을 뿐 재구현하지 않았다. 보호 stash `owner-skip-671-672-other-code-in-progress`는 복원하지 않는다.

검증 증거는 Pinvi `docs/reviews/`의 이슈별 JSON과 각 PR 최종 댓글에 있다. #690은 두 독립 전문 적대 리뷰 무차단·최종 필수 CI11성공, WSL 실제 UI7/pageerror0·웹421·공유 PG9·ICS2파일 독립 파서·PDF9페이지 검수를 마쳤다. 이 수치는 WSL 검증이다. #641 PDF는 브라우저 인쇄 대상에서 PDF 저장을 선택하며, 위치도는 배경지도·도로 경로가 없는 방문 순서 개요다.

## Pinvi 650 주소 검색 진단

**최신 상태: CLOSED.** [Claude Code 운영 결과](https://github.com/digitie/pinvi/issues/650#issuecomment-6670875765)는 Geo 실행 이미지가 구조화 주소 검색 수정 전이었던 것이 원인이며305777d 배포 뒤 원래 약칭/정식명40이 각각 정확1행, 운영 SRCH-004가 통과했다고 기록했다. Pinvi 추가 제품 수정은 없다. 이는 Claude Code의 운영 증거이며 Codex가 직접 수행한 결과가 아니다. 아래 절차는 재발 시 진단용으로 보존한다.

[원래 이슈와 운영 댓글](https://github.com/digitie/pinvi/issues/650)을 먼저 읽는다. 2026-11-05 운영 기록은 약칭과 정식명 모두 Geo 직접 호출에서도 NOT_FOUND/0건이며, 도로명만은67건이다.

- `경북 안동시 풍천면 하회종가길 40`
- `경상북도 안동시 풍천면 하회종가길 40`
- 대조: `하회종가길`

Geo623은 공식202605 보존 원천67행을 실제COPY/generated columns/정본MV/검색SQL/공개 v2 HTTP와 연결했다. WSL에서는 원래40이 약칭·정식명 각각1행이고 40-1/68은 별도다. 런타임 source는 선행 Geo622와 같다. 이 결과만으로 현재 운영의 데이터 누락·배포 회귀를 단정하지 않는다.

1. [Geo 읽기 전용 진단 런북](https://github.com/digitie/kor-travel-geo/blob/main/docs/runbooks/pinvi-650-read-only-diagnosis.md)의 절차로 실제 응답 worker/image·시작 시각을 식별한다. 새로 import한 파일 hash는 이미 실행 중 worker의 메모리 상태를 증명하지 않는다.
2. 같은 endpoint에 원래 입력을 `type=address,page=1,size=8`로 고정해 응답 input/status/total/candidates를 비교한다. 현재 Pinvi는 address를 명시하고 화면 bbox·region hint를 전달하지 않는다. 다른 요청 type이나 잔류 hint로 시험 조건을 바꾸지 않는다.
3. 실제 연결 DB·search_path를 읽기 전용 트랜잭션에서 확인하고 raw `tl_juso_text`와 serving `mv_geocode_target`의 정확한40행·원천 월·관리번호·지상/지하·부번·지역을 비교한다. relation/컬럼 오류는0건으로 바꾸지 않는다.
4. raw에만40이 있으면 적재와 MV 게시 경계를, MV에 정확한40이 있는데 HTTP만0이면 worker·요청·연결 대상·활성 release를 대조한다. 현재 source month와 보존202605가 다르면 공식 원천의 실제 변동을 확인한다. 원인을 확인하기 전에 무조건 재적재·MV refresh·worker 재시작으로 증거를 지우지 않는다.
5. Geo→Pinvi API→브라우저 주소 행을 같은 입력으로 확인한다. 좌표NULL은 주소 후보 삭제 조건이 아니므로 가짜 좌표를 넣지 않는다.

완료에는 운영 원인과 조치 근거, 원래 약칭/정식명40의 정확한 후보, Pinvi 주소 배지 행과 SRCH-004 실행 성공이 모두 필요하다. 현재 SRCH-004는 주소 행 존재만 단언하므로 exact40·부번·지역은 응답을 별도로 대조한다. 원래40을40-1/68로 바꾸거나 없는40-2/999·지하40을 근처 주소로 대체하지 않는다. 공식 보존 자료의40 관리번호는26자리 `47170340472227900004000000`이며 자리수를 추측 보정하지 않는다.

현재 spec은 정상 단언이며 test.fail이 없다. 카탈로그의 과거 종료 기록만 재오픈 상태로 정정한다. 실제 운영 성공을 확인하기 전 #650을 닫거나 #643 체크를 완료로 바꾸지 않는다.

## Map 1450 국립공원 경계 적재

**최신 상태: 최초 적재·운영 검증 완료, 갱신 정책 때문에 OPEN.** [Claude Code 운영 결과](https://github.com/digitie/kor-travel-map/issues/1450#issuecomment-6670520886)는 정식 경계21건·서빙 Polygon·실제 SRCH-028 통과를 확인했다. [Pinvi PR692](https://github.com/digitie/pinvi/pull/692)/d02a35d가 scripted 복귀를 반영했다. 남은 것은 갱신 주기와 다른 미적재 dataset 포함 여부의 소유자 결정이다. 초회 요청을 다시 제출하지 않는다. 아래는 재발 진단 절차다.

[Map1450](https://github.com/digitie/kor-travel-map/issues/1450)은 2026-11-05 zoom7 전국 조회에서 items/clusters가0건이었다는 운영 기록이다. 이 zoom은 시·도 cluster 모드이고 행정코드NULL을 제외하므로 이 응답만으로 DB 전체 area0건을 확정할 수 없다. 국립공원 경계는 `knps_park_boundaries`이고 `knps_protected_areas`는 한국보호지역 데이터다. 후자를 적재했다고 설악산 국립공원 경계를 확인한 것으로 처리하지 않는다.

Map `providers/knps.py`에는 경계를 area/national_park로 변환하는 spec이 있다. 기존 job은 `feature_geometry_knps_records_job`, asset은 `feature_geometry_knps_records`다. geometry 설정 기본값은 `knps_trails`이며 월간 schedule은 설정의 단일 dataset만 갱신한다. 나머지 dataset은 기존 feature update request 경로로 갱신한다.

1. 운영의 dataset 목록·작업 원장·실행 중 작업·마지막 성공/실패를 먼저 확인한다. spec 존재만으로 원천 수집이나 운영 적재 완료를 판단하지 않는다.
2. 설치된 KNPS SDK의 `knps_park_boundaries` 카탈로그·공식 파일 URL/형식·geo extra/공간 파서·CRS를 확인한다. 저장소 카탈로그의 경계는 SHP, MultiPolygon이며 data.go.kr dataset15017313이다. Polygon/MultiPolygon, WGS84 좌표, 원천 식별자와 설악산 명칭을 확인한다. 원천 변경·다운로드/파서 오류는 상세 원인으로 남기고 빈 결과를 성공으로 게시하지 않는다.
3. 기존 운영 pipeline의 `POST /v1/ops/pipeline/requests/preview`로 계획을 확인하고 승인된 기존 경계의 `/requests`로 한 번 요청한다. 생성에는 UUID `Idempotency-Key`가 필요하다. scope는 `type=provider_dataset`, `provider_dataset_id=운영 catalog에서 확인한 실제 ID`, `sync_scope=dataset_wide`, `operation_key=feature_geometry_knps_records_job`이다. baseline ID61을 운영 ID로 가정하지 않으며 옛 provider/dataset 문자열 scope 예시를 복사하지 않는다. dataset은 `knps_park_boundaries`로 한정한다. 실행 snapshot에서 `knps_geometry_records`와 `knps_geometry_dataset_key`의 `config.dataset_key`가 모두 같은 값이고 선언 scope와 일치하는지 확인한다. 일회성 적재를 위해 월간 전역 기본값을 바꾸거나 중복 run을 제출하지 않는다.
4. 기존 job은 authoritative snapshot 경로이므로 일부 자료만 읽고 전체 scope 성공으로 봉인하지 않는다. 정본 적재·삭제/철회·curation 경계를 우회하는 직접 SQL INSERT, 가짜 polygon, point 좌표로 만든 면을 사용하지 않는다.
5. 원장 성공뿐 아니라 source provenance·area subtype·공개 상태를 확인한다. 정본은 MV가 아닌 일반 VIEW `feature.public_features`이며 area는 `feature.feature_areas.geom`의 MultiPolygon/4326과 active/published/valid 상태를 확인한다. MV refresh를 먼저 수행하지 않는다. 이어 실제 서빙 Map API를 확인한다. 설악산과 교차하는 작은 bbox에서 `/v1/features/in-bounds`의 `kind=area,include_geometry=true` 결과가 실제 area와 Polygon/MultiPolygon을 돌려주는지 확인한다. 전국 bbox/zoom7의 집계나 item수만으로 Pinvi의 zoom14 이상 도형 성공을 대신하지 않는다.
6. Pinvi에서 같은 영역의 `/features/in-bounds` 요청은 `kinds=area`를 사용한다. 응답 ID·이름·geometry를 대조하고 실제 canvas hit·목록 선택·상세·큰 bounds 선택 후 zoom14 이상 유지와 선택 보존을 SRCH-028로 확인한다.

SRCH-028의 anchor는 설악산 영역과 교차하는 실제 검색 가능한 근처 point다. 도형 좌표를 가짜 point로 바꾸지 않는다. 이름에 설악산이 들어간 큰 영역이고 전체 영역의 자연 fit zoom이14 미만이어야 해당 검사의 전제를 충족한다. 면을 적재했어도 이 전제를 만족하지 못하면 fixture 조건을 근거와 함께 조정하며 skip을 성공으로 세지 않는다.

현재 KNPS 공용 asset은 authoritative load지만 부재 항목 retirement는 기본 false다. 이 작업을 위해 hard-delete나 부재 retirement 옵션을 추가하지 않는다. 기존 코드의 centroid 범위 검사는 전체 면의 위상·모든 좌표 검증을 대신하지 않으므로 공식 파일의 CRS·geometry도 대조한다.

완료 조건은 공식 국립공원 경계의 성공적인 적재·서빙 geometry·실제 Pinvi SRCH-028 성공이다. 그 뒤에만 카탈로그 SRCH-028을 blocked에서 scripted로 바꾸고 index를 재생성하며 Map1450과 #643 체크를 갱신한다.

## Map 1440과 기존 운영 데이터 잔여

[Map1440](https://github.com/digitie/kor-travel-map/issues/1440)은 #1446 후보 선택 수정이 배포된 뒤에도 WX-004가 실패해 재오픈 상태다. #643의 완료 체크보다 개별 이슈의 [최신 운영 재현 댓글](https://github.com/digitie/kor-travel-map/issues/1440#issuecomment-6628848029)을 우선한다. #1446이 바꾼 빈 표본 후보 선택과 과거 요약 원천의 보관·적재 부재를 구분한다.

1. 실제 Pinvi의 `PINVI_KOR_TRAVEL_MAP_WEATHER_ENABLED`와 실행 경로를 확인한다. 테스트의 `PINVI_E2E_WEATHER_VIA_MAP`을0으로 낮춰 직접 경로 no_data를 허용하는 것으로 Map 회귀를 해결하지 않는다.
2. 새 D-5 도산서원 fixture로 Map의 과거14일 `daily_summaries` 계약과 실제 원천/보관 기간·수집/적재·시각 기준을 대조한다. 오래된 테스트 날짜가 보관 기간 밖으로 밀린 경우와 현재 D-5의 원천 부재를 나눈다.
3. 실제 Map 응답과 Pinvi 여행 응답의 요약 kind·날짜·아침/점심/저녁·단위를 확인한다. 원천이 없는데 값을 만들거나 현재 예보를 과거 요약으로 대체하지 않는다.
4. 원인·조치와 실제 WX-004 성공을 확인한 뒤에만 test.fail 표식·이슈·카탈로그를 갱신한다.

[Map1438](https://github.com/digitie/kor-travel-map/issues/1438)은 코드상 CLOSED지만 [마지막 운영 댓글](https://github.com/digitie/kor-travel-map/issues/1438#issuecomment-6628849031)은 MCST/MOIS 재적재 전 데이터 대기를 남긴다. SRCH-019/020/022와 NEAR-030은 실제 재투영 후 재검증한다. 시설명·브랜드로 업종을 추측하지 않으며 공식 원천 대조로 확인하지 못한 시설은 미분류를 유지한다.

## 운영 E2E 실행 순서

운영 접속과 변경은 Claude Code가 각 저장소의 비공개 운영 접근/배포 런북과 기존 preflight를 따른다. 자격증명·운영 주소는 추적 문서나 명령 인자/리포트에 복사하지 않는다. Pinvi는 [live catalog 실행 절차](live-e2e-catalog.md), 배포는 [deploy.md](deploy.md), 관측은 [observability.md](observability.md)를 따른다.

검증할 clean checkout과 실제 배포 revision을 먼저 맞춘다. 다음 명령은 운영 담당의 실행 순서이며 이 PR의 WSL 실행 결과가 아니다.

```bash
: "${PINVI_LIVE_EXPECTED_REVISION:?실제 배포한 Pinvi full SHA를 먼저 고정}"
test "$(git rev-parse HEAD)" = "$PINVI_LIVE_EXPECTED_REVISION"
scripts/n150-live-catalog.sh --list --area search --area weather --project desktop --grep 'SRCH-(004|028)|WX-004'
scripts/n150-live-catalog.sh --area search --area weather --project desktop --grep 'SRCH-(004|028)|WX-004'
```

`PINVI_E2E_GEOMETRY_AREA_ANCHOR_QUERY`는 기존 root 소유 mode600 E2E env 파일에 실제 확인한 point 검색어로 설정한다. catalog의 sudo 재실행은 임의 shell 변수를 모두 보존하지 않으므로 호스트에서 변수 하나를 앞에 붙였다는 이유만으로 container 전달을 가정하지 않는다.

#691은 Docker 전달 허용 목록에 위 키와 `PINVI_E2E_GEOMETRY_SEORAK_ANCHOR_QUERY`, `PINVI_E2E_GEOMETRY_BUKHAN_ANCHOR_QUERY`를 추가한다. 이름으로만 전달하고 값은 argv에 넣지 않는다. N150 host·exact checkout·고정 이미지·새 npm ci guard는 유지한다. WSL 실제 Bash 구성 회귀에서 수정 전3실패, 보완 후 신규4/관련26통과를 확인했다. 이는 N150 컨테이너·운영 UI 실행을 대신하지 않는다.

표적 세 건 후 search/nearby/core/share/weather/notify/admin/trip/poi를 최종 회귀한다. blocked·skip·manual과 실제 pass를 분리하고 결과의 API/웹/Map/Geo/Weather revision·image digest, 실제 fixture, 원인·조치, pass/fail/skip, 민감값을 가린 증거를 남긴다. #653의 실제 UUID별 상한 설정·기존 임시 allowed6건 정리, #667 관리자 명시 GC, #668 미확정 명령 확인, #636/#638/#637의 실제 Telegram 대상·예약·Prometheus Docker 실행 확인과 인증 scrape, #641 인쇄/PDF/ICS도 운영 인계 범위다. 운영 Prometheus가 없으면 Manager 소유의 정본 Compose 절차로 띄우고 실제 API target과 발송/실패 고정 label을 확인한다. 실제 전송은 승인된 전용 테스트 대상만 쓰며 일반 사용자 대상에 보내지 않는다.

## 추가 묶음과 남은 운영 확인

2026-11-06 개별 이슈·최신 운영 댓글을 다시 확인했다. 오래된 우산의 미체크만으로 실제 운영 상태를 덮어쓰지 않는다.

| 항목      | 현재 근거와 남은 범위                                                                                                                                       |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| #658      | PR694/a5a2154로 WSL 소유 PG 잠금 지연 회귀·독립2리뷰·적용CI8성공 뒤 병합, CLOSED.                                                                           |
| #616·#621 | PR695/a3129a9로 WSL 구현·검증 병합. #616 CLOSED, #621은 운영 flag·edgeHTTP2·지연/pool/worker 확인으로 OPEN 유지.                                            |
| #618·#623 | PR693에 검사 격리·실제 지도 가림·선택 위치/offset을 함께 보완. 이 PR의 Closes 대상이며 운영 배포는 Claude Code가 담당.                                      |
| #686      | PR693의 layer/ID 선택·정확 응답/본문·native viewport oracle과 WSL 실제UI8흐름으로 보완. 원래 운영 NEAR024/025/006·CORE025 재실행 뒤 Claude Code가 종료한다. |
| #650      | Geo 배포와 원래 SRCH004 운영 성공으로 Claude Code가 CLOSED. 2문자 Geo query timeout은 별도 관측이며 이 결과로 해결됐다고 하지 않는다.                       |
| Map1440   | 과거 daily_summaries 원천/보관/실행 경로와 WX004 운영 재검증으로 OPEN.                                                                                      |
| Map1450   | 공식 국립공원 경계21건·SRCH028 성공 및 PR692 반영 완료. 갱신 정책/추가 dataset 선택 때문에 OPEN.                                                            |

검증 근거는 [PR693 WSL 실제 UI 기록](../reviews/pinvi-618-623-686-wsl-ui.json), [PR695 API 기록](../reviews/pinvi-616-621-wsl-resilience.json)과 각 PR 최종 댓글이다. Codex는 운영/SSH·실제 provider·Telegram을 호출하지 않았다. #671/#672 보호 stash와 다른 Code의 upstream PR30도 보존했다.

### 새 배포 후 우선 확인

Pinvi는 PR695의 API와 PR693의 web을 함께 적용한 정확 revision을 기록한다. 독립적으로 낡은 web/API를 섞어 비교하지 않는다. source/tree·lockfile·image gate와 정본 Manager 절차를 유지한다.

- #686의 원래 네 케이스를 desktop/mobile로 실행한다. 같은 이름의 feature/transport는 실제 interaction ID로 구분하고 정상 클릭의 상세 HTTP200·본문 ID를 확인한다. 강제 dispatch로 다른 마커를 누르지 않는다.
- 선택 SVG 끝점과 native projection, 경로/영역·교통 패널과 통계 칩의 교차, 선택 offset, 사용자 드래그 중 지연 응답을 확인한다. 고정 높이 스택의 내부 패널 변경도 관찰한다.
- #621의 직접 날씨 cold miss는 즉시 Pending/빈 카드이며 배경 single-flight 후 warm hit가 된다. durable outbox처럼 누락 없는 수행을 가정하지 않는다. pool acquisition 대기·관측 손실·회로/포화 counter를 운영 latency와 함께 확인한다.
- mocked suite는 전용 reserved API/Grafana origin과13805를 사용한다. live env·실제 제공자를 섞지 않는다. context/page request·HTTP redirect·서버 proxy/optimizer도 guard 대상이다.
- live runner의 variadic project 오류는 PR693에서 --project=값으로 수정했다. WSL 실제 --list로 단일/반복 area·project2건을 확인했으며 이 검사는 운영 실행이 아니다.

Map1438의 MCST/MOIS 운영 재투영과 분류 재검증, Telegram 전용 테스트 대상·Prometheus 인증 scrape 및 나머지 최종 운영 카탈로그는 기존 인계 범위를 유지한다.

## SDK57 패치 정합성과 남은 Map 조사 (PR696)

[Pinvi PR696](https://github.com/digitie/pinvi/pull/696)은 root/mobile Expo를 57.0.32로 함께 맞추고 SDK57 권장 6개 직접 패치를 반영한다. React/RN override·기존 install.exclude·CI 필수 여부는 유지한다. Expo doctor 21/21, Node22.23.1/npm12.0.1 clean 설치, lockfile integrity 100%, 전체 workspace lint/typecheck·unit608과 Android/iOS Hermes·web static Metro export를 WSL에서 확인했다. 수동 expo-router symlink는 사용하지 않았다. production Next + Chromium UI202통과/기존3skip도 확인했다. 세부 증거는 docs/reviews/expo-57-patch-alignment.json에 기록한다. 이 결과는 native Dev Client 기기 실행·EAS build·운영 배포를 포함하지 않는다.

Map1440 읽기 전용 코드 재검토에서도 새 소스 결함은 확정하지 못했다. Map은 과거 daily_summaries 슬롯을 요청하며 Pinvi도 지난 날짜를 해당 계약으로 전달한다. Weather의 14일 요청 범위는 실제 관측 요약 보관을 보장하지 않고, raw 사실이 자동으로 summary로 재집계되지 않는다. 실제 D-5는 31일 보관 pruning으로 설명할 수 없다. 같은 location_id·D-5로 Weather 저장 요약/coverage·publisher checkpoint → Map W5 표본/실행 상태 → active generation의 동일 슬롯 → Pinvi 응답을 대조하고 원래 WX-004 성공을 남긴다. 코드의 publisher/W5 기본 STOPPED는 실제 운영 활성화 상태의 증거가 아니다. 최근접 후보 선택 정책은 실제 표본 없이 변경하지 않았다.

Map1450은 경계21건·SRCH028·scripted 복귀가 Claude Code 댓글상 완료다. 갱신 정책은 선택 대기이며 기존 월간 trails schedule은 유지한다. 향후 경계 schedule을 추가한다면 기존 geometry job을 공유하면서 두 resource와 dataset_wide scope 모두 자연키 knps_park_boundaries를 명시해야 한다. 같은 job을 중복 등록하거나 운영 숫자 dataset ID를 고정하지 않는다. 현재 '지금 실행'은 schedule run_config 대신 기본 job을 실행하므로 경계 전용 실행을 보장하는 보강도 필요하다. 이번에는 schedule 정의·DB 활성화·운영 적재를 변경하지 않았다.
