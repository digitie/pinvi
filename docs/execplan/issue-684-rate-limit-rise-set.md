# #684 — 요청 한도 예외 경계와 일자 rise/set 경합

## 확인한 문제

allowed override의 await self.app가 SQLAlchemyError 처리 안에 있어 handler DB 오류를 quota 저장소503으로 오인한다. fail_open에서는 handler를 다시 실행할 수 있다.

sync_trip_day_rise_sets는 기존 행 조회 뒤 ORM INSERT를 하여 두 여행 조회가 같은 PK를 만들 수 있다. best-effort 예외에서 db.rollback을 호출하면 호출자의 loaded trip/poi도 만료되어 후속 응답 조립이 실패한다. 현재 호출부는 여행 GET과 POI 이동 후 조회이며 사용자 mutation은 먼저 commit한다.

## 구현 범위와 수용

- override 조회·hit 등 한도 저장소 판정만 보호한다. handler와 응답 전송 오류를 저장소 오류로 바꾸지 않으며 어떤 경로도 handler를 재실행하지 않는다.
- 실제 저장소 오류의 fail_open/fail_closed 의미는 유지하고 예외 종류만 안전하게 기록한다. SQL·PII·연결 자격을 로그에 남기지 않는다.
- 동일 trip/day 캐시 생성은 PostgreSQL의 원자 upsert로 경합을 처리한다. 좌표·날짜가 같으면 ETL success·출몰시각을 보존하고 입력 변경만 refetch/stale로 전환한다.
- 유지 작업의 실패가 호출자 transaction과 loaded trip/poi를 만료시키거나 별도 사용자 쓰기를 commit/rollback하지 않도록 경계를 정한다. 기존 committed 입력 전제와 호출부를 함께 확인한다.
- 명시적 Event로 두 실제 GET의 누락 행 조회/쓰기 순서를 맞춰 둘 다200·PK중복 없음·일자1행을 확인한다. 캐시 실패 음성 대조에서도 응답 조립과 caller 상태가 보존돼야 한다.

## 검증 순서

초안 PR을 먼저 만들고 자주 push한다. 기존 코드의 실패 우선 회귀: allowed override + handler SQLAlchemyError에서 status500·호출1회, fail_open 경로도 재실행 없음; 저장소 실패는 기존 fail_open/closed 정책 보존. 실제 PostgreSQL 동시 GET·변경 없는 success 보존·좌표/날짜 변경·best-effort 실패의 세션 상태를 검증한다.

WSL 단위/통합과 실제 앱·DB·브라우저 UI를 확인하고 두 독립 전문 적대 리뷰를 다각 수행한다. 정확 최종 HEAD 전체CI를 확인한 뒤 일반 squash merge한다. 운영 접근/배포/시험은 수행하지 않으며 최종 prod는 Claude Code 담당이다.

## 직전 완료

#668은 owner Map1451(27033b1) → 실제 merge sync·Git tree/vendor bytes 대조 → Pinvi683(a1b2f53) 순서로 병합했다. Map 최종0afad CI9 SUCCESS·PostGIS1651pass14skip, Pinvi 최종537 CI15 SUCCESS, 각 두 독립 리뷰 무차단을 확인했다. WSL API1976/관련50·실제UI10·웹393 등 범위는 source proof에 있다.

#643을 최신 본문으로 읽어668 완료와 새684·Map1450을 반영했다. #650은 재오픈으로 유지하며 원래40 주소 실패를 치환하지 않고 공식 원천·코드/배포를 대조한다. Telegram636/637/638 묶음과641도 남아 있다. Map1450 실제 prod area 적재·확인은 Claude Code 담당이다. #671/#672 및 다른 Code의 보존 stash는 건드리지 않는다.

## 구현·실패 우선 증거

- 초안 #687(b7a74fa) → 한도 경계 f876fa9 → 독립 유지/upsert 11dd93c → Trip 선행 잠금 652770b 순으로 각각 remote push했다.
- 원래 코드에서 allowed/handler 예외 회귀 6개 실패: fail-closed503 치환·fail-open 중복 호출·응답 시작 후 추가 전송. caller 만료·미flush/flush 쓰기 자동 commit 회귀3개도 실패했다.
- 두 독립 리뷰어가 오래된 snapshot 후발 저장을 P2로 발견했다. 11dd93c에서 Event로 A 입력 읽기/대기 → 실제 POI 이동+B 유지 완료 → A 재개를 고정해 day1 기준이 복구되는 실패1개를 재현했다.
- 수정은 Trip→POI/day 잠금 순서를 공유한다. 유지 세션이 활성 Trip부터 FOR UPDATE하고 입력 조회~조건부 upsert commit까지 보호한다. POI 삭제도 같은 Trip→POI 규약을 쓴다. 날짜·일자·추가/이동/정렬은 기존 Trip 선행 규약을 유지한다.
- 두 호출부는 알려진 읽기 경계에서 release_read_connection 뒤 transaction이 남지 않은 경우만 독립 유지 세션을 연다. 이 helper가 Core DML까지 감지하는 범용 transaction 판정자는 아니므로 다른 쓰기 경로로 확대하지 않는다.
- 기존 API/DTO·색상·컴포넌트는 바꾸지 않으며 OpenAPI 재생성이 필요한 계약 변경은 없다.
- PostgreSQL 집중13개는 두 GET 200·일자별1행, 실제 SQL 실패 GET/커밋된 이동200, pool_size1/max_overflow0, caller 미커밋 유지·skip, ETL success/timestamps/payload 보존·NULL 전환, 오래된 GET/이동 fence를 확인했다.
- SQL/parameter/PII 대신 예외 종류만 기록한다. UI는 WSL owned PostGIS·실제 API/한도 DB/Chromium으로 확인하며 외부 Map/weather 원천·지도 타일·운영 환경은 검증 범위에 넣지 않는다.

최종 리뷰·CI·병합은 최종 증거를 확인한 뒤 기록한다.

- 후속 두 리뷰의 P1은 삭제가 관측한 여행을 잠근 뒤 관리자 이동된 POI를 따라가는 권한 경합이었다. 실제 관리자 HTTP 이동 뒤 지연 DELETE/PATCH 재개를652770b에서2실패로 재현했다. ef69f74는 원래 여행·POI ID를 await 전에 고정하고 동일 소속·활성 조건의 잠금 재조회로 두 경로를404 차단한다.
- 최종 제품 ef69f74: API1988pass9skip·관련Postgres/API88(집중15 포함)·mypy261·Ruff/format493, 실제 사용자UI5·GET7회200·pageerror0. 웹 타입/lint는 같은 web/packages source의652770b 증거(0error/기존5warning), 최종UI에서는 같은 웹을 새로 production build했다.
- 두 독립 전문 제품 리뷰는 정확 ef69f74에서 잔여P0/P1/P2가 없다. 증거는 docs/reviews/pinvi-684-rate-limit-rise-set-wsl-live.json이며 최종 문서 후보·CI를 별도로 확인한다.
