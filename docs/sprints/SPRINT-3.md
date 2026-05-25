# SPRINT-3 — Admin 데이터 디버그 콘솔

- **상태**: proposed
- **선행**: Sprint 2 DoD 완료
- **목표**: 지도 UI를 만들기 전에 Admin 페이지로 모든 데이터 흐름을 검증한다.
  (SPEC V8 #5 결정 — Sprint 3 ≺ Sprint 4)
- **DoD**:
  - Admin 진입 (`/admin`) + RBAC (`roles` 검사) — 일반 사용자는 404 (존재 숨김)
  - `/admin/users` 목록 + 상세 + 디버그 액션 ([force-verify], [resend-verify], [disable])
  - `/admin/trips` 목록 + 상세 (멤버/POI/공유 토큰 가시화)
  - `/admin/features`, `/admin/pois` read-only
  - `/admin/api-calls`, `/admin/emails`, `/admin/audit`
  - `/admin/seed` 8 시나리오 + 운영 환경 404 안전장치
  - `/admin/reset` ("RESET" 키워드 + admin 비밀번호 재입력)
  - `admin_audit_log` content_hash chain — 모든 mutating 액션 기록
  - 사유 입력 다이얼로그 (위험 액션 시 강제, O-6)
  - SPEC V8 #4 M-7 시나리오 4가지 통과
  - Sentry 통합 활성화 (Next.js + FastAPI)

## 산출물

### 백엔드

- `apps/api/alembic/versions/0007_feature_requests.py`
- `apps/api/alembic/versions/0008_category_mappings.py`
- `apps/api/alembic/versions/0009_data_integrity_violations.py`
- `apps/api/app/api/v1/admin/{__init__,users,trips,features,pois,api_calls,emails,audit,seed,reset,feature_requests,category_mappings}.py`
- `apps/api/app/services/admin/{entity_browser,audit_chain,seed_scenarios,reset}.py`
- `apps/api/app/middleware/admin_audit.py` — `admin_audit_log` 자동 기록 + chain
- `apps/api/app/middleware/rbac.py` — `roles` 검사 dependency
- `apps/api/app/core/sentry.py` — `before_send` PII 마스킹 활성

### 프론트엔드

- `apps/web/app/admin/layout.tsx` (사이드바 + RBAC 가드)
- `apps/web/app/admin/page.tsx` (대시보드 카드 8개)
- `apps/web/app/admin/users/{page.tsx, [id]/page.tsx}`
- `apps/web/app/admin/trips/{page.tsx, [id]/page.tsx}`
- `apps/web/app/admin/features/page.tsx`
- `apps/web/app/admin/pois/page.tsx`
- `apps/web/app/admin/api-calls/page.tsx`
- `apps/web/app/admin/emails/page.tsx`
- `apps/web/app/admin/audit/page.tsx`
- `apps/web/app/admin/seed/page.tsx` (`ENABLE_SEED` 환경 가드)
- `apps/web/app/admin/reset/page.tsx`
- `apps/web/components/admin/{DataTable,FilterBar,KeyValueGrid,JsonViewer,ActionButton,ReasonDialog}.tsx`
- `apps/web/lib/searchParser.ts` — `email:gmail.com` / `-status:disabled` 문법
- `apps/web/sentry.client.config.ts`

### 테스트

- `tests/integration/test_admin_users.py` (RBAC 403 + force-verify)
- `tests/integration/test_admin_audit_chain.py` (content_hash chain 검증)
- `tests/integration/test_admin_seed_guard.py` (운영 환경에서 404)
- `tests/integration/test_search_parser.py` (필드 prefix 문법)
- `apps/web/tests/admin-flow.test.mjs` (Playwright)

### ADR

- ADR-NNN: Admin RBAC 모델 확정 (`roles TEXT[]` — `is_admin BOOLEAN` 정정 mirror)
- ADR-NNN: Admin audit chain (prev_hash + content_hash)
- ADR-NNN: 검색 문법 (필드 prefix + faceted 필터)
- ADR-NNN: Seed/Reset 환경 가드 (`ENABLE_SEED` + ENV)

## SPEC V8 매핑

- 04-admin.md 전체 (M-1 ~ M-14)
- 00-infrastructure.md §3.5 (O-6 Admin 접근 통제)
- 01-data.md §2.5 (admin_audit_log chain)

## M-7 시나리오 통과 기준

본 Sprint 종료 직전 사용자(또는 자동 e2e)가 다음 4 시나리오를 실제로 실행:

1. ETL 잘 도는지: `/admin` → `/admin/etl`(임베드 placeholder) → `/admin/api-calls` → `/admin/features?updated_after=24h`
2. 회원가입 잘 되는지: `/signup` → `/admin/users?status=pending_verification` → `/admin/emails` → verify 클릭 → 상태 변화
3. 동반자 초대: A로 trip + B 초대 → `/admin/trips/{id}` → `/admin/emails` → B 가입 후 `joined_at`
4. feature 링크 broken 시뮬레이션: `/admin/features` DELETE → `/admin/pois?feature_link_broken=true` → snapshot 폴백

## 종료 체크리스트

- [ ] DoD 모두 통과
- [ ] M-7 시나리오 4 통과
- [ ] `docs/journal.md` Sprint 3 종료 엔트리
- [ ] `docs/resume.md` "다음 한 작업" → Sprint 4
- [ ] 일반 사용자가 `/admin/*`에 진입하면 404 (존재 자체 숨김)
