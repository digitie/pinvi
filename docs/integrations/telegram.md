# Telegram Integration

## 목적

TripMate는 여행별 Telegram 알림 대상을 최대 3개까지 연결한다. 알림은 저장된 여행, 지역, 날씨/유가 데이터를 기반으로 생성하며, 같은 시군구는 규칙에 따라 묶는다.

## 핵심 불변 조건

- Telegram 대상은 사용자 소유 리소스다.
- 여행은 Telegram 대상 자체를 복사하지 않고 사용자 소유 대상을 참조한다.
- 여행별 Telegram 알림 대상은 최대 3개다.
- bot token 원문은 DB에 평문 저장하지 않는다.
- 일반 채팅은 thread/topic id를 비워둔다.
- 발송 실패 원인은 구분해 저장한다.

## 대상 모델

권장 필드:

- `id`: 내부 Telegram target id
- `user_id`: 소유 사용자 id
- `telegram_bot_token_ref`: 실제 token이 아닌 환경변수 이름, secret key, 내부 참조값
- `telegram_chat_id`: 필수. 개인 대화, 그룹, 채널 식별자
- `telegram_chat_type`: `private` / `group` / `supergroup` / `channel`
- `telegram_message_thread_id`: 선택. 포럼형 supergroup topic 또는 thread 대상 발송 시 사용
- `telegram_direct_messages_topic_id`: 선택. Telegram Bot API에서 direct messages topic이 필요한 케이스 대응
- `telegram_label`: 사용자가 구분하기 쉬운 별칭
- `is_default`: 사용자 기본 알림 대상 여부
- `is_enabled`: 활성화 여부
- `last_verified_at`: 최근 검증 시각
- `last_send_status`: 최근 발송 성공/실패 상태
- `created_at`, `updated_at`

여행 연결 모델:

- `trip_id`
- `telegram_target_id`
- `created_at`

`trip_id + telegram_target_id`는 중복 연결을 허용하지 않는다.

## 검증 플로우

최초 등록 또는 대상 수정 시 다음 중 하나로 검증한다.

- `getChat`: chat id, chat type, bot 접근 가능 여부 확인
- `sendMessage`: 실제 발송 권한과 topic/thread id 유효성 확인

검증 결과는 `last_verified_at`과 `last_send_status`에 저장한다.

## 실패 사유

최소 구분:

- `missing_chat_id`: chat id 없음
- `bot_forbidden`: bot 권한 없음 또는 차단
- `invalid_chat`: chat id 잘못됨
- `invalid_topic`: topic/thread id 잘못됨
- `rate_limited`: Telegram rate limit
- `network_error`: 일시적 네트워크 오류
- `unknown_error`: 분류되지 않은 오류

사용자 UI에는 기술 오류 문자열을 그대로 노출하지 말고, 조치 가능한 메시지로 변환한다.

## 메시지 생성

- 일주일 전 알림: 여행 전체 요약, 지역별 날씨/유가 요약
- 하루 전 알림: 상세 시간대 예보, 이동/장소 준비 정보
- 같은 시군구 데이터는 묶어서 중복 메시지를 줄인다.
- 메시지 생성은 외부 API 실시간 호출이 아니라 serving 테이블 조회를 우선한다.
- 관리자 권한 사용자의 Telegram 여행 알림에는 여행 정보와 시스템 에러/로그 요약을 함께 포함할 수 있다.
- 일반 권한 사용자 Telegram에는 여행 정보만 발송하고 시스템 에러/로그 정보는 포함하지 않는다.
- 날씨, 유가, 주변 정보처럼 여행 정보에 포함되는 데이터 생성이 실패하면 해당 데이터 섹션을 생략하지 않고 사용자용 에러 메시지로 대체한다.
- 사용자용 에러 메시지에는 dataset key, stack trace, raw response body, API key, token, 내부 로그 경로를 포함하지 않는다.
- 관리자용 메시지에는 dataset key, Dagster job/run id, 실패 단계, retry 횟수, 마지막 오류 분류, stale serving 사용 여부, 내부 로그 참조 id 또는 경로를 포함할 수 있다.

## 운영/ETL 알림

- 데이터 수집 retry를 모두 소진한 실패는 관리자 페이지 알림과 함께 관리자 권한 사용자 Telegram에도 발송한다.
- 운영 알림은 여행별 Telegram 대상 3개 제한과 별개이며, 관리자 권한 사용자 소유의 활성화·검증된 Telegram target을 사용한다.
- 일반 권한 사용자 Telegram에는 운영/ETL 시스템 에러와 로그 정보를 발송하지 않는다.
- 관리자/권리자 권한은 앱 UI가 아니라 pgAdmin 등 DB 관리 도구로 사용자 구분 필드에 부여한다.
- 관리자 권한 사용자에게 활성 Telegram target이 없으면 Telegram 발송은 건너뛰고 관리자 페이지 알림과 실패 로그만 남긴다.
- 운영 알림 메시지에는 dataset key, Dagster job/run id, 실패 단계, retry 횟수, 마지막 오류 분류, 기존 serving 사용 여부, 내부 로그 참조 id 또는 경로를 포함할 수 있다.
- token 원문, API key, 원본 응답 body 전체는 운영 알림에 포함하지 않는다.

## 보안

- token 원문은 로그, 테스트 fixture, 일반 DB 컬럼에 저장하지 않는다.
- `telegram_bot_token_ref`만 도메인 모델에 저장한다.
- 초기 운영에서는 `telegram_bot_token_ref`가 환경변수 이름을 가리킨다.
- secret store를 도입하면 이 문서와 runbook을 함께 갱신한다.

## 테스트

필수 테스트:

- 대상 등록 정상 경로
- `chat_id` 누락 실패
- 권한 없는 bot 실패
- topic/thread id 오류 실패
- 여행별 대상 3개 제한
- 중복 연결 방지
- 메시지 생성 중복 제거
- ETL retry 소진 시 관리자 권한 사용자 Telegram target으로 운영 알림 발송
- 관리자 Telegram target이 없을 때 관리자 페이지 알림만 남기는 fallback
- 일반 권한 사용자 Telegram 여행 알림에 시스템 에러/로그가 포함되지 않는지 확인
- 여행 정보 데이터 실패 시 사용자용 에러 메시지로 대체되는지 확인
- 관리자 권한 사용자 Telegram 여행 알림에 여행 정보와 시스템 에러/로그 요약이 함께 포함되는지 확인
- token 원문 로그/응답 미노출
