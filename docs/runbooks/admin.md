# Admin 콘솔 운영 Runbook

Admin 콘솔 운영 — 권한 부여 / seed / 위험 액션 / audit log 검증. SPEC V8 #4 + 본
저장소 [`docs/api/admin.md`](../api/admin.md).

## 1. 권한 모델

| 역할 | 권한 |
|------|------|
| `user` | 일반 사용자 |
| `admin` | 운영 admin (대부분 mutate 가능) |
| `operator` | 데이터 운영 (notice plan / category mapping) |
| `cpo` | 개인정보 보호 책임자 (location_access_log SELECT 등) |

부여:

```sql
-- DB에서 직접 (pgAdmin 또는 psql)
UPDATE app.users SET roles = array_append(roles, 'admin') WHERE email = 'admin@example.com';
UPDATE app.users SET roles = array_append(roles, 'cpo') WHERE email = 'cpo@example.com';
```

UI에서는 부여하지 않음 (Telegram 정책과 동일 — `docs/integrations/telegram.md` §1).

## 2. 초기 admin 계정

Alembic seed: `apps/api/alembic/versions/.../seed_default_admin.py`

```python
def upgrade():
    op.execute("""
        INSERT INTO app.users (user_id, email, password_hash, status, roles, email_verified_at)
        VALUES (
            gen_random_uuid(),
            'admin@ad.min',
            -- Argon2id hash of 'admin'
            '$argon2id$v=19$m=65536,t=3,p=4$...',
            'active',
            ARRAY['user', 'admin'],
            now()
        )
        ON CONFLICT (email) DO NOTHING
    """)
```

- 운영 환경: 첫 진입 후 비밀번호 변경 + 신규 admin 생성 → `admin@ad.min` 비활성
- `BOOTSTRAP_ADMIN_EMAIL` 환경변수로 다른 첫 admin 지정 가능

## 3. 자주 사용하는 admin 작업

### 3.1 사용자 강제 verify

```bash
# Admin 로그인 (curl)
COOKIE=$(curl -fsS -c - -X POST http://localhost:9021/admin/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"..."}' | grep tripmate_access | awk '{print $7}')

# force-verify
curl -fsS -X POST "http://localhost:9021/admin/users/<user_id>/force-verify" \
  -H "Cookie: tripmate_access=$COOKIE" \
  -H "X-Access-Reason: 고객 문의 TICKET-1234" \
  -d '{}'
```

UI: `/admin/users` → 사용자 행 클릭 → [강제 인증] 버튼 → 사유 다이얼로그.

### 3.2 사용자 disable

```http
POST /admin/users/<user_id>/disable
X-Access-Reason: "약관 위반 확인 (TICKET-...)"

{}
```

- `users.status = 'disabled'`
- 모든 `user_sessions.revoked_at = now()`
- `admin_audit_log` 자동

### 3.3 비밀번호 재설정 메일 재발송

```http
POST /admin/users/<user_id>/resend-verify
```

(verify와 reset은 별 endpoint — `/admin/users/{id}/resend-reset`도 추가 권장)

### 3.4 Dagster ETL 수동 trigger

`/admin/etl` → asset 카드 [지금 실행] 또는:

```bash
docker compose exec dagster dagster asset materialize \
  --select feature_event_festivals \
  -p partition_2026-06-01
```

### 3.5 Notice plan publish

UI: `/admin/notice-plans/{plan_id}` → [Publish] 버튼.

API:

```http
PATCH /admin/notice-plans/<plan_id>
If-Match: 3
X-Access-Reason: "월간 추천 콘텐츠 공개"

{"is_published": true}
```

## 4. RBAC 시나리오

### 4.1 일반 사용자가 `/admin` 진입

→ Next.js middleware가 cookie 검증 → 백엔드가 `404 Not Found` (존재 자체 숨김).

### 4.2 admin이 `/admin/audit/location` 진입

→ `cpo` 역할 없음 → `403 PERMISSION_DENIED` (CPO 권한 필요 — admin 화면에서 명시 안내).

### 4.3 cpo가 사용자 disable 시도

→ `roles`에 `admin` 없음 → `403`. CPO는 disable 권한 X (조회만).

## 5. Audit log 검증

매주 운영자가 점검:

```sql
-- chain 깨짐 검사
WITH rows AS (
  SELECT id, prev_hash, content_hash,
         LAG(content_hash) OVER (ORDER BY id) AS expected_prev
  FROM app.admin_audit_log
  ORDER BY id
)
SELECT id FROM rows WHERE prev_hash IS DISTINCT FROM expected_prev;
```

깨진 row 발견 → 즉시 CPO 알림 + Sentry alert (보안 사건 가능성).

`location_access_log`도 동일.

## 6. Seed / Reset (dev/staging only)

운영에서는 라우트 비활성 (`ENABLE_SEED=false`). dev/staging에서만:

### 6.1 시나리오 적용

```bash
curl -fsS -X POST "http://localhost:9021/admin/seed/scenarios/new_user_first_trip" \
  -H "Cookie: tripmate_access=$ADMIN_COOKIE" \
  -d '{}'
```

8 시나리오: `new_user_first_trip`, `companion_concurrent_editing`,
`share_link_expiring_soon`, `unverified_users_aged`, `dedup_candidates`,
`etl_failure_simulation`, `large_trip_with_200_pois`, `audit_log_sample_30d`.

### 6.2 Reset

```bash
curl -fsS -X POST "http://localhost:9021/admin/reset" \
  -H "Cookie: tripmate_access=$ADMIN_COOKIE" \
  -d '{"confirm":"RESET","admin_password":"..."}'
```

- DB 전체 reset (`alembic downgrade base` → `upgrade head`)
- 라이브러리 schema는 별도 (`POST /admin/krtour-map/reset`)
- 자동으로 `new_user_first_trip` 적용

## 7. Daily check (운영자 일과)

매일 KST 09:00에:

1. `/admin` 대시보드 카드 확인:
   - users_24h, pending_verification
   - trips_total, etl_last_24h
   - email_queue_pending
2. `/admin/audit` 어제 변경 review
3. `/admin/api-calls` provider 실패율 (특히 외부 API)
4. `/admin/integrity` 위반 신규 발생 여부
5. Sentry 알림 inbox 확인

## 8. 위험 액션 (사유 입력 필수)

- 사용자 disable / 강제 verify / PII 원본 reveal
- Notice plan publish / unpublish
- Category mapping 변경
- Reset / Seed
- RustFS object 강제 삭제

사유는 `X-Access-Reason` 헤더 또는 body. 미입력 → `422 VALIDATION_ERROR`.

## 9. AI agent 작업 체크리스트

새 Admin 페이지 추가:

- [ ] `apps/api/app/api/v1/admin/<resource>.py` 라우터
- [ ] `apps/api/app/services/admin/<resource>.py` 비즈니스 로직
- [ ] `apps/api/app/middleware/admin_audit.py`가 자동으로 audit log 적재하는지 확인
- [ ] 위험 액션은 `X-Access-Reason` 검사
- [ ] `apps/web/app/admin/<resource>/page.tsx` (shadcn/ui DataTable + FilterBar)
- [ ] RBAC dependency 적용 (`require_role("admin")` 등)
- [ ] 통합 테스트 — 일반 사용자 403, admin 200, RBAC 거부 시 404
- [ ] 본 runbook + `docs/api/admin.md` 갱신

## 10. 관련 문서

- `docs/api/admin.md` — 전체 endpoint
- `docs/spec/v8/04-admin.md` — SPEC V8 13 페이지
- `docs/integrations/sentry.md` — audit chain alert
- `docs/compliance/pipa.md` — PIPA 침해 통지 트리거
