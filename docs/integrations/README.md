# 외부 통합

Pinvi가 직접 통합하는 외부 서비스 (이메일/소셜 로그인/AI companion 호출 계약/
알림/지도/검색).
`kor-travel-map`이 소유하는 한국 공공 API는 본 디렉토리 범위 밖.
AI provider(Gemini / Claude / Codex) 직접 구현은 ADR-020에 따라 별도 repo
`kor-travel-concierge`이 소유하고, 본 저장소는 호출 계약만 둔다.

## 1. 인덱스

| 파일 | 서비스 | Sprint |
|------|--------|--------|
| [resend.md](./resend.md) | Resend (이메일 transactional) | 2 |
| [social-login.md](./social-login.md) | Google OAuth (Naver/Kakao는 T-122 future provider) | 2 |
| ~~[gemini.md](./gemini.md)~~ | 보류 — `kor-travel-concierge` 참고용 레거시 Gemini 메모 | deferred |
| [telegram.md](./telegram.md) | Telegram Bot (알림) | 4+ |
| [maplibre-vworld.md](./maplibre-vworld.md) | **지도 클라이언트** — `maplibre-vworld-js` (VWorld + MapLibre GL) (ADR-015) | 4 |
| [kor-travel-map-rest-api.md](./kor-travel-map-rest-api.md) | **kor-travel-map REST API 계약** — feature 데이터 OpenAPI HTTP(포트 12701, ADR-026/027) + Pinvi 연결 작업 | 4 |
| [kor-travel-geo.md](./kor-travel-geo.md) | kor-travel-geo v2 REST geocoding (ADR-025) | 4 |
| [kasi.md](./kasi.md) | KASI 특일 + 위치별 해·달 출몰시각 | 5 |
| ~~[kakao-map.md](./kakao-map.md)~~ | 폐기 — `maplibre-vworld-js`로 교체 (ADR-015) | — |
| [youtube-intelligence.md](./youtube-intelligence.md) | YouTube + AI companion 비디오 분석 후보 | (v2) |
| [mcp-tools.md](./mcp-tools.md) | MCP 도구 표준 (read-only / draft-only) | (v2) |
| [sentry.md](./sentry.md) | Sentry (에러 / 성능 / Replay) | 1~5 |
| [loki.md](./loki.md) | Loki + Promtail + Grafana (로그 집계) | 5 |

## 2. 공통 정책

### 2.1 비밀 관리

- 환경변수에 저장. `PINVI_*` prefix
- `.env`는 로컬 권한 `600`, 운영은 systemd `EnvironmentFile` 또는 vault
- DB / 로그 / Sentry 이벤트에 **평문 키 절대 X** — `before_send` PII 마스킹
- 사용자별 AI provider 키는 `kor-travel-concierge`이 소유한다. 본 저장소가
  호출 계약상 참조해야 할 때만 `secret_ref` 같은 간접 참조를 저장한다.

### 2.2 위탁 처리자 명시

PIPA 처리방침에 현재 필수로 명시할 위탁자:

- Google OAuth — 미국. AI provider(Gemini 등)는 `kor-travel-concierge`의
  처리방침/위탁자 목록에서 관리
- Resend — 미국 AWS
- Sentry SaaS — 미국
- Telegram — 글로벌

Naver/Kakao는 T-122 구현 전까지 현행 위탁 처리자가 아니다. provider 활성화 PR에서
국내 위탁자 항목으로 추가 검토한다.

자세히는 `docs/compliance/pipa.md`.

### 2.3 Rate limit / Quota

각 통합 문서에 명시. SlowAPI 자체 한도 + 외부 quota 보호.

### 2.4 Webhook 검증

| 발신자 | 검증 |
|--------|------|
| Resend | Svix 서명 (`Resend-Signature` 헤더) |
| OAuth callback | state + nonce + PKCE |
| Telegram (v2) | HMAC + 사용자별 secret |
| AI companion callback (future) | idempotency_key + shared secret |

자세히는 `docs/api/common.md` §9.

### 2.5 retry / failure 분류

각 통합 서비스의 실패는 다음으로 분류:

- `network_error` (timeout, connection refused)
- `rate_limited` (provider 한도)
- `auth_failed` (키 만료 / 권한)
- `bad_request` (입력 오류)
- `provider_unavailable` (5xx)
- `unknown_error`

retry 정책 + 사용자 알림 / Admin 알림 / Sentry 보고 매트릭스는 각 문서.

## 3. AI agent 작업 가이드

새 외부 통합 추가 시:

1. 본 디렉토리에 신규 파일 생성 (`<service>.md`)
2. 환경변수 / endpoint / 인증 방식 / Webhook 명시
3. Rate limit / failure 분류 / 위탁자 처리방침
4. `apps/api/app/services/<service>.py` 구현 (wrapper 금지 — 직접 사용)
   - AI provider 통합이면 본 저장소에 provider client를 만들지 말고
     `kor-travel-concierge` repo의 HTTP/MCP 계약을 먼저 정의한다.
5. (테스트) VCR.py 응답 녹화 → fixture
6. 본 README 인덱스 + `docs/compliance/data-policy.md` 갱신
7. (관련 시) ADR 추가
