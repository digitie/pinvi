# #616·#621 외부 호출 계약과 복원력 WSL 실행계획

## 기준·책임 경계

- 사용자 지정 기준은 `ff5c2386c22412714b42365fd3ab801502258087`이다. 원격 main이 전진해도 메인 안내 전에는 통합하지 않는다.
- 작업은 Linux native 도구와 `agent/codex-616-621-resilience`, 전용 `pinvi-codex-616-621` worktree에서만 수행한다.
- 2026-11-06 GitHub #616·#621 최신 본문·댓글을 직접 조회했다. #616 댓글은 없고 #621에는 직접 weather resolve 경로를 추적하는 추가 댓글이 있다.
- 운영·SSH·실제 provider·Telegram 접근은 금지한다. prod·edge HTTP/2·운영 플래그·worker 증설은 Claude Code 소유다.
- frontend #618/#623/#686 및 다른 작업자의 변경은 건드리지 않는다. 보호 stash를 적용하지 않으며 0105 이하 migration은 불변이다.
- API clients/middleware/core와 해당 tests·필요한 forward migration·문서만 소유한다. 최종 두 전문 적대리뷰·ready 전환·merge는 메인이 수행한다.

## 착수 시 소스 재분류

| 항목 | 확인 상태 | 이번 조치 |
| --- | --- | --- |
| #616 outer envelope 세 곳 | 최신 이슈가 정확 키 집합 검사를 지목한다 | 필수 키·타입·상태 의미는 보존하고 additive 키를 무시한다. 위치·키 집합별 warning 1회를 검증한다 |
| signed receipt·증명 | exact 검사가 보안 경계다 | 완화하지 않고 기존 반례를 재검증한다 |
| #621 시작 시각 tracker 누수 | 현재 `request.extensions` 사용으로 이미 해결됨 | 재구현하지 않는다 |
| response hook DB 저장 | 현재 새 session의 INSERT·COMMIT을 inline await함을 CodeGraph로 확인 | bounded batch queue, 즉시 enqueue, 별도 flush·실패/drop 계수·종료 lifecycle을 구현한다 |
| timeout·연결 실패·취소 로깅 | response hook만으로 기록이 불가능하다 | 기존 httpx 계약에 맞는 예외 경로 기록, 중복 방지와 redaction을 검증한다 |
| rate limit | Postgres backend·override 소비자 영향도 확인 | 한 statement로 override 결정·atomic counter를 처리하고 만료 정리는 요청 밖 주기 작업으로 분리한다 |
| provider bulkhead·회로 | source 재분류가 더 필요하다 | weather·Map·geo별 포화 즉시 실패, timeout 회로의 긴 복구 간격, 취소 시 슬롯 반환을 구현한다 |
| pool | source 재분류가 더 필요하다 | 명시 max_overflow·짧은 timeout·실제 acquisition 대기 관측을 검증한다 |
| #621 추가 댓글의 직접 resolve·예산·느린 5xx | 현재 구현과 소유 서비스 경계를 추가 확인한다 | 이미 완료된 부분을 재작성하지 않는다. 남은 범위와 이 작업의 비소유 서비스를 정확히 보고한다 |
| edge HTTP/2·운영 flag·worker | WSL 미검증·Claude prod 소유 | #621은 자동 종료하지 않는다 |

## 구현 순서·병행 소유권

1. 이 한국어 계획과 착수 기록을 먼저 commit·push하고 Draft PR을 생성·첨부한다.
2. CodeGraph explore/impact를 선행한 뒤 병행한다. 작업 A는 #616의 세 client와 해당 회귀, 작업 B는 rate limit과 해당 회귀, 주 작업은 logging·provider·pool 및 lifecycle 통합이다. 공용 파일의 편집 충돌은 주 작업이 조율한다.
3. 기존 코드에서 실패하는 의미 있는 반례를 먼저 실행한다. 단순 내부 구현 모양만 단언하는 검사를 피한다.
4. 단위·실제 소유 Postgres·소유 HTTP fixture로 성공·실패·timeout·취소·포화·종료·redaction·공개 오류 계약을 검증한다.
5. 단계별 보안 감사·짧은 원격 commit을 유지하고 최종 정확 SHA·source hash·명령·증거·한계를 PR에 반영한다.

## 검증 및 안전 조건

검증 실행 전 명령과 목적지를 확인한다. prod env를 source하지 않으며 실제 provider URL·자격증명을 사용하지 않는다. DB는 WSL 소유 fixture만 쓰고, HTTP는 loopback fixture 또는 명시적 MockTransport로 제한한다. Linux Python/uv·git·CodeGraph·npm만 사용한다. 각 commit 직전에 본인 cwd에서 `python3 /home/digitie/.cache/pinvi-643/audit-staged.py`를 실행한다.

검증 예정: 관련 pytest unit/integration, 실제 PG의 override·counter 경합/만료 청소, bounded logging batch·DB 실패/종료·취소, provider별 HTTP timeout/포화·공개 unavailable 계약, pool wait 관측, Ruff/format·mypy·import 경계. 실행 결과와 실패 우선 증거는 완료 시 갱신한다. UI 변경은 없으며 운영 UI/edge 검증은 수행하지 않는다.

## 진행 상태

- [x] 지정 기준 worktree 생성, Linux native 도구 확인, CodeGraph 인덱스 초기화·explore/impact.
- [x] GitHub 최신 본문·댓글 확인, 구현 전 실행계획 작성.
- [x] 계획 commit·push·Draft PR 생성: 계획 4776d0d, Draft PR #695.
- [x] 소유 범위 실패 우선 회귀·구현·실제 fixture 검증.
- [x] 정확 최종 검증 SHA f99e9b396b393a5d3e001bd39b7bec96502ff940·source hash·WSL 증거·한계 기록. 최종 문서 commit SHA는 PR head로 인계한다.

PR 종료 문구는 #616 완료 검증 뒤에만 `Closes #616`을 사용하고, #621에는 `Refs #621`만 사용한다.

## 중간 검증

- #616 담당 작업: additive 세 경로 수정 전 3 FAIL, 관련·보안·설정 검사 148 PASS. receipt·event·fingerprint exact 검사는 보존했다.
- rate limit 담당 작업: 실제 소유 PG에서 기존 3 statement 반례 1 FAIL → 한 statement와 관련 unit/PG 70 PASS(26.51초). concurrent 12요청·override 우선순위·만료/철회·SKIP LOCKED·취소·공개429/503/fail-open·handler 1회 계약을 확인했다.
- logging/runtime 주 작업: inline DB 대기 반례 실패 후 신규 unit 12 PASS. 실제 소유 PG와 loopback HTTP의 성공/503·read timeout·connect failure 기록 및 pool 대기/timeout/취소 7 PASS(14.55초).
- pool 구현은 core의 관측 pool을 사용하며 실제 생성 지점인 app/db/session.py에 최소 배선 4줄을 추가했다. 설정은 pool size 10, max_overflow 0, pool_timeout 5초가 기본이며 운영 적용/부하 튜닝은 미검증이다.
- provider 회귀는 기존 코드에서 포화 대기·timeout 재전송·늦은 결과 회로 오염 7 FAIL을 확보했다. 구현 및 통합 검증은 진행 중이다.
- 직접 weather resolve는 아직 서비스 요청 경로에서 inline await한다. 서비스 재설계는 이번 clients/middleware/core 소유 범위 밖이며 #621 잔여로 남긴다. edge HTTP/2·운영 flag·worker와 함께 #621 자동 종료를 금지한다.

## 구현 중간 저장

- 공통 기록 큐는 factory별 1개이며 대기 1024행 + 전송 중 최대100행이다. 0.25초/최대100행 배치, DB flush2초·종료3초 상한을 둔다. 실패·포화·종료 손실은 고정 outcome counter로 집계한다. 이 큐는 감사/업무 outbox가 아닌 손실 허용 관측이다.
- provider factory의 ApiCallLoggingClient가 전송·body read 오류와 취소를 기록하고 원래 예외를 다시 올린다. endpoint는 기존 redaction을 적용하며 임의 예외 메시지는 저장하지 않는다. 기록 시각은 enqueue 시각이다.
- 기존 최외곽 Map client lifespan에 logging drain과 rate-limit cleanup을 연결했다. main.py와 runtime/서명 guard는 변경하지 않았다.
- Map·geo·weather 사용자 client의 독립 bulkhead 기본16, 회로120초, 단일 half-open·세대 fencing을 구현했다. Map weather는 기본 Map client의 bulkhead를 공유하고 로컬 포화/PoolTimeout은 회로 장애로 세지 않는다. admin/curation 등 별도 command client까지 하나의 전역 Map cap으로 묶지는 않았다.
- 전체 API unit 2084 PASS/기존9 SKIP(98.32초), 전체 strict mypy274파일, Ruff/format518파일 통과. 세 provider 실제 loopback HTTP+소유PG 검사3 PASS(14.13초)이다. 공개 오류 계약을 포함한 확장 통합 검사는 진행 중이다.

## 최종 WSL 검증

- 제품 코드 기준674602e00f1a269970db4e7c695e30773062da52. 추가 공개 계약 검사는 동일 제품 소스에 테스트만 보강했다.
- 관련 API/실제PG 통합134 PASS(88.55초), 실제3provider HTTP·공개503 오류계약7 PASS(15.54초, 앞선134중3건과중복)이다.
- 공개 계약 신규 검사의 초기 data/meta 가정은 현재 error-only 계약과 달라4건 실패했고 문서/handler 확인 후 테스트만 정정했다. 이 실패를 제품 결함의 실패 우선 증거로 계산하지 않는다.
- pool 관측을 기본 pool로 교체한 별도 negative control은 실제PG1 FAIL이었다. 정상 구현에서는 acquisition 대기·timeout·취소 metric과 후속 연결을 모두 통과했다.
- 최종 증거 JSON은 docs/reviews/pinvi-616-621-wsl-resilience.json에 source SHA-256·명령·집계·제약을 담는다.
- 추가 plain httpx service/routes의 OAuth·Telegram 호출부 전환은 clients 소유 범위 밖이다. event hook만 부착한 client의 response 없는 실패 기록은 후속으로 남는다. 실제 Telegram 접근은 수행하지 않았다.

최종 고정 f99e9b3에서 전체 API unit 재실행은 2084 PASS/기존9 SKIP(104.59초)이며 실행 전후 변경 source SHA-256이 전부 일치했다. 최종 Ruff/format519파일·strict mypy274파일·diff 검사도 통과했다.
