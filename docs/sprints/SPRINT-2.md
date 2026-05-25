# SPRINT-2 — 도메인 API + DB

- **상태**: proposed
- **선행**: Sprint 1 DoD 완료
- **목표**: Trip / POI / 4 분리 동의 / Resend 이메일 / 위치 감사 로그 / 소셜
  로그인까지 — UI 없이 API + DB 흐름이 통과해야 한다.
- **DoD**:
  - `app.trips` / `app.trip_days` / `app.trip_pois` (COLLATE "C") + 동반자/공유
    토큰 Alembic 통과.
  - `POST /trips`, `POST /trips/{id}/pois`, `POST /trips/{id}/pois/reorder` 통과
    (httpx ASGI 통합 테스트).
  - 4 분리 동의 (`tos`/`privacy`/`lbs_tos`/`location_collection`) DB 기록.
  - `app.location_access_log` content_hash chain — `/features/in-bounds` 호출
    시 자동 적재.
  - Resend `email_queue` worker + verify/reset 메일 발송 (콘솔 모드 + 실제).
  - Webhook `/webhooks/resend` — Svix 서명 검증 + bounced/complained 처리.
  - Google OAuth 안전 매칭 (G-4) 통과.
  - `app.api_call_log` 미들웨어 — 외부 API 호출 logging.
  - `pytest apps/api/tests/integration -q` 통과.

## 산출물

### 백엔드

- `apps/api/alembic/versions/0002_trips.py`
- `apps/api/alembic/versions/0003_pois_collate_c.py` — `sort_order TEXT COLLATE "C"`
- `apps/api/alembic/versions/0004_consents_audit.py` — `user_consents` +
  `location_access_log` + `admin_audit_log` chain
- `apps/api/alembic/versions/0005_email_queue.py`
- `apps/api/alembic/versions/0006_api_call_log.py`
- `apps/api/app/models/{trip,poi,companion,share_link,consent,location_audit,email,api_call}.py`
- `apps/api/app/schemas/{trip,poi,consent,share_link}.py`
- `apps/api/app/services/{trip,poi,consent,email_service,oauth_google,location_audit_hash}.py`
- `apps/api/app/api/v1/{trips,pois,oauth}.py`
- `apps/api/app/middleware/{location_audit,api_call_logging}.py`
- `apps/api/app/webhooks/resend.py`
- `emails/{verify_email,reset_password,trip_invite,share_link_notice}.tsx`
  (React Email) — 빌드 정적 HTML export

### 테스트

- `tests/integration/test_trips_api.py`
- `tests/integration/test_pois_reorder.py` (LexoRank + COLLATE "C" 검증)
- `tests/integration/test_consent_flow.py` (4 동의)
- `tests/integration/test_location_audit_chain.py` (content_hash chain)
- `tests/integration/test_oauth_google.py` (Google `email_verified` 분기)
- `tests/integration/test_resend_webhook.py` (Svix 서명)

### ADR

- ADR-NNN: 인증 토큰 모델 확정 (cookie session vs JWT 잠정 — Sprint 1 ADR-010)
- ADR-NNN: 소셜 로그인 매칭 정책 (G-4 mirror)
- ADR-NNN: `email_queue` worker 패턴 (PostgreSQL `SKIP LOCKED`)

## SPEC V8 매핑

- 02-backend.md §4 (G장 회원가입/동의)
- 02-backend.md §5.3 (H-3 Trip API)
- 02-backend.md §4.3 (G-6 Resend)
- 02-backend.md §3.2 (F-2 공유 토큰)
- 01-data.md §2.1 (E-2 user_consents)
- 01-data.md §2.4 (O-3 위치 감사)
- 01-data.md §2.6 (M-6 email_queue, api_call_log)

## 미해결

- Resend 도메인 인증 (SPF/DKIM/DMARC) — 실제 도메인 확정 필요
- Google OAuth client id/secret — 도메인 확정 후

## 종료 체크리스트

- [ ] DoD 모두 통과
- [ ] `docs/journal.md` Sprint 2 종료 엔트리
- [ ] `docs/resume.md` "다음 한 작업" → Sprint 3
- [ ] CI 3 워크플로 main green
- [ ] SPEC V8 #2 §G/H 항목 모두 박힘
