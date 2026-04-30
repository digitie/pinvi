# Gemini Deep Research Integration

## 목적

Gemini Deep Research는 저장된 장소에 대한 보강 정보 생성을 사용자가 수동으로 실행하는 기능이다. 결과는 provider 원천 데이터와 분리해 “Gemini 생성 요약/조사 결과”로 표시한다.

## 핵심 불변 조건

- 자동 주기 실행은 기본 비활성화한다.
- 사용자가 버튼으로 수동 실행하거나 명시적으로 재실행한다.
- 사용자 개인 Gemini API 키 입력 구조로 설계한다.
- API 키 원문은 일반 DB 테이블과 로그에 저장하지 않는다.
- 생성 결과와 확인된 원천 데이터는 UI와 DB에서 분리한다.
- 환각 가능성을 전제로 출처/근거 링크를 남긴다.

## 사용자 키 모델

권장 필드:

- `id`: 내부 key reference id
- `user_id`: 소유 사용자 id
- `provider`: `gemini`
- `secret_ref`: secret store 또는 암호화 저장 계층의 참조값
- `masked_fingerprint`: 사용자가 구분할 수 있는 마스킹된 지문
- `is_enabled`: 활성화 여부
- `last_verified_at`: 최근 검증 시각
- `last_verification_status`: 최근 검증 상태
- `created_at`, `updated_at`, `deleted_at`

금지:

- API 키 원문 DB 평문 저장
- API 키 원문 로그 출력
- API 키 원문 클라이언트 재전송
- 테스트 fixture에 실제 키 사용

## 키 플로우

1. 사용자가 Gemini API 키를 입력한다.
2. 서버가 키 형식과 간단한 호출 가능 여부를 검증한다.
3. 원문 키는 secret store 또는 암호화된 비밀 저장 계층에 저장한다.
4. 도메인 DB에는 `secret_ref`, `masked_fingerprint`, 검증 상태만 저장한다.
5. 사용자는 키를 교체하거나 삭제할 수 있다.
6. 삭제된 키로는 새 실행을 시작할 수 없다.

## 실행 기록 모델

권장 필드:

- `id`: 실행 id
- `user_id`
- `place_id`
- `idempotency_key`
- `gemini_key_ref`
- `model`
- `prompt_version`
- `prompt`
- `input_context_summary`
- `status`: `queued` / `running` / `succeeded` / `failed` / `canceled`
- `result_summary`
- `result_sections`
- `sources`
- `error_code`
- `error_message`
- `started_at`
- `finished_at`
- `created_at`

같은 입력에 대한 최근 결과가 있으면 재사용 옵션을 제공한다.

## 결과 섹션

긴 응답은 다음 섹션 구조로 저장한다.

- 요약
- 방문 포인트
- 주의사항
- 교통/주차
- 가족/아이 동반 적합성
- 비 오는 날 대안
- 출처/근거

## UI 표시

- “생성 결과”와 “확인된 원천 데이터”를 시각적으로 구분한다.
- 출처 링크 또는 참조를 사용자가 열어볼 수 있게 한다.
- 실패 시 재시도 가능 여부와 키 검증 필요 여부를 구분해 안내한다.

## YouTube 영상 분석 모드

YouTube 국내여행 정보 수집은 `docs/architecture/youtube-travel-intelligence.md`를 따른다.

Gemini API는 공개 YouTube URL을 `file_data.file_uri`로 직접 전달하는 방식을 제공한다. TripMate에서는 전체 영상을 다운로드해 Gemini에 업로드하는 방식을 기본값으로 두지 않고, YouTube URL 직접 전달을 우선한다.

운영 기준:

- 이 기능은 Gemini 문서상 preview이므로 안정적인 영구 인터페이스로 가정하지 않는다.
- private 또는 unlisted 영상은 처리할 수 없으므로 실패 상태를 저장하고 skip한다.
- 자동 모니터링 배치는 시스템/관리자 Gemini key 사용을 추천한다.
- 사용자가 직접 실행하는 수동 분석은 사용자 개인 Gemini key 정책과 연결할 수 있다.
- Gemini가 추출한 장소명, 주소, 좌표는 검증 전에는 `pending` 후보로만 저장한다.
- 자막 전문, 설명란 전문, 전체 영상 파일은 장기 저장하지 않는다.
- 대표 프레임 이미지는 저작권/약관 검토 전까지 공개 UI 기본 이미지로 쓰지 않는다.

## 테스트

필수 테스트:

- 사용자 키 등록/검증/교체/삭제
- 키 원문이 일반 DB와 로그에 남지 않는지 확인
- idempotency key 재사용
- 최근 결과 재사용
- 실패 상태 저장
- result section schema validation
- provider 원천 데이터와 Gemini 생성 결과 분리
