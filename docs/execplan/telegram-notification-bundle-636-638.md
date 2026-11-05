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


## 2차 구현 체크포인트

- 공유 탭에 전체/일자 발송과 대상별 진행·재시도·정제 오류 내역, 설정에 기본 off 일간·주간·특보 동의를 연결했다. 기존 색상 토큰을 유지한다.
- 일간은 KST 전날/당일, 주간은 앞으로7일 여행 목록이다. 사용자 시각/요일과 발생키로 중복 planner를 제어한다. 날씨는 기존 투영 경계를 별도 세션으로 사용하고, 일출은 해당 날짜의 성공·비stale 캐시만 넣는다.
- Dagster 매분 schedule은 전용 key의 내부 HTTP 적재 경계만 호출한다. 미설정은 no-op이며 사용자 JWT로는 호출할 수 없다. 관리자 정적 정의/실패 sensor/큐 집계를 함께 동기화했다.
- Hubble의a3ffc17 검토에서 P1대상 다중잠금 교착과 P2응답 ACK·전송 전체시간·Retry-After 기준시각을 지적받았다. 기존 잠금 컴포넌트는 수정된 실제 NO KEY UPDATE 경계 테스트에서 실패했고 새 enqueue는 대상 잠금을 잡지 않는다. 실제 전송은 개별 대상 generation을 잠그고 검사한다.
- malformed ACK6건·느린 response hook1건은 이전 client에서 실패 후 수정, 지연429 계산2건도 이전 코드에서 실패 후 수정했다. 일반 취소는 전파한다. HTTP request+hook은 wall-clock timeout으로 제한한다.
- 현재 WSL: client/메시지41건, 관련 HTTP·PG21건(예약/권한/동의/집계 포함), ETL81건, API mypy269개, 웹 typecheck 통과. 웹 lint는 신규 오류 수정 후0error/기존5warning이다. 최종 전체검증과 live UI·최종 두리뷰는 아직이다.
- Weather 리뷰에서도 활성 특보 목록만으로 명시적 해제·검증된 적용 지역을 알 수 없음을 확인했다. #637 owner 이벤트 계약을 먼저 보완한다. 아직 특보 planner를 연결하지 않았으며 완료 처리하지 않는다.


## 3차 구현 체크포인트

- Hume의9914ee5 리뷰 P2 두 건을 보완했다. 삭제·비활성 주간 대상이 있어도 off 저장을 허용하고 오래된 주간 참조를 해제한다. 저장 중 입력 전체를 비활성화한다.
- 두 대상 무효화 회귀는 이전 API에서 실패 후 수정했다. 지연된 저장 응답 회귀도9914의 UI 컴포넌트에서 실패 후 수정했고 새 컴포넌트는 통과했다.
- 추가 실제 PG에서 날씨 보강 지연 중 opt-out 잠금 대기를 재현했다. 외부 보강을 잠금 전 단계로 분리하고 enqueue 시 현재 동의를 다시 읽는다. 일출은 적재 단계의 현재 성공 캐시를 읽는다.
- 새 대상 큐가 복원 quiescence 검사에 빠진 것도 실제 PG 실패로 고정했다. 이전 canonical revision에는 테이블이 없을 수 있어 존재 여부를 확인한 뒤 정확한 pending 수를 합산한다.
- WSL API 전체 단위2009통과·기존9skip, 관련 PG25통과, web394/schema24통과, 전체 workspace typecheck, web lint0error/기존5warning을 확인했다. ETL81통과는9914 체크포인트이며 이 단계 ETL source는 동일하다.
- 아직 최종 두리뷰·live UI·최종CI를 마치지 않았고 초안 상태를 유지한다.
- Weather201(초안)을 선행 개설했다. DataGoKR getPwnCd는 공식 지역별 command를 제공하되 APIHub와 코드표가 다르다. 공개 공식413행 특보구역CSV를 확보했으며 현재 Weather location.region_code와는 namespace가 달라 직접 비교하지 않는다. 공식 영역 근거를 추가 대조 중이다. 운영 접근은 없다.
