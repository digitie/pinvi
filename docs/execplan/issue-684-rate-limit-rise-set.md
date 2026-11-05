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
