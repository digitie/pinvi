# Telegram 일정·예약 알림 운영

## 설정과 범위

PR688은 #636/#638, PR689는 Weather201 병합 계약을 소비하는 #637 특보를 구현한다. 사용자 예약 설정은 기본 off다. 여행 연결과 수동 발송은 소유자만 할 수 있다. 새 일정·예약 큐는 검증된 본인 대상으로 보내며 다른 기본 대상으로 fallback하지 않는다. 기존 시스템 outbox의 동작은 유지한다.

서버에 PINVI_TELEGRAM_BOT_TOKEN_DEFAULT를 주입한다. PINVI_TELEGRAM_API_BASE의 기본값은 https://api.telegram.org이다. 예약에는 API와 Dagster가 공유하는 별도 PINVI_TELEGRAM_PLANNER_KEY와 PINVI_NOTIFICATION_PLANNER_API_URL을 사용한다. 키는 32바이트 이상의 무작위 값으로 별도 주입한다. 미설정 schedule은 no-op이며 사용자 JWT로 내부 planner를 호출할 수 없다. 실제 credential은 저장소·로그·브라우저에 넣지 않는다.

일간 브리프는 KST 전날·당일 일정이고, 주간 요약은 선택한 요일 기준 앞으로 7일 안에 시작하는 여행 목록이다. 시각은 KST이며 같은 회차를 중복 생성하지 않는다. 설정 변경은 기존 대기 알림을 무효화하고 같은 회차를 새로 전송하지 않는다. 날씨는 기존 투영 경계를 사용하며 미확인 상태를 명시한다. 일출은 해당 날짜의 성공·비stale 캐시만 사용한다.

## 전달과 오류

요청은 DB에 기록하고 worker가 대상별 chunk를 처리한다. 각 chunk마다 현재 동의·소유권·계정·대상/연결 generation과 예약 날짜를 검사한다. 날짜가 변경되거나 다음 KST 날짜로 넘어간 예약은 skip한다. 미래 Retry-After 대기라도 만료되면 정리한다. 과대 입력은 사용자별 실패로 기록하고 다른 사용자를 막지 않는다.

Bot API의 양의 retry_after와 backoff를 오류 관측 시각부터 적용한다. HTTP 요청과 response hook에는 전체 시간 상한을 적용하며 일반적인 취소는 전파한다. 확인된 chunk는 다시 보내지 않지만, Telegram 수락 후 DB 확인이 유실되면 해당 chunk가 중복될 수 있다. [Telegram sendMessage](https://core.telegram.org/bots/api#sendmessage), [ResponseParameters](https://core.telegram.org/bots/api#responseparameters).

## 관측과 인계

사용자는 설정·공유 탭의 최근 발송 내역에서 완료·일부 진행·실패/skip 원인과 다음 시도 시각을 확인한다. 운영 SQL 집계는 기존 system outbox와 신규 대상 큐·예약 실패를 합친다. 복원 quiescence는 신규 pending도 합산하며 이전 canonical revision에서는 테이블 존재를 먼저 확인한다.

기존 /metrics 표면에 pinvi_telegram_delivery_steps_total, pinvi_telegram_delivery_step_seconds, pinvi_telegram_planning_failures_total을 추가했다. 차원은 고정된 category/outcome/code이며 사용자 ID·chat ID·본문·credential을 label로 사용하지 않는다.

0104를 적용한 뒤 runtime role bootstrap의 exact-head ACL 복구를 확인한다. 새 알림 테이블 3개는 일반 runtime role의 CRUD 대상이며, app.alembic_version의 UPDATE나 migration-owner 권한을 runtime에 주지 않는다.

검증은 WSL 소유 DB/API/프로덕션 웹 빌드와 소유 Telegram HTTP fixture만 사용했다. 운영 접근·배포·실수신자 전송은 수행하지 않았다. 최종 prod 검증은 사용자 지시에 따라 Claude Code가 담당한다.

## 0105 특보 관측 fence

0104 뒤0105를 적용한다. 기본 off 특보 동의/서버 전환 시각과 telegram_weather_observations 테이블을 추가한다. exact0105 runtime ACL repair도 확장하며 신규 테이블을 포함한6테이블의 SELECT/INSERT/UPDATE/DELETE AND 검사를 수행한다. SELECT-only 반례6개가 모두 거절되는지 확인한다. 봉인된0104는 수정하지 않는다.

특보 신규 생성은 신선하고 완결된 검증 지역 응답에만 허용한다. 확인된 취소·상충 관측은 수집 실패와 별개인 긍정적 증거이므로 이전 대기의 무효화 fence에 반영한다. 수집 실패/빈 결과가 해제나 취소를 만들지는 않는다. 잘못된 주간 대상이 별도 특보 철회를 막지 않도록 오래된 무효 주간 설정은 해제와 함께 정리한다.

운영 최종 적용/실제 수신자 검증은 Claude Code 담당이다. 이 작업은 WSL 소유 HTTP fixture와 실제 로컬 PG/API/웹/Prometheus만 검증한다.
