# 외부 통합

TripMate가 직접 통합하는 외부 서비스 (이메일/소셜 로그인/AI/알림/지도/검색).
`python-krtour-map`이 소유하는 한국 공공 API는 본 디렉토리 범위 밖.

## 1. 인덱스

| 파일 | 서비스 | Sprint |
|------|--------|--------|
| [resend.md](./resend.md) | Resend (이메일 transactional) | 2 |
| [social-login.md](./social-login.md) | Google / Naver / Kakao OAuth | 2 |
| [gemini.md](./gemini.md) | Gemini Deep Research (사용자 키) | 4+ |
| [telegram.md](./telegram.md) | Telegram Bot (알림) | 4+ |
| [maplibre-vworld.md](./maplibre-vworld.md) | **지도 클라이언트** — `maplibre-vworld-js` (VWorld + MapLibre GL) (ADR-015) | 4 |
| ~~[kakao-map.md](./kakao-map.md)~~ | 폐기 — `maplibre-vworld-js`로 교체 (ADR-015) | — |
| [youtube-intelligence.md](./youtube-intelligence.md) | YouTube + Gemini 비디오 분석 (v2) | (v2) |
| [mcp-tools.md](./mcp-tools.md) | MCP 도구 표준 (read-only / draft-only) | (v2) |
| [sentry.md](./sentry.md) | Sentry (에러 / 성능 / Replay) | 1~5 |
| [loki.md](./loki.md) | Loki + Promtail + Grafana (로그 집계) | 5 |

## 2. 공통 정책

### 2.1 비밀 관리

- 환경변수에 저장. `TRIPMATE_*` prefix
- `.env`는 로컬 권한 `600`, 운영은 systemd `EnvironmentFile` 또는 vault
- DB / 로그 / Sentry 이벤트에 **평문 키 절대 X** — `before_send` PII 마스킹
- 사용자별 키 (Gemini 등)는 `secret_ref` + `masked_fingerprint`만 DB 저장

### 2.2 위탁 처리자 명시

PIPA 처리방침에 다음 위탁자 명시 필수:

- Google (OAuth + Gemini) — 미국
- Resend — 미국 AWS
- Sentry SaaS — 미국
- Naver / Kakao — 국내
- Telegram — 글로벌

자세히는 `docs/compliance/pipa.md`.

### 2.3 Rate limit / Quota

각 통합 문서에 명시. SlowAPI 자체 한도 + 외부 quota 보호.

### 2.4 Webhook 검증

| 발신자 | 검증 |
|--------|------|
| Resend | Svix 서명 (`Resend-Signature` 헤더) |
| OAuth callback | state + nonce + PKCE |
| Telegram (v2) | HMAC + 사용자별 secret |
| Gemini (v2 사용자 키 callback) | idempotency_key |

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
5. (테스트) VCR.py 응답 녹화 → fixture
6. 본 README 인덱스 + `docs/compliance/data-policy.md` 갱신
7. (관련 시) ADR 추가
