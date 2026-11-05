# #636/#637/#638 — Telegram 일정·특보·예약 알림 묶음

## 범위

- #636: 관리 가능한 여행 전체/특정 일자의 장소·도착/출발(KST)·메모를 연결된 Telegram 대상에 plain text로 전송 요청한다. UI에서 연결 대상·전송 결과와 실패 원인을 확인한다.
- #637: 여행 기간·POI/대표 지역의 실제 특보 원천을 확인한다. 특보별 발령/해제를 durable occurrence로 중복 enqueue하지 않는다. 실패·부분/불확실 응답에서 해제를 추정하지 않는다.
- #638: 사용자별 opt-in과 KST 시각을 저장한다. 일간은 전날/당일 일정, 주간은 최신 이슈의 다가오는 여행 목록으로 구현한다. 기존 문서의 단일 여행7일 전 예시와 차이를 명시한다. 요일·시각은 설정 UI에서 고른다.

기존 대상 연결/검증·공유 역할 정책을 사용한다. 새 메시지에 원문 token/chat credential·공유 토큰·로그/stack trace를 넣지 않는다. 색상·기존 컴포넌트 톤을 유지한다.

## 전달·저장 경계

- 중복 사용자 요청/복수 planner의 occurrence를 DB 유일성으로 제어하고, 대상/연결·설정·권한이 바뀐 경우 전송 직전 재검증한다. 비활성·미검증·삭제/이동한 대상은 보내지 않는다.
- 긴 메시지는 순서를 보존한 chunk로 나누며 대상별·chunk별 진행 상태를 영속화한다. 실패 재시도에서 이미 확인된 성공을 되풀이하지 않는다. Telegram API가 제공하지 않는 exactly-once를 주장하지 않는다.
- provider의 양의 정수 Retry-After와 backoff를 존중한다. UI에 안전하게 정제한 오류 원인·재시도/일부 전송 상태를 보여 준다.
- 예약은 Dagster schedule이 처리하되 API 사업 로직 모듈을 ETL에서 import하지 않는다. 기존 승인된 내부 HTTP/서비스 경계를 조사해 선택한다. 공유 Dagster·worker 중복 실행/재시작과 opt-out/대상 재연결 경합을 테스트한다.
- 특보가 Weather marker/latest에 존재함을 최신 API 계약에서 확인했다. 안정적 식별자·발령/해제/유효기간·지역 해석을 실제 원천 코드로 확인한 뒤 소비한다. 필요하면 owner 계약을 먼저 보완하고 소비자를 sync한다.
- 기존 outbox 운영 요약/telemetry에 새 카테고리·실패/지연을 연결하며 개인정보를 label/metadata로 내보내지 않는다.

## 검증·리뷰

초안 PR부터 만들고 단계별 remote commit한다. 실패 우선/실제 PostGIS·권한/동시성·클럭·대상 변경/opt-out·chunk/429/불확실 전송·일간/주간 발생키·특보 발령/해제와 실패 응답 대조를 검증한다. Bot API 공식 문서를 확인한다.

실제 웹/API/DB와 소유 로컬 Telegram provider fixture로 live UI E2E를 실행한다. 실제 Telegram 수신자에게 메시지를 보내지 않는다. 두 독립 전문 적대리뷰를 다각도로 진행하고, 정확 최종HEAD의 모든 적용CI를 확인한 뒤 일반 squash merge한다.

사용자 최신 지시에 따라 WSL에서만 검증하며 운영 접근·배포·시험은 하지 않는다. 최종 prod는 Claude Code 담당이다. #671/#672의 다른 Code 작업·보존 stash는 건드리지 않는다.

## 직전 완료와 남은 작업

- Pinvi684/PR687은6f47dad로 병합했다. 정확21e1 두최종리뷰 무차단·CI9SUCCESS, API1988/관련PG88/실제UI5를 확인했다.
- Geo623은305777d로 병합했다. 보존202605 공식67행의 실제COPY/MV/인증HTTP·두브라우저를 검증했고 정확b1f9 두리뷰무차단·CI5SUCCESS였다. runtime은d46과같으며 운영650은재현/원인미확정이라열어둔다. 읽기전용대조가이드는Geo docs/runbooks/pinvi-650-read-only-diagnosis.md에 있다.
- #643 최신 본문을 다시 읽고684완료와650운영확인후속을 반영했다.
- 이 묶음 뒤641내보내기를 진행한다. Map1450의 실제prod area적재/확인은Claude담당이다.


## 1차 구현 체크포인트

- 시스템 outbox와 분리한 발생키·대상별 chunk 진행 큐, 기본 off 예약 동의, 소유자 수동 발송/결과 API와0104 migration을 추가했다.
- chunk마다 동의→여행→대상 검사와 row lock을 수행한다. 검증·연결 변경은 generation으로 구분한다. Telegram 수락 후 ACK commit 유실은 중복 가능하며 exactly-once가 아니다.
- 기존 worker의 Retry-After 무시를 실제 PG 실패로 재현한 뒤 양의 retry 간격을 적용했다.
- WSL 실제 migration/HTTP/DB 관련26건과 요약·UTF-16 분할4건 통과, mypy266개 통과. 최초 테스트6건은 누락된 테스트 사용자 fixture 문제였으며 보완 후 전체26건 통과했다.
- 아직 UI·예약 planner·Dagster 연결·명시적 특보 이벤트 owner 계약과 최종 리뷰/검증은 남아 있다. #636/#637/#638 완료 또는 병합 준비로 간주하지 않는다.
