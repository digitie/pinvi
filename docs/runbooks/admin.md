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

API startup은 `PINVI_BOOTSTRAP_ADMIN_PASSWORD`가 **비어 있지 않을 때만**
`PINVI_BOOTSTRAP_ADMIN_EMAIL` 계정을 생성/복구한다. 이 값이 비어 있으면 의도적으로
skip한다. 운영에서 기본 비밀번호가 우연히 살아나는 일을 막기 위한 안전장치다.

| 환경변수 | 기본/예시 | 설명 |
|----------|-----------|------|
| `PINVI_BOOTSTRAP_ADMIN_EMAIL` | dev/smoke 예시값 | bootstrap 대상 이메일 |
| `PINVI_BOOTSTRAP_ADMIN_PASSWORD` | 비어 있음 | 설정된 경우에만 Argon2id hash로 저장/복구 |

동작:
- 계정이 없으면 `status='active'`, `roles=['user','admin']`, `email_verified_at=now()`로 생성한다.
- 계정이 있으나 비활성/미인증/admin role 누락/password 불일치면 복구한다.
- password hash가 바뀌면 기존 active session을 폐기한다.
- 비밀번호 원문은 로그나 DB에 저장하지 않는다.

개발/smoke에서는 `PINVI_BOOTSTRAP_ADMIN_PASSWORD`에 명시적으로 설정한 임시값으로만
bootstrap 로그인을 검증한다. 운영 환경에서는 첫 진입 후 별도 admin 계정을 만들거나
기존 실사용 계정에 `admin` role을 부여한 뒤, `PINVI_BOOTSTRAP_ADMIN_PASSWORD`를
비우고 bootstrap 대상 계정을 비활성화한다. 공개 문서에는 이메일/비밀번호 조합을
고정하지 않는다.

N150에서 계정 존재 여부만 확인:

```bash
ssh <n150-ssh-target>
docker exec -i pinvi-api-latest python - <<'PY'
import asyncio
from sqlalchemy import text
from app.db.session import async_session_factory

async def main():
    async with async_session_factory() as db:
        rows = (await db.execute(text("""
            SELECT email, status, roles, email_verified_at IS NOT NULL AS verified,
                   password_hash IS NOT NULL AS has_password, is_active
            FROM app.users
            WHERE roles @> ARRAY['admin']::varchar[] AND deleted_at IS NULL
            ORDER BY created_at DESC NULLS LAST
            LIMIT 10
        """))).mappings().all()
        for row in rows:
            print(dict(row))

asyncio.run(main())
PY
```

## 3. 자주 사용하는 admin 작업

### 3.1 사용자 강제 verify

```bash
# Admin 로그인 (curl)
COOKIE=$(curl -fsS -c - -X POST http://localhost:12801/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"..."}' | grep pinvi_access | awk '{print $7}')

# force-verify
curl -fsS -X POST "http://localhost:12801/admin/users/<user_id>/force-verify" \
  -H "Cookie: pinvi_access=$COOKIE" \
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

→ `cpo` 역할 없음 → `404 Not Found` (존재 자체 숨김 정책).

### 4.3 cpo가 사용자 disable 시도

→ `roles`에 `admin` 없음 → `403`. CPO는 disable 권한 X (조회만).

## 5. Audit log 검증

매주 운영자가 점검:

```sql
-- chain 깨짐 검사
WITH rows AS (
  SELECT log_id, prev_hash, content_hash,
         COALESCE(
           LAG(content_hash) OVER (ORDER BY log_id),
           repeat('0', 64)
         ) AS expected_prev
  FROM app.admin_audit_log
  ORDER BY log_id
)
SELECT log_id FROM rows WHERE prev_hash IS DISTINCT FROM expected_prev;
```

깨진 row 발견 → 즉시 CPO 알림 + Sentry alert (보안 사건 가능성).

`location_access_log`도 동일.

## 6. Seed / Reset (dev/staging only)

운영에서는 라우트 비활성 (`ENABLE_SEED=false`). dev/staging에서만:

### 6.1 시나리오 적용

```bash
curl -fsS -X POST "http://localhost:12801/admin/seed/scenarios/new_user_first_trip" \
  -H "Cookie: pinvi_access=$ADMIN_COOKIE" \
  -d '{}'
```

8 시나리오: `new_user_first_trip`, `companion_concurrent_editing`,
`share_link_expiring_soon`, `unverified_users_aged`, `dedup_candidates`,
`etl_failure_simulation`, `large_trip_with_200_pois`, `audit_log_sample_30d`.

### 6.2 Reset

```bash
curl -fsS -X POST "http://localhost:12801/admin/reset" \
  -H "Cookie: pinvi_access=$ADMIN_COOKIE" \
  -d '{"confirm":"RESET","admin_password":"..."}'
```

- DB 전체 reset (`alembic downgrade base` → `upgrade head`)
- 라이브러리 schema는 별도 (`POST /admin/kor-travel-map/reset`)
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
