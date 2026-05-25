# SPEC V8 #5 — 실행 · 결정 · Sprint (TripMate 적용 노트)

원본: `spec_v8_5_execution.docx` (A 결정 / P Sprint / C 추가 결정 대기).

## 1. 필수 결정 6건 (A-1, 모두 확정)

| # | 항목 | 결정 | TripMate v2 매핑 |
|---|------|------|------------------|
| 1 | vworld 법정동코드 파일 | vworld.kr txt 사용 | `python-kraddr-geo`가 임포트 (L장 / `python-krtour-map` ADR-006) |
| 2 | 참여자 동의 UI | 프로필 입력 시 통합. 필수/선택 분리 | G-5 4 분리 동의 (`docs/spec/v8/02-backend.md` §4.2) |
| 3 | 소셜 로그인 매칭 | 이메일 인증 방식. verify 후만 활성/연결 | G-4 안전 매칭 (F-3) |
| 4 | 카카오맵 SDK | `react-kakao-maps-sdk` 직접 사용 | I-2 컴포넌트 + 일 호출 한도 관리 |
| 5 | 운영 환경 | Odroid M1S + Ubuntu 24.04 + Docker. 셀프호스팅 | N-7 (`docs/spec/v8/00-infrastructure.md` §2.1) |
| 6 | 이메일 발송 | Resend (React Email + SPF/DKIM/DMARC + webhook) | G-6 (`docs/spec/v8/02-backend.md` §4.3) |

## 2. 권장 채택 (A-2)

| 영역 | 채택 |
|------|------|
| 백엔드 | FastAPI + SQLAlchemy 2 + Alembic + PostGIS + Dagster (Redis 없음) |
| 프론트 | Next.js 15 + Zustand + TanStack Query v5 + RHF + Zod + dnd-kit + Tailwind |
| 인증 | JWT (15m + 7d) + email verify + Google OAuth (verified_email) |
| 16색 팔레트 | P-01 ~ P-16 (브랜드 색 확정 전 임시) |
| 동시 편집 | LWW + optimistic lock + fractional indexing |
| 공유 링크 | 256bit + 30일 기본 + revoke |
| PWA | v1 미포함 (카카오맵 약관 차원) |
| 실시간 수평 확장 | v1 단일 (v2: Redis Streams) |
| 알림 | v1 이메일만. push는 v2 |
| 사진 업로드 | v1 아바타만. RustFS. 여행 사진 v2 |
| ETL 모니터링 | v1 Dagit 임베드. 자체 UI v2 |
| 다국어 | ko 만. next-intl i18n-ready |
| 동반자 권한 | POI/일정 편집만. 동반자 추가/공유 발급은 리더만 |

## 3. Sprint 계획 (P장)

SPEC V8 원본의 Sprint 순서를 TripMate v2 책임 분담에 맞춰 정리.

### Sprint 1 (1~2주) — 기반

- DB 초기 schema (`app` schema) + Alembic 마이그레이션
- FastAPI 뼈대 + Argon2 + JWT + 회원가입 + 이메일 인증
- Next.js 뼈대 + 로그인/가입/verify 화면
- `infra/docker-compose.yml`
- CI 3 워크플로 (api/web/etl)
- structlog + Sentry FastAPI

DoD: `/healthz` + 가입 → verify → 로그인 e2e 통과 + `pytest -q` + `npm lint typecheck build`.

자세히는 `docs/sprints/SPRINT-1.md`.

### Sprint 2 (2주) — 도메인 API + DB

- Trip CRUD + 동반자 + 공유 토큰 (H-3)
- POI CRUD + optimistic lock + COLLATE "C" (E-3, E-6)
- 4 분리 동의 + 위치 감사 미들웨어 (G-5, O-3)
- Resend 통합 + `email_queue` worker (G-6)
- Google OAuth + 안전 매칭 (G-4)
- `python-krtour-map` DI helper skeleton (호출은 Sprint 4부터)

DoD: UI 없이 API + DB 완성.

### Sprint 3 (2주) — Admin 데이터 디버그 (지도 UI 전)

- Admin 뼈대 + 공통 DataTable/FilterBar
- `/admin/users`, `/admin/trips`, `/admin/features`(read), `/admin/pois`
- `roles` RBAC + `admin_audit_log` chain
- `/admin/api-calls`, `/admin/emails`, `/admin/audit`
- `/admin/seed` 안전장치 + 8 시나리오
- M-7 시나리오 4가지 통과

DoD: ETL/회원가입/여행 동작 검증을 Admin으로 완료.

### Sprint 4 (2~3주) — 지도 + 사용자 UI

- 카카오맵 어댑터 (`react-kakao-maps-sdk`)
- viewport 기반 feature 로딩 + 클러스터링 (I-4)
- POI D&D + 양방향 패널 (I-5)
- 16색 팔레트 + maki 아이콘 (I-6)
- 우클릭 메뉴 (I-7)
- Trip 대시보드 (초기화면 미래/과거 아코디언)
- `python-krtour-map` 라이브러리 read 활성화

DoD: 일반 사용자가 PC/모바일에서 여행 생성 + POI 추가 + 지도 확인.

### Sprint 5 (2주) — 실시간 + ETL

- WebSocket 동기화 (J장)
- Dagster code location 활성화 — 첫 4 asset:
  - VisitKorea 축제 (event)
  - OpiNet 유가 (price)
  - KMA 단기 예보 (weather)
  - 국가유산 (Sprint plan E)
- vworld 법정동코드 임포트 trigger UI (L-3)
- `/admin/etl` Dagit 임베드
- `/admin/dedup-review` Record Linkage 검토 (K-4)
- `/admin/features/{id}/sources/overrides/weather-values` (M-15)
- `/admin/provider-sync` 재시도/일시정지/재개
- `/admin/integrity` 데이터 일관성
- `/admin/debug/logs` + `request/{id}` 추적
- Loki + Promtail + Grafana 컨테이너

DoD: 라이브러리 통합 + 첫 적재 + 실시간 동시 편집.

### Sprint 6 (2주) — 마무리

- Admin 보강: `/admin/feature-requests`, `/admin/category-mapping`
- 일정 자동 최적화 UI (스마트 정렬, I-8 / H-8)
- E2E 테스트 + 성능 측정 + 보안 점검
- LBS 사업자 신고 (O-1)
- 법무 4 문서
- 처리방침 / 이용약관 / LBS 약관 / 위치 동의

DoD: 외부 정식 출시 가능 상태.

> **Sprint 3가 Sprint 4보다 앞** — 데이터 흐름을 Admin으로 검증한 뒤 지도 UI.
> SPEC V8 원본의 핵심 결정 (M장 머리말).

## 4. 추가 결정 대기 (C장)

### C-1 즉시 (Sprint 1 시작 전)

| 항목 | 상태 | 메모 |
|------|------|------|
| 도메인 + 브랜드명 | ❓ 대기 | manifest / Resend / OAuth redirect / 이메일 발신자에 모두 필요 |
| 외부 API 인증키 일괄 신청 | ❓ 대기 | VWORLD / TourAPI / 기상청 / 행안부 / 카카오 / OpiNet / KHOA / 천문연 / KASI |
| Resend 가입 + 도메인 | ❓ 대기 | 도메인 결정 후 |
| Git 리포지토리 | ✓ `tripmate` | 본 저장소 + `python-krtour-map` 별 저장소 |
| CI/CD 플랫폼 | ✓ GitHub Actions | Sprint 1에서 활성화 |
| Container Registry | ❓ 대기 | GHCR 권장 |
| Odroid NVMe 용량 | ❓ 대기 | 256GB 시작 권장 |

### C-2 Sprint 2~4 사이

| 항목 | 권장 |
|------|------|
| Uptime 모니터 | UptimeRobot 무료 또는 Better Stack |
| Sentry release 정책 | main 머지 시 자동 + git short sha |
| DB 마이그레이션 정책 | v1 단순 alembic + 30초 503 허용 |
| 공유 링크 보안 강화 | v2 비밀번호/PIN |
| 이메일 발송 rate limit | Resend + 자체 1분 5회 |

### C-3 출시 직전 (Sprint 5~6)

| 항목 | 비고 |
|------|------|
| 사업자 등록 | LBS 신고 필수. 개인사업자 빠름 |
| 법무 4 문서 | 변호사 검토 권장 |
| 고객 지원 채널 | v1: 이메일 + FAQ |
| 분석 도구 | Plausible/Umami 자체호스팅 (PII 친화) |
| HTTPS 인증서 | Let's Encrypt + certbot 자동 갱신 |
| 백업 외부 위치 | BackBlaze B2 권장 |
| RTO/RPO | RPO 24h / RTO 1h / 분기 1회 훈련 |

### C-4 v2 / 장기

- PWA / 오프라인 (카카오맵 약관 + 다계층 캐싱)
- Redis Streams 수평 확장
- 푸시 알림 (Web Push API)
- 여행/POI 사진 업로드 + 부적절 검출
- 다국어 en/ja/zh
- 결제 (카카오페이 / 토스 / 스트라이프)
- AI 추천 (일정 자동 작성, Gemini 통합)
- GPX 업로드 (route feature)
- 고유식별정보 (여권, 항공권 예약)
- 공개 여행 / 댓글 / 커뮤니티

## 5. SPEC V8 후속 메모 (2026-05-16 ~ 2026-05-20)

원본에 후속 추가된 결정 메모. TripMate v2에 반영:

- **M, N (2026-05-16)** — `users.role` RBAC, audit log chain, provider canonical
  명칭, weather slot 정의
- **O (2026-05-17)** — `python-krtour-map` 책임 분리 (feature schema 이관) →
  v2의 ADR-001/002/003 mirror
- **P (2026-05-19)** — 국가유산 (`python-krheritage-api`) 추가
- **Q, R (2026-05-20)** — asyncio provider 통합, 표준데이터 5건, debug UI 정책,
  wrapper 절대 지양

위 메모는 본 디렉토리의 각 spec 파일에 반영됨.

## 6. 본 저장소의 Sprint 문서

- `docs/sprints/README.md` — 인덱스
- `docs/sprints/SPRINT-1.md` — 기반 (proposed)
- `docs/sprints/SPRINT-2.md` — 도메인 API + DB (작성 예정)
- `docs/sprints/SPRINT-3.md` — Admin (작성 예정)
- `docs/sprints/SPRINT-4.md` — 지도 (작성 예정)
- `docs/sprints/SPRINT-5.md` — 실시간 + ETL (작성 예정)
- `docs/sprints/SPRINT-6.md` — 마무리 (작성 예정)

## 7. 관련 문서

- `docs/decisions.md` (ADR-001 ~ ADR-010)
- `docs/resume.md` (다음 한 작업)
- `docs/tasks.md` (백로그)
- `docs/journal.md` (작업 일지)
