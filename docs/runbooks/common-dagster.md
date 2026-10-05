# PinVi Common Dagster 적용 (T-370 / ADR-072)

## 정책과 소유권

Common Python `73e3ff8b9398e533806d2d1a8435292570169de3`를 exact Git dependency로 고정한다.
Common UI는 `e28559803c1ec1134ef7ba7736b9acf4cadb9a32`의 dev.6, tokens는 `426de4fbad35282bb558712d922c06268e9aba62`의 고정 tarball이며
`apps/web/vendor/kor-travel-common-PROVENANCE.md`에 SHA256·GPL 출처를 남긴다.
공통 구현 가이드는 [Common runbook](https://github.com/digitie/kor-travel-common/blob/main/docs/runbooks/dagster-adoption.md).
PinVi는 app 데이터와 JWT/cookie·DB 역할 검사만 소유한다. Map provider 구현은 가져오지 않는다.

8개 named job의 최대 실행 시간은 3600초다. 읽기 전용 email/telegram outbox 집계,
PII retention dry-run, 위치 archive dry-run, weather horizon 조회 5개만 인프라 실패 1회 재시도한다.
provider 오류·일반 step 오류·혼합 실패·부분 실행·취소는 자동 재시도하지 않는다.
KASI upsert와 trip-day 보강은 자동 retry 0이며 다음 schedule 또는 원인 수정 후 수동 실행한다.
7개 schedule은 같은 location/job의 QUEUED/STARTING/STARTED/CANCELING이 있으면 coalesce한다.
storage 조회 실패를 빈 상태로 간주하지 않는다. Common 센서는 native retry가 활성화되어 있으면
native에 위임하고, 비활성 인스턴스에서만 bounded cursor 기반 fallback을 제공한다.

## 배치와 메모리

executor step 동시 실행 1, DB pool 1/overflow 0, DB connect/command/lock timeout을 사용한다.
KASI는 provider page를 순회하며 100행 또는 raw 1MiB 단위로 commit한다(단일 raw 64KiB 제한).
month 범위는 각 0..36, page당 100행·월/dataset당 100페이지·전체 정규화 10000행 제한이다.
provider page fetch는 retry를 포함해 60초 이내다. 전체 결과 list와 전량 SQL parameter를 만들지 않는다.
**배치별 commit**이므로 뒤 배치 실패 시 앞 배치는 남는다. unique identity/upsert와 fetched_at 조건으로
재실행을 안전하게 처리하고 오래된 writer가 최신 payload를 덮지 못한다.
tracemalloc의 합성 5000행 결과는 Python allocation만 측정한다. 운영 RSS 보장은 아니다.

## Admin 계약과 복구 UI

GraphQL은 PinVi repository selector/tag로 제한한다. 최근 30건에 active run(최대 1000)을 병합한다.
1000건 cap·active 조회 오류는 degraded로 표시하며 완전한 결과인 척하지 않는다.
최대 응답 4MiB·전체 probe 10초이며 schedule/sensor tick은 최근 3개의 상태/시각만 읽는다.
실패 probe count는 **null**이다(0이 아님). Python DTO·TS/Zod·OpenAPI export를 함께 갱신했다.
`docs/api/admin-dagster-openapi.json`의 component drift는 actual app.openapi()로 검사한다.
Common 대시보드는 마지막 정상 snapshot 1개를 장애 중에도 유지하고 오류와 새로고침을 제공한다.
30초 polling·AbortSignal·60초 GC와 공통 50행 pagination을 사용한다.
LoginForm/AppMenu는 공통 표현을 쓰되 API RBAC·cookie는 PinVi의 기존 정본이다.

## 운영 인스턴스 전제

consumer YAML 변경은 **공유 Manager daemon을 바꾸지 않는다**. 배포 시 공유 plane의
run monitoring enabled, start timeout, max runtime, tag concurrency
`kortravelcommon/job` unique value별 limit 1, bounded 전체 queue를 별도로 확인한다.
자체 인스턴스 YAML은 전체 run 2, job별 1, monitor poll 60초/start 300초, resume 0이다.
중단된 worker는 monitor가 terminal 상태로 확정해야 coalescing이 풀린다. 원인 확인 없이
실행을 success로 바꾸거나 active worker가 살아 있는데 재실행하지 않는다.
notification outbox의 기존 best-effort 전달 보장과 trip-day 부분 실패의 metadata 의미는 바꾸지 않았다.
초기 T-370 검증에는 실제 배포·공유 daemon 재시작·운영 데이터 초기화를 포함하지 않았다.
이후 Map paired 운영 재구축의 범위와 증거는 아래 후속 절을 따른다.

## 초기 T-370 검증 범위

ETL 실제 Dagster persistent instance의 active coalescing/terminal 해제, definitions 로드,
retry allowlist 및 KASI bounds/allocation 회귀를 검사한다. API는 scope·older active·cap·tick·stream cap을 검사한다.
UI는 semantic outage 후 stale 유지/복구, invalid email focus/password clearing, nonadmin logout을 검사한다.
N150 live UI는 고정 dev 포트를 별도 network namespace 안에서 사용하며 운영 host port를 점유하지 않는다.
운영 서비스·운영 DB는 사용하지 않고 별도 빈 fixture DB와 실제 API/GraphQL을 연결한다.
최종 review/live/CI 결과와 SHA는 journal/증거 문서에 기록한다.

## Code location 실제 로드 확인

조립용 `Definitions` 객체를 모듈 전역에 남기지 않는다. private 이름도 Dagster 자동 탐색 대상이다.
최종 `defs`만 노출한 뒤 `dagster job list -m pinvi.etl.definitions -d apps/etl`을 확인한다.
Python import 성공만으로 gRPC code location 로드가 보장되지는 않는다.
최종 결과는 [검증 기록](../reviews/common-dagster-2026-10-05/README.md)을 따른다.

## Map paired 재구축 후속 HTTP 채택

API 전송은 Common `1f8e339c7c79f86f8952b0d4c326ab4dae56bee8`의 `[http]` extra를 소비한다. 4 MiB plain 응답/전체 10초·압축 사전 거부·별도 연결 정리 제한을 공유하고, JSON 객체·PinVi 소유권·활성 run·재시도 계약은 앱이 유지한다. Common은 GPL-3.0-or-later이며 API 배포는 공통 의존성의 라이선스·소스 고지를 함께 유지한다. 기존 UI dev.6 산출물과 ETL RecoveryPolicy는 변경하지 않는다. 관리자 Map snapshot 변경은 원천 commit/bytes를 함께 재vendor하고 M05 pair 계약을 재생성한다. 운영 재구축/live 결과는 후속 [검증 기록](../reviews/common-map-rebuild-2026-10-05/README.md)에 따로 보존한다.

## 최신 tick 요약의 저장소 작업 상한

`ticks(limit: 3, statuses: [STARTED, SKIPPED, SUCCESS, FAILURE])`로 Dagster 1.13.24의 전체 이력 batch rank 조회를 피한다. 네 상태를 모두 선택하여 실패 tick을 숨기지 않고 instigation별 최신 최대 3건을 표시한다. 운영 Map의 sensor tick storage statement timeout을 재현하고 같은 query의 정상 응답을 확인했다. Dagster upgrade 때 schema enum과 resolver 경로를 재검증하며 HTTP deadline·응답 cap은 계속 적용한다. 실제 재구축과 브라우저 검증은 해당 [검증 기록](../reviews/common-map-rebuild-2026-10-05/README.md)을 따른다.
