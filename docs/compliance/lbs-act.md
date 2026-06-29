# 위치정보법 (위치정보의 보호 및 이용 등에 관한 법률)

Pinvi는 사용자 좌표를 서버로 전송·처리하는 위치기반서비스(LBS)이므로 본 법의
규제를 받음. SPEC V8 O-1 / O-2 / O-3 / O-9 정합.

> 관련 법무 문서(초안, T-269): `docs/legal/lbs-terms.md`(위치기반서비스 이용약관),
> `docs/legal/location-consent.md`(개인위치정보 수집·이용 별도 동의). 동의 UX는
> `/settings/consents` · 가입 시 `profile-complete`에서 `/legal/<slug>`로 전문을 링크한다.
> 위치 이용·제공사실 확인자료(제16조, 6개월+)는 운영 `location_access_log`에 자동 기록된다.

## 1. 사업자 신고 (제9조) — Sprint 6 마감

### 1.1 신고 의무

본 서비스는 다음 행위로 LBS 사업자 신고 의무 대상:

- "주변 관광지" 검색 (좌표 → kor-travel-map OpenAPI 호출)
- "내 위치 날씨" 표시
- viewport 기반 feature 로딩
- 사용자 위치 마커 / 거리 표시

디바이스 내부에서만 처리하고 서버 전송 없는 경우는 면제 — 본 서비스는 해당
없음.

### 1.2 신고 절차

- 신고처: 방송통신위원회 (LBSC 사이트 `www.lbsc.kr`)
- 출시 전 신고 완료. 미신고 영업 시 형사 처벌 + 서비스 차단
- 필요 서류:
  - 사업자 등록증
  - 위치정보 처리방침
  - 기술적·관리적 보호조치 계획서
- 처리 기간: 30일 (소요 기간 예상)

### 1.3 진행 상태 추적

| 단계                          | 상태 | 비고                                            |
| ----------------------------- | ---- | ----------------------------------------------- |
| 사업자 등록 (개인/법인)       | ⬜   | 개인사업자 권장 (빠름)                          |
| 위치정보 처리방침 작성        | ⬜   | 법무 4 문서 중 하나 (`docs/legal/lbs-terms.md`) |
| 기술적·관리적 보호조치 계획서 | ⬜   | `docs/compliance/pipa.md` §관리 조치와 통합     |
| LBSC 신고 제출                | ⬜   |                                                 |
| 신고 수리 확인                | ⬜   |                                                 |

## 2. 별도 동의 (제15조) — Sprint 2 + T-117 구현

회원가입 시 일반 개인정보 동의와 별도로 **위치정보 수집·이용 동의** 필수.
SPEC V8 G-5 + `docs/integrations/social-login.md` §3 + `docs/api/auth.md` §2.

### 2.1 4 분리 동의

```
[ 회원가입 동의 ]
☑ (필수) 이용약관에 동의합니다.                    [전문 보기]
☑ (필수) 개인정보 처리방침에 동의합니다.            [전문 보기]
☑ (필수) 위치기반서비스 이용약관에 동의합니다.       [전문 보기]
☑ (필수) 개인위치정보 수집·이용에 동의합니다.        [전문 보기]
☐ (선택) 마케팅·이벤트 이메일 수신에 동의합니다.
```

성별·생년월·거주지 추천 활용(`demographic_use`)은 회원가입이 아니라 프로필 보강
단계에서 해당 값을 입력할 때만 별도로 받는다.

DB: `app.user_consents.consent_type` enum:

- `tos` (이용약관)
- `privacy` (개인정보 처리방침)
- `lbs_tos` (위치기반서비스 이용약관)
- `location_collection` (개인위치정보 수집·이용)
- `demographic_use` (선택)
- `marketing` (선택)

### 2.2 동의 철회

`POST /users/me/consents/withdraw` — `withdrawn_at = now()` + 부작용:

- `location_collection` 철회 → 위치 기능 비활성 (위치 기록은 6개월 보존)
- `demographic_use` 철회 → `users.gender`, `birth_year_month`, `residence_sigungu_code` NULL

자세히는 `docs/api/users.md` §3.

## 3. 위치 감사 로그 (제16조) — Sprint 2 구현

"위치정보 수집·이용·제공 사실 확인자료" **6개월 이상 보존** 의무.

### 3.1 `app.location_access_log` 모델

```sql
CREATE TABLE app.location_access_log (
  id           BIGSERIAL PRIMARY KEY,
  user_id      UUID NOT NULL REFERENCES app.users(user_id),
  occurred_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  endpoint     TEXT NOT NULL,
  purpose      TEXT NOT NULL,
  lat          NUMERIC(9,6),
  lng          NUMERIC(9,6),
  request_id   UUID NOT NULL,
  ip_hash      CHAR(64) NOT NULL,   -- SHA-256(IP). 원본 IP 저장 X
  prev_hash    CHAR(64) NOT NULL,    -- 직전 row content_hash
  content_hash CHAR(64) NOT NULL     -- 본 row 표현 SHA-256
);

CREATE INDEX ON app.location_access_log USING brin (occurred_at);
CREATE INDEX ON app.location_access_log (user_id, occurred_at DESC);
```

자세히는 `docs/architecture/user-location.md` §4.2.

### 3.2 `purpose` 분류

| 값                   | endpoint                                 |
| -------------------- | ---------------------------------------- |
| `viewport_query`     | `/features/in-bounds`                    |
| `nearby_attractions` | `/features/nearby`                       |
| `weather_at_coord`   | `/features/{id}/weather` (좌표 query 시) |
| `feature_request`    | `/features/requests`                     |
| `region_covering`    | `/regions/covering-point`                |
| `region_radius`      | `/regions/within-radius`                 |

### 3.3 content_hash chain

```python
# apps/api/app/services/location_audit_hash.py
import hashlib
import json

def compute_content_hash(prev_hash: str, row: dict) -> str:
    serialized = json.dumps({
        "prev_hash": prev_hash,
        "user_id": row["user_id"],
        "occurred_at": row["occurred_at"].isoformat(),
        "endpoint": row["endpoint"],
        "purpose": row["purpose"],
        "lat": float(row["lat"]) if row["lat"] else None,
        "lng": float(row["lng"]) if row["lng"] else None,
        "request_id": row["request_id"],
        "ip_hash": row["ip_hash"],
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()
```

미들웨어 (`apps/api/app/middleware/location_audit.py`):

1. 응답 직후 좌표 query/body에서 추출
2. 직전 row의 `content_hash` 조회 (또는 0)
3. 새 row INSERT (`prev_hash` + `content_hash` 계산)

중간 row 삭제·변조 시 chain 검증으로 탐지.

### 3.4 6개월 retention / archive 정책

`pinvi_location_log_archive` Dagster asset은 매일 KST 04:30 `app.location_access_log`의 6개월
초과 archive 후보를 dry-run으로 집계하고, archive tail `content_hash`와 active head `prev_hash`가
이어지는지 확인한다. 미처리 `app.location_audit_outbox` 중 cutoff 이전 row가 있으면 archive 실행
blocker로 보고한다.

실제 archive/delete는 `/admin/retention`에서만 실행한다. 기본 kill-switch
`PINVI_RETENTION_EXECUTE_ENABLED=false`가 꺼져 있으면 execute는 `409`로 차단된다. 실행 시에는
후보 row를 `app.location_access_log_archive`에 먼저 복사하고, 같은 transaction에서
`set_config('app.retention_location_delete_allowed', 'on', true)`를 설정한 경우에만
`app.location_access_log` 삭제 trigger가 허용한다.

직접 `DELETE FROM app.location_access_log ...`를 실행하면 이후 row의 `prev_hash` 검증이 깨질 수
있으므로 금지한다. archive/delete 전에 cutoff 이전 pending outbox와 chain bridge mismatch가 없어야
하며, 모든 실행은 `app.retention_runs`와 `admin_audit_log`에 evidence를 남긴다.

### 3.5 권한

- 일반 사용자 / admin → 접근 X
- **CPO 역할만 SELECT** — `app.users.roles @> ARRAY['cpo']`
- 사용자 본인은 본인 row count만 (좌표는 노출 안 함 — `/profile/consents`)
- audit log chain은 `cpo`도 SELECT only, UPDATE/DELETE X

## 4. 자동 트리거 (PIPA 침해 통지)

다음 이상 패턴 자동 감지 → CPO 알림 (`docs/integrations/telegram.md` admin
target):

- 같은 user_id 짧은 시간 다수 IP → 강제 로그아웃 + 알림
- admin이 단시간 1000+ row export → CPO 알림
- audit log chain 깨짐 → 즉시 CPO 알림 (보안 사건)

## 5. 동의 / 감사 로그 운영 정책

- 처리방침에 보존기간 명시: "위치정보 처리 사실 6개월 (위치정보법 제16조)"
- 동의 철회 후에도 기존 row 보존 (법정 의무) — 단, 새 위치 수집 X
- chain hash는 매월 1회 점검 자동화

## 6. AI agent 작업 체크리스트

본 컴플라이언스 항목 구현 시:

- [ ] `app.user_consents.consent_type` 4 분리 + DB CHECK 제약
- [ ] `app.location_access_log` chain 컬럼 + SHA-256 trigger 또는 미들웨어
- [ ] `apps/api/app/middleware/location_audit.py` 자동 적재
- [ ] CPO RBAC dependency
- [x] retention Dagster job + chain 보존 정책
- [x] `/admin/retention` archive/delete kill-switch + evidence log
- [x] `/admin/audit/location` UI (CPO 권한)
- [ ] chain 깨짐 monitoring (Sentry alert)
- [ ] 처리방침 텍스트 (`docs/legal/lbs-terms.md`)
