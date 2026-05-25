# SPEC V8 #0 — 인프라 · 컴플라이언스 (TripMate 적용 노트)

원본: `spec_v8_0_infrastructure.docx` (N장 비기능 + O장 법률).

## 1. 적용 범위

| 항목 | 본 저장소 | `python-krtour-map` | 비고 |
|------|-----------|---------------------|------|
| docker-compose / Odroid 운영 manifest | ✓ | — | `infra/docker-compose.yml`은 TripMate 소유. 라이브러리는 import만 |
| Sentry SaaS Free 통합 | ✓ | ✓ | 양쪽 모두 동일 DSN + environment 태그 |
| Loki+Promtail+Grafana | ✓ | — | `apps/api` / `apps/web` / `apps/etl` 로그 수집 |
| RustFS 객체 저장소 | ✓ | — | TripMate가 운영. 라이브러리는 `file_store` 주입 받음 |
| 백업 (pg_dump + WAL) | ✓ | — | DB는 단일. TripMate alembic + 라이브러리 alembic 모두 백업 대상 |
| 위치정보법 / PIPA 컴플라이언스 | ✓ | — | 호출 측 책임 — 라이브러리는 schema 미설치 |

## 2. 핵심 채택 (TripMate v2)

### 2.1 운영 환경 — Odroid M1S

- ARM64 (Rockchip RK3566 quad-core @ 1.8GHz), 8GB RAM
- Ubuntu 24.04 LTS + Docker 28.x + Docker Compose v2
- NVMe SSD (256GB 권장)
- 평상시 5W, 부하 시 10W — 24/7 가정 운영
- `infra/docker-compose.yml`(개발) / `infra/docker-compose.app.yml`(운영) 분리
  (`docs/architecture.md` §5)

서비스 컨테이너:

- `postgres` (PostGIS 3.5 / 메모리 1GB / `shared_buffers=256MB` — 10명 환경 튜닝)
- `rustfs` (S3 호환 / 메모리 256MB)
- `fastapi` (uvicorn workers=1, 메모리 768MB)
- `nextjs` (메모리 768MB)
- `dagster` (concurrency=1, 메모리 512MB)
- `loki` + `promtail` + `grafana` (옵션, 메모리 합 ~1.1GB)
- `nginx` (reverse proxy + Let's Encrypt)

볼륨: `/mnt/nvme/{pgdata,rustfs,dagster,backups,grafana}`.

### 2.2 ARM64 multi-arch 빌드 정책

- CI: GitHub Actions + docker buildx + QEMU
- `linux/amd64,linux/arm64` 양쪽 manifest push
- 운영(Odroid)은 arm64 manifest 자동 선택
- 단일 arch 빌드 → "exec format error"로 컨테이너 안 뜸 — 사고 사례로 ADR에 명시 후보

### 2.3 WSL 미러 작업 흐름

ADR-004로 박힌 v2의 단일 모델. SPEC V8의 N-7.2 "WSL ext4 직접 작업본 + NTFS
export"와 차이가 있다 — v2는 **NTFS 작업 + WSL 미러 실행**.

| SPEC V8 원본 | v2 채택 (ADR-004) |
|------|------|
| 코드는 ext4 `~/projects/trip-service` | 코드는 NTFS `F:\dev\tripmate` + WSL 미러 `~/tripmate-workspaces/tripmate` |
| 산출물(tar)은 NTFS `/mnt/c/Users/Me/artifacts/` | 산출물은 ext4 build/, 배포 시 scp 또는 GHCR pull |
| Windows 손상 시 산출물 NTFS 보존 | git origin이 단일 진실 공급원, 산출물은 임시 |

SPEC V8 N-7.2의 "코드 ext4 / 산출물 NTFS" 모델은 v1에서 운영 중 NTFS ↔ ext4
양방향 동기 모호함이 발생해 v2에서 단순화했다. 본 정정은 `docs/decisions.md`
ADR-004에 기록되어 있다.

### 2.4 i18n (N-1)

- next-intl + Next.js 15 App Router
- `messages/ko.json` 기본
- ESLint 룰로 코드 내 한글 하드코딩 차단
- 로케일 라우팅 `/ko/...` (v1) → v2에 `/en/...` 확장 자연스러움
- DB의 `name_en` 등 i18n 컬럼은 코드 단계 진입 후 도입

### 2.5 보안 (N-2)

- 비밀번호 해시: **Argon2id** (passlib 또는 argon2-cffi)
- JWT secret 최소 32 bytes
- HTTPS 강제 + HSTS 1년
- CORS 화이트리스트
- CSP: `script-src 'self'` + `connect-src 'self' https://api.vworld.kr` (`maplibre-vworld-js` 사용, ADR-015). inline script 금지 (nonce)
- Rate limit (SlowAPI): 로그인/가입/재설정 IP+이메일 기준 분당 5회
- Admin 작업 audit log: `app.admin_audit_log` (TripMate 소유)

### 2.6 백업 (N-3)

- `pg_dump --format=custom` 일 1회 (PostGIS 포함)
- RustFS: bucket versioning + lifecycle 90일
- WAL archiving: wal-g 또는 pgBackRest 7일
- 외부 위치 전송 필수 (NAS / 다른 가정 머신 / BackBlaze B2)
- 분기 1회 복구 훈련

### 2.7 관측 (N-4)

- 에러: **Sentry** (Next.js + FastAPI + Dagster)
  - SaaS Free 시작 (월 5K events)
  - `before_send` PII 마스킹 — 이메일/좌표/전화 정규식 필터
  - Dagster run failure sensor → Sentry capture_message
- 로그: **Loki + Promtail + Grafana**
  - Sentry는 에러/예외/성능, Loki는 INFO/요청 추적
  - `apps/api` structlog JSON → Promtail 파싱
  - `request_id` / `user_id` / `level` 라벨
- 메트릭: Prometheus + Grafana (v2 후보)
- Uptime: UptimeRobot / Better Stack (v2 후보)

Admin `/admin/debug/logs`는 Loki LogQL을 WebSocket으로 stream
(`docs/spec/v8/04-admin.md` M-12).

### 2.8 테스트 / CI (N-5, N-6)

- Backend: pytest + pytest-asyncio + testcontainers PostGIS (coverage 70% 목표)
- Frontend: Vitest(단위) + Playwright(E2E)
- 외부 API: VCR.py 응답 녹화/재생
- GitHub Actions: PR → 단위+lint+type+build, main 머지 → 이미지 빌드+레지스트리 push

## 3. 위치정보법 / PIPA (O장)

### 3.1 LBS 사업자 신고 (O-1)

본 서비스가 사용자 좌표를 서버에 전송하여 "주변 관광지/내 위치 날씨/viewport
feature 로딩"을 처리하므로 **위치기반서비스사업자 신고 의무 대상**.

- 신고처: 방송통신위원회 (LBSC `www.lbsc.kr`)
- 출시 전 신고 완료. 미신고 영업 시 형사 처벌 + 차단
- 필요 서류: 사업자 등록증, 위치정보 처리방침, 기술적·관리적 보호조치 계획서
- 진행 상태는 `docs/compliance/lbs-act.md`에 추적 (작성 예정)

### 3.2 위치정보 별도 동의 (O-2)

회원가입 동의는 **4개 분리 체크**:

- (필수) 이용약관
- (필수) 개인정보 처리방침
- (필수) 위치기반서비스 이용약관
- (필수) 개인위치정보 수집·이용

각 항목 전문 보기 링크 + 별도 체크박스. 동의 철회 절차: `/profile/consents`.

`app.user_consents.consent_type` enum:

- `tos`, `privacy`, `lbs_tos`, `location_collection`, `marketing`,
  `demographic_use`(선택)

### 3.3 위치 감사 로그 (O-3)

`app.location_access_log`:

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
  ip_hash      CHAR(64) NOT NULL,
  prev_hash    CHAR(64) NOT NULL,
  content_hash CHAR(64) NOT NULL
);
CREATE INDEX ON app.location_access_log USING brin (occurred_at);
CREATE INDEX ON app.location_access_log (user_id, occurred_at DESC);
```

`content_hash`는 직전 row의 `content_hash` + 현재 row 표준 표현 SHA-256 →
변조 검증 가능 chain. 6개월 경과 자동 삭제 (Dagster job).

CPO 역할만 SELECT 가능 — `app.users.roles`에 `'cpo'` 포함 검사
(`docs/spec/v8/04-admin.md` M-14).

### 3.4 PIPA 2024 (O-4)

- 과징금: 전체 매출액 최대 3% (특정 조건 10%)
- 유출 "가능성 인지 시점" 즉시 통지 (이메일 + Admin 통지 이력)
- 자동 트리거:
  - 같은 user_id 짧은 시간 다수 IP/지역 → 강제 로그아웃 + 알림
  - admin 단시간 1000+ row export → CPO 알림
- 처리방침 의무 기재: 자동화 결정, 국외 이전, 위탁자, 보존기간, 파기 절차

### 3.5 Admin 접근 통제 (O-6)

`app.admin_audit_log`:

- `access_reason` 자유 텍스트 + 카테고리 (위험 액션 시 강제 입력)
- `target_pii_fields` 배열 (접근한 PII 필드 목록)
- `prev_hash` / `content_hash` chain
- `/admin/users/{id}` 진입 시 사유 입력 다이얼로그
- 목록에서 이메일/전화 **마스킹** (`a***@gmail.com`)
- 상세에서 사유 입력 후에만 원본
- Admin 로그인 2FA + 세션 1시간 + IP 화이트리스트 옵션

`app.users.roles`:

- `user`, `admin`, `operator`, `cpo` (4종)
- v1의 `is_admin BOOLEAN`은 정정 — `roles TEXT[]` 사용 (`docs/data-model.md` §2.1)

### 3.6 국외 이전 (O-7)

- 셀프호스팅 환경 → 일반적 국외 이전 의무 발생 없음
- 단 외부 의존 처리방침 명시 필수:
  - Google OAuth (Google 서버)
  - 카카오/VWORLD/TourAPI/기상청 (국내)
  - **Resend** (미국 AWS) — 위탁 처리자
  - Sentry SaaS (미국) — 위탁 처리자
- 향후 백업본을 외부 객체 스토리지(BackBlaze B2 등)에 두면 그 시점 갱신 필요

### 3.7 Privacy by Design 체크리스트 (O-8)

PR 템플릿에 통합:

- [ ] 새로 수집하는 개인정보가 있는가? 항목/목적/보유 명세
- [ ] 위치 데이터 새로 처리? `O-3` 감사 로그 미들웨어
- [ ] 새 저장 시 암호화·해싱?
- [ ] 외부 공유? 동의·법적 근거
- [ ] 처리방침 갱신 필요?
- [ ] Admin 노출 시 권한·마스킹?

## 4. 본 저장소 적용 작업 (Sprint 매핑)

| SPEC V8 항목 | Sprint | 산출물 |
|------|--------|--------|
| `infra/docker-compose.yml` (N-7) | Sprint 1 | `infra/docker-compose.yml` + `.app.yml` |
| ARM64 multi-arch (N-7.1) | Sprint 1 | `.github/workflows/api.yml` + `web.yml` |
| Sentry FastAPI/Next 통합 (N-8) | Sprint 2 | `apps/api/app/core/sentry.py` + `apps/web/sentry.client.config.ts` |
| Loki+Promtail+Grafana (N-9) | Sprint 5 | `infra/docker-compose.yml`에 추가 + Promtail config |
| structlog JSON (N-9) | Sprint 1 | `apps/api/app/core/logging.py` |
| `request_id` middleware (M-12) | Sprint 1 | `apps/api/app/middleware/request_id.py` |
| 백업 (N-3) | Sprint 5 | `scripts/backup-db.sh` + WAL 정책 |
| LBS 신고 (O-1) | Sprint 6 | 서류 준비 + 신고 |
| 위치 동의 (O-2) | Sprint 2 | G-5 UI + `user_consents` |
| 위치 감사 로그 (O-3) | Sprint 2 | `app.location_access_log` + 미들웨어 |
| PIPA 자동 트리거 (O-4) | Sprint 5 | 이상 접근 감지 / export 알림 |
| Admin 접근 통제 (O-6) | Sprint 3 | `roles`, audit chain, 마스킹, 사유 입력 |
| 처리방침 (O-7) | Sprint 6 | 4개 법무 문서 |

## 5. 관련 문서

- `docs/architecture.md` §5 운영 환경 / §6 보안
- `docs/dev-environment.md` §4 PostgreSQL+PostGIS
- `docs/postgres-schema.md` §2.4 `user_consents` / `location_access_log`
- `docs/decisions.md` ADR-004 (WSL 미러) / ADR-007 (PR-only)
- `docs/sprints/SPRINT-1.md` ~ `SPRINT-6.md`
