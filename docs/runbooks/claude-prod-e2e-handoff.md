# Claude Code 운영 검증 인계

2026-11-06 기준 #643 후속 구현은 머지됐으며 우산에서 직전 미완료로 남은 항목은 Pinvi #650과 Map #1450이며, 이번 열린 이슈 감사에서 Map #1440의 재오픈도 확인했다. Codex는 WSL 작업·검증·머지, Claude Code는 운영 진단·필요한 적재·최종 UI 검증을 담당한다. 아래 머지 SHA는 운영 배포 완료를 뜻하지 않는다.

## 머지 내역과 실행 기준

Pinvi 제품 기준은 `efc01affd4267e4e6c75411db3cb902e38d2c7aa`, Map은 `27033b116d8d7328689b19a20de830417937dd73`, Geo는 `305777d561a98588e310756981d3a984908be2ee`, Weather는 `d8534aeae8852f9c514e39d625ea7dded956f3ed`다. 운영 시작 시 각 서비스의 실제 실행 image digest/revision·worker 시작 시각과 이 변경의 포함 여부를 확인한다. Pinvi revision만으로 Map/Geo/Weather의 실행 버전을 대신하지 않는다. 이후 릴리스를 쓰면 실제 전체 SHA와 변경 포함 관계를 기록한다.

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
| [kor-travel-map #1448](https://github.com/digitie/kor-travel-map/pull/1448)                     | MCST SDK 승인형 CSV와 데이터셋별 적재 결과를 반영                                        | `dd0238c3` |
| [kor-travel-map #1451](https://github.com/digitie/kor-travel-map/pull/1451)                     | fix(admin): safely reconcile uncertain feature commands                                  | `27033b11` |
| [kor-travel-geo #623](https://github.com/digitie/kor-travel-geo/pull/623)                       | test(search): 공식 Juso 원천으로 Pinvi 전체 주소 회귀 확인                               | `305777d5` |
| [kor-travel-weather #201](https://github.com/digitie/kor-travel-weather/pull/201)               | feat: 명시적 기상특보 이벤트 조회 계약                                                   | `d8534aea` |
| [kor-travel-docker-manager #582](https://github.com/digitie/kor-travel-docker-manager/pull/582) | fix(pinvi): deliver bounded user rate limit settings                                     | `20868ab3` |

#678은 다른 Code가 처리한 #671/#672이며 기존 병합을 포함했을 뿐 재구현하지 않았다. 보호 stash `owner-skip-671-672-other-code-in-progress`는 복원하지 않는다.

검증 증거는 Pinvi `docs/reviews/`의 이슈별 JSON과 각 PR 최종 댓글에 있다. #690은 두 독립 전문 적대 리뷰 무차단·최종 필수 CI11성공, WSL 실제 UI7/pageerror0·웹421·공유 PG9·ICS2파일 독립 파서·PDF9페이지 검수를 마쳤다. 이 수치는 WSL 검증이다. #641 PDF는 브라우저 인쇄 대상에서 PDF 저장을 선택하며, 위치도는 배경지도·도로 경로가 없는 방문 순서 개요다.

## Pinvi 650 주소 검색 진단

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

## 체크리스트 밖의 추가 열린 이슈

이번 감사 시점 #643은 GitHub에서 CLOSED이며 본문 미체크는650/Map1450 두 건이었다. Map1440은 개별 이슈가 재오픈되어 우산의 완료 기록도 정정해야 한다. 전체 저장소의 모든 이슈가 끝났다는 의미는 아니다. 2026-11-06 Pinvi의 열린 이슈는 다음7건이며 별도 조사/작업 범위를 유지한다. 관련 PR이 머지됐다는 이유만으로 원래 운영 재현을 완료 처리하지 않는다.

- [616 Map 응답 envelope 정확-집합 검사 3곳을 런타임 검증으로 (additive 변경 내성)](https://github.com/digitie/pinvi/issues/616): OPEN.
- [618 N150 mocked e2e: mock 안 된 API 호출이 localhost:12801(운영 PinVi API)로 샌다](https://github.com/digitie/pinvi/issues/618): OPEN.
- [621 PinVi 의존 서비스 지연 대비 복원력 — 남은 항목(로깅 outbox·rate limit·동시성 상한·풀 설정·edge HTTP/2)](https://github.com/digitie/pinvi/issues/621): OPEN.
- [623 여행 지도 기존 결함 3건 — 모바일 통계 칩이 남쪽 핀을 가림·선택 마커 CSS scale 위치 이동 의심·선택 POI flyTo offset 없음](https://github.com/digitie/pinvi/issues/623): OPEN.
- [650 통합 검색: 전체 도로명 주소(시·도 약칭) 질의에 주소 행 0건](https://github.com/digitie/pinvi/issues/650): OPEN.
- [658 restore hotswap cleanup 반환 직후 advisory lock 해제 검증 경합 조사](https://github.com/digitie/pinvi/issues/658): OPEN.
- [686 #677 이후 운영 지도 케이스 잔여 실패 — NEAR-024(desktop 맞춤 중심)·CORE-025/NEAR-025(mobile)·NEAR-006(휴게소 상세 미오픈)](https://github.com/digitie/pinvi/issues/686): OPEN.

#616은 additive envelope와 서명 경계를 구분한 회귀, #618은 mocked E2E의 미등록 API 요청 차단, #621은 이미 보완된 항목과 남은 로깅/동시성/풀/edge를 재분류한다. #623과 #686은 실제 제품 결함·marker/카메라·helper 실패를 각각 재현해 구분하며, #658은 소유 DB에서 클라이언트 종료 뒤 서버 lock 해제 지연과 지속 잔류를 나눈다. 이 항목들을 현재 두 운영 이슈가 해결된 것으로 함께 닫지 않는다.

Map 열린 이슈는 #1440·#1450 두 건이고 열린 PR은0건이었다. Pinvi 열린 PR은 이번 인계/러너 보완 #691이다. #1438의 운영 데이터 대기는 CLOSED 이슈의 후속 검증으로 별도 기록한다.
