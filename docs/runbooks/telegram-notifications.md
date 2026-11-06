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

## 0106 planner 상한·공정 drain·본문 보존 (2026-11-06 소유자 결정)

0105 뒤 0106을 적용한다. 세 nullable 열(`telegram_notification_preferences.last_planned_at`, `telegram_notification_deliveries.claim_token`, `telegram_notifications.body_purged_at`)과 부분 index 하나만 추가하므로 이전 코드와 함께 동작한다(forward-safe). 신규 테이블이 없어 runtime ACL 대상은 그대로다.

- **planner 단일 실행·시간 예산.** `/internal/telegram/plan`은 DB session advisory lock으로 한 번에 하나만 돈다. 이전 실행이 남아 있으면(예: Dagster 호출 120초 timeout 뒤에도 API 요청이 계속 도는 경우) 새 tick은 `skipped: 1`로 바로 끝난다. 한 tick은 `PINVI_TELEGRAM_PLANNER_BUDGET_SECONDS`(기본 60초) 안에서만 사용자를 처리하고 남은 사용자는 `deferred`로 다음 tick에 넘긴다. 다음 tick은 가장 오래 기다린 사용자(`last_planned_at`)부터 시작하므로 뒤 사용자가 굶지 않는다. 중복 방지는 기존 발생키(unique)가 그대로 맡는다. Dagster asset 메타데이터에 `processed`·`deferred`·`skipped`·`purged`가 실린다.
- **사용자 공정 drain.** worker는 한 바퀴마다 사용자별 순번(window function, 사용자당 최대 5 chunk)으로 처리 순서를 정한다. 한 사용자의 backlog가 먼저 쌓여 있어도 다른 사용자의 기한 있는 특보·브리프는 첫 바퀴 안에 나간다.
- **전송 중 잠금 해제.** 정책 확인(동의·소유권·계정·대상 generation·날짜)은 claim transaction에서 Trip→User→대상 잠금으로 하고, 보낼 chunk와 대상을 고정한 뒤 60초 lease(`claim_token`)를 commit해 잠금을 모두 푼 다음 Telegram을 호출한다. 결과는 새 transaction에서 같은 token일 때만 기록한다. 느린 Telegram 응답이 여행 편집·동의 철회를 막지 않는다. 대신 정책 확인 commit 뒤 전송 직전 사이의 철회는 이미 결정된 그 한 chunk를 막지 못한다(전송 중 철회와 같은 창). 프로세스가 결과 기록 전에 죽으면 lease가 끝난 뒤 다시 보내며, 이는 기존 "수락 뒤 ACK 유실" 중복 가능성과 같다. worker 취소는 lease를 즉시 돌려준다.
- **본문 보존 기한.** 대기 중 전송이 없는 알림은 생성 뒤 `PINVI_TELEGRAM_NOTIFICATION_RETENTION_DAYS`(기본 30일)가 지나면 planner tick마다 최대 500건씩 본문(chunks)을 같은 개수의 빈 문자열로 바꾸고, 예약 스냅샷과 전송 오류 상세 문구를 지운다. 발생키·분류·상태·시각·오류 코드·`body_purged_at`은 중복 방지와 감사용으로 남는다. 발송 내역 화면은 상태·진행률을 그대로 보여 준다.
- **특보 시각 정밀도.** 특보 조회 범위(`since`)는 초 단위 UTC로 보내고, 응답 범위·발표 시각·동의 시각·관측 시각은 초 단위 UTC instant로 맞춘 뒤 비교한다. Weather가 범위를 초 단위나 KST offset으로 돌려줘도 응답 범위 검사가 실패하지 않고, 동의와 같은 초의 발표가 microsecond 차이로 빠지지 않는다.
- **저장 시각 뒤에 켠 일간 브리프(유지).** 저장한 발송 시각이 이미 지난 뒤 일간 브리프를 켜면 그날 회차를 바로 보낸다(늦게 켜도 당일 브리프를 받는다). 소유자 결정으로 유지하며 `test_daily_brief_enabled_after_send_time_is_planned_today`가 고정한다. live e2e는 이 때문에 발송 시각을 23:59로 저장한다(NTF-019).
