# 위치정보법 (위치정보의 보호 및 이용 등에 관한 법률)

TripMate는 사용자 좌표를 서버로 전송·처리하는 위치기반서비스(LBS)이므로 본 법의
규제를 받음. SPEC V8 O-1 / O-2 / O-3 / O-9 정합.

## 1. 사업자 신고 (제9조) — Sprint 6 마감

### 1.1 신고 의무

본 서비스는 다음 행위로 LBS 사업자 신고 의무 대상:

- "주변 관광지" 검색 (좌표 → 라이브러리 호출)
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

| 단계 | 상태 | 비고 |
|------|------|------|
| 사업자 등록 (개인/법인) | ⬜ | 개인사업자 권장 (빠름) |
| 위치정보 처리방침 작성 | ⬜ | 법무 4 문서 중 하나 (`docs/legal/lbs-terms.md`) |
| 기술적·관리적 보호조치 계획서 | ⬜ | `docs/compliance/pipa.md` §관리 조치와 통합 |
| LBSC 신고 제출 | ⬜ | |
| 신고 수리 확인 | ⬜ | |

## 2. 별도 동의 (제15조) — Sprint 2 구현

회원가입 시 일반 개인정보 동의와 별도로 **위치정보 수집·이용 동의** 필수.
SPEC V8 G-5 + `docs/integrations/social-login.md` §3 + `docs/api/auth.md` §4.

### 2.1 4 분리 동의

```
[ 회원가입 동의 ]
☑ (필수) 이용약관에 동의합니다.                    [전문 보기]
☑ (필수) 개인정보 처리방침에 동의합니다.            [전문 보기]
☑ (필수) 위치기반서비스 이용약관에 동의합니다.       [전문 보기]
☑ (필수) 개인위치정보 수집·이용에 동의합니다.        [전문 보기]
☐ (선택) 성별·생년월 통계·추천 활용에 동의합니다.
☐ (선택) 거주지 추천 활용에 동의합니다.
☐ (선택) 마케팅·이벤트 이메일 수신에 동의합니다.
```

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

| 값 | endpoint |
|----|----------|
| `viewport_query` | `/features/in-bounds` |
| `nearby_attractions` | `/features/nearby` |
| `weather_at_coord` | `/features/{id}/weather` (좌표 query 시) |
| `feature_request` | `/features/requests` |
| `region_covering` | `/regions/covering-point` |
| `region_radius` | `/regions/within-radius` |

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

### 3.4 6개월 retention

Dagster job 일 1회:

```sql
DELETE FROM app.location_access_log WHERE occurred_at < now() - INTERVAL '6 months';
```

단, chain 끊김 → 이후 row의 `prev_hash` 검증 실패. retention 정리 시 chain
재계산 또는 batch 단위 삭제 시 그 batch의 마지막 hash 보존 trigger 필요.

대안: `DELETE`가 아니라 archive 테이블 (`location_access_log_archive`)로 이전.
chain 검증은 그 archive 끝과 active 시작을 join.

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
- [ ] retention Dagster job + chain 보존 정책
- [ ] `/admin/audit/location` UI (CPO 권한)
- [ ] chain 깨짐 monitoring (Sentry alert)
- [ ] 처리방침 텍스트 (`docs/legal/lbs-terms.md`)
