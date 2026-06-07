# SPRINT-6 — 마무리 + 출시 준비 + MCP 외부 인터페이스

- **상태**: proposed
- **선행**: Sprint 5 DoD 완료 (v0.2.0)
- **목표**: 일정 자동 최적화, Admin 보강, 컴플라이언스 (LBS 신고 + 법무 4 문서),
  **MCP 외부 인터페이스 (TripMate가 서빙)**, **Backup/Restore UI 핫스왑**,
  **한국 전용 geofencing**, **운영 하드웨어 확장 (Odroid + N150)**,
  E2E + 성능 + 보안 점검 — 외부 정식 출시 가능 상태
- **릴리즈**: `v1.0.0` (Sprint 6 종료 시 tag) — 외부 정식 출시.
- **DoD**:
  - `POST /trips/{id}/days/{day_index}/optimize` (OR-Tools)
  - 스마트 정렬 미리보기 UI (I-8)
  - `/admin/feature-requests` (사용자 요청 → 라이브러리 trigger)
  - `/admin/category-mapping` (`app.category_mappings`)
  - E2E 시나리오 6가지 통과 (Playwright)
  - 성능 측정 (API p95 latency, DB pool, WebSocket 동시)
  - 보안 점검 (CSP, CORS, rate limit, Argon2, Resend webhook signature)
  - LBS 사업자 신고 진행 (방통위 LBSC) — 본 Sprint 시작 시 신청
  - 법무 4 문서 작성/검토 (이용약관 / 처리방침 / LBS 약관 / 위치 동의)
  - 운영 환경 배포 smoke test 통과 — **Odroid M1S + N150 16GB / NVMe 1TB
    / Ubuntu 26.04 양쪽** (ADR-023)
  - 백업 + 복구 훈련 1회 — **핫스왑 패턴 검증** (ADR-022)
  - **MCP 외부 인터페이스 서빙** — `apps/api/app/mcp/` 모듈 + `/mcp/sse`
    엔드포인트. 외부 AI agent가 TripMate의 trip/poi/feature 데이터를
    토큰 인증으로 read. 자세히는 `docs/architecture/mcp-server.md` (ADR-019).
  - **Backup/Restore UI 핫스왑** — `/admin/backup` 페이지에서 snapshot 목록
    + 복구 시 동일 DB `app_restore_<ts>` schema로 hot import → schema-swap cut-over (ADR-022,
    `docs/runbooks/backup-restore.md`)
  - **한국 전용 geofencing** — Cloudflare WAF + nginx geo + FastAPI middleware
    (3중 안전) — KR 외 IP는 451 (`docs/architecture/korea-only-policy.md`,
    ADR-018)
  - **T-107 (Gemini) 별도 서비스로 분리** — 본 저장소에서 제거, 별 repo
    (`tripmate-ai-companion` 또는 사용자 지정)로 이동. local docker-to-docker
    호출 패턴. 자세히는 ADR-020.

## 산출물

### 백엔드

- `apps/api/app/services/route_optimizer.py` (OR-Tools)
- `apps/api/app/api/v1/optimize.py` (`POST /trips/{id}/days/{day_index}/optimize`,
  `GET /trips/{id}/days/{day_index}/distance-matrix`)
- `apps/api/app/api/v1/admin/{feature_requests,category_mappings}.py`
- `apps/api/app/services/distance_matrix.py` (PostGIS + 카카오 모빌리티 + cache)
- **`apps/api/app/mcp/`** — TripMate MCP 서버 (ADR-019):
  - `__init__.py` / `server.py` — FastAPI sub-app or 별 binary 선택 (ADR에서 결정)
  - `tools/{list_trips,get_trip,list_pois,search_features,get_user_profile}.py`
  - `auth.py` — 전용 MCP token (JWT scope=`mcp:read`) — 사용자가
    `/admin/mcp-tokens` 또는 `/users/me/mcp-tokens`에서 발급
  - `/mcp/sse` (또는 `/mcp/stdio` 둘 중 SPEC 결정에 따라 — `docs/architecture/mcp-server.md`)
- **`apps/api/app/services/backup_service.py`** 확장 — Sprint 5의 trigger를
  핫스왑 워크플로로:
  - `snapshot()` → 기존 (Sprint 5)
  - `restore_hotswap(snapshot_id)` → 신규: 같은 DB의 `app_restore_<ts>` schema로
    복구 → write drain → `app` / `app_previous_<ts>` schema-swap → previous schema
    보존 후 삭제
- **`apps/api/app/middleware/geofence.py`** — `X-Real-IP` 기반 KR 외 차단
  (`docs/architecture/korea-only-policy.md`). Cloudflare WAF가 1차, nginx가 2차,
  본 미들웨어가 3차 안전망.

### 프론트엔드

- `apps/web/components/poi/OptimizeDialog.tsx` (미리보기 + 옵션 + 적용)
- `apps/web/app/admin/feature-requests/page.tsx`
- `apps/web/app/admin/category-mapping/page.tsx`
- `apps/web/components/admin/CategoryMappingEditor.tsx` (P-01~P-16 색상 + maki 선택)
- Admin notice plan 작성기 (`docs/architecture/notice-plans.md`):
  - `apps/web/app/admin/notice-plans/page.tsx` (목록)
  - `apps/web/app/admin/notice-plans/[planId]/page.tsx` (편집)
  - `apps/web/app/admin/notice-plans/new/page.tsx` (생성)
  - `apps/web/components/admin/NoticePoiEditor.tsx`
  - 첨부 업로드 + 미리보기 (`POST /storage/upload-urls` + presigned PUT)
- **Backup/Restore UI 핫스왑** (ADR-022):
  - `apps/web/app/admin/backup/page.tsx` 확장 — snapshot 목록 + manual trigger
    + 복구 시작
  - `apps/web/components/admin/RestoreHotswapDialog.tsx` — snapshot 선택 →
    progress (schema 준비 / pg_restore / validate / drain / schema-swap 단계 표시) → 결과
  - `apps/web/components/admin/SnapshotTable.tsx`
- **MCP 토큰 관리 UI** (ADR-019):
  - `apps/web/app/admin/mcp-tokens/page.tsx` — admin 전체 토큰 / 발급 / revoke
  - `apps/web/app/(app)/settings/mcp-tokens/page.tsx` — 사용자 본인 토큰
  - `apps/web/components/mcp/McpTokenIssuer.tsx` (scope / 만료 / description)

### 컴플라이언스

- `docs/compliance/lbs-act.md` — 신고 상태 추적
- `docs/compliance/pipa.md` — PIPA 2024 점검 매트릭스
- `docs/legal/terms-of-service.md` (placeholder + 변호사 검토)
- `docs/legal/privacy-policy.md`
- `docs/legal/lbs-terms.md`
- `docs/legal/location-consent.md`

### 인프라 / 운영

- `infra/odroid/README.md` (배포 절차) — 유지
- `infra/n150/README.md` (신규, ADR-023) — N150 16GB / NVMe 1TB / Ubuntu 26.04
  배포 + Odroid 대비 변경점 (x86_64 vs ARM64 이미지)
- `scripts/{odroid-docker-doctor,n150-docker-doctor,backup-db,restore-db,restore-hotswap}.sh`
- `infra/docker-compose.app.yml` 최종 — x86_64 / ARM64 멀티 platform
- `infra/nginx/{nginx.conf,geo-kr.conf}` — 한국 IP 화이트리스트 (ADR-018)
- `infra/cloudflare/wrangler.toml` 또는 dashboard 설정 메모 — WAF rule "Country
  ≠ KR → Block 451" (`docs/architecture/korea-only-policy.md`)
- nginx + Let's Encrypt + certbot 설정
- DDNS 또는 Cloudflare Tunnel
- **`apps/api/Dockerfile`**: multi-platform build (linux/amd64 + linux/arm64)
- **MCP 서버 별 docker service** (선택, ADR-019에서 결정): `mcp` service 또는
  `api` 본체에 통합

### 테스트

- `apps/web/tests/e2e/{signup_to_trip,companion_realtime,smart_sort,share_link,admin_audit,etl_ingestion}.test.mjs`
- `tests/load/api_p95_latency.py` (locust 또는 hey)
- `tests/security/csp_cors_rate_limit.py`

### ADR

- 후속 ADR 후보(번호 미배정): OR-Tools 경로 최적화 정책 (POI ≤10/11-20/20+ 분기)
- 후속 ADR 후보(번호 미배정): 카테고리 매핑 운영 정책 (라이브러리 default + DB override + 사용자 custom)
- **ADR-018** (참조): 한국 전용 서비스 정책 + geofencing 3중 안전망
- **ADR-019** (참조): TripMate MCP 외부 인터페이스 서빙 (tool 목록 / 인증 / scope)
- **ADR-020** (참조): T-107 (Gemini AI) 별도 서비스 분리
- **ADR-022** (참조): Backup/Restore 핫스왑 정책 (snapshot → restore schema → schema-swap)
- **ADR-023** (참조): 운영 하드웨어 확장 (Odroid M1S + N150 16GB 병행)

## SPEC V8 매핑

- 02-backend.md §6 (H-8 일정 최적화)
- 03-frontend.md §8 (I-8 스마트 정렬 UI)
- 04-admin.md §2 (M-2 `/admin/feature-requests`, `/admin/category-mapping`)
- 00-infrastructure.md §3 (O장 컴플라이언스 전체)
- 05-execution.md §4.3 (C-3 출시 직전)

## 출시 직전 체크리스트 (C-3)

- [ ] 사업자 등록 (LBS 신고에 필수)
- [ ] LBS 사업자 신고 완료 (방통위)
- [ ] 법무 4 문서 변호사 검토 통과
- [ ] HTTPS 인증서 + 자동 갱신 cron
- [ ] 백업 외부 위치 (BackBlaze B2 또는 NAS)
- [ ] 분기 1회 복구 훈련 통과
- [ ] Sentry 알림 채널 (이메일 + Telegram bot)
- [ ] UptimeRobot 또는 Better Stack 모니터
- [ ] DDNS 또는 Cloudflare Tunnel 안정 동작
- [ ] 도메인 + 브랜드명 확정 + Resend 도메인 인증 verified
- [ ] 외부 API 키 모두 발급 + 일 호출 한도 확인

## E2E 시나리오 (Playwright)

1. 가입 + verify + 로그인 + 프로필 완성 (G장)
2. 여행 생성 + 동반자 초대 + 공유 토큰 발급
3. POI 추가 + 우클릭 메뉴 + 드래그 정렬 + 스마트 정렬 적용
4. 동반자 동시 편집 + 충돌 다이얼로그
5. Admin force-verify + audit log chain 검증
6. ETL 자산 manual trigger + dedup-review
7. **MCP 토큰 발급 → 외부 stdio client (`mcp-cli` 또는 Claude Code MCP server)
   → `list_trips` / `search_features` 호출 → 응답 검증** (ADR-019)
8. **Backup 핫스왑: snapshot 생성 → 더미 변경 후 restore_hotswap → schema-swap 데이터
   복구 확인 + previous schema 자동 삭제 trigger 검증** (ADR-022)
9. **한국 외 IP에서 접근 → 451 응답 + landing page redirect** (ADR-018)

## 종료 체크리스트

- [ ] DoD 모두 통과
- [ ] E2E **9** 시나리오 통과 (기존 6 + MCP / Backup 핫스왑 / Geofence)
- [ ] 운영 환경 smoke test 통과 — **Odroid + N150 양쪽** (ADR-023)
- [ ] **MCP 외부 인터페이스 1차 client 실증** (Claude Code MCP server 등록 후
  TripMate trip 조회 성공)
- [ ] **Backup 핫스왑 분기 1회 훈련 통과 (RTO 1h / RPO 24h)**
- [ ] **한국 외 IP 차단 검증 (VPN 미국/일본 노드에서 451 응답 확인)**
- [ ] **T-107 (Gemini) 별도 repo 분리 + 호출 컨트랙트 문서 (`docs/integrations/ai-companion.md`)**
- [ ] 첫 외부 사용자(가족 베타) 가입 + 여행 생성 성공
- [ ] **`v1.0.0` git tag + GitHub Release notes**
- [ ] `docs/journal.md` Sprint 6 종료 + v1.0 출시 엔트리
- [ ] `docs/resume.md` 진척도 → v1 출시 / v2 후보 백로그

## v1 출시 후 (post-Sprint 6)

- v2 후보: PWA, Redis Streams, 푸시 알림, 사진 업로드, 다국어, 결제,
  GPX 업로드, 공개 여행 / 커뮤니티, 댓글
- AI 추천 / 챗봇은 별 repo (`tripmate-ai-companion`, ADR-020) — Gemini /
  Claude / Codex 등 provider 선택 가능. local docker-to-docker 호출로 본
  서비스 통합.
- `docs/tasks.md`에 T-100 ~ T-200 백로그로 관리
- v1.0 → v1.1 마이너: PWA + 푸시 알림 + 사진 업로드 우선
- 해외 진출 시 ADR-018 (한국 전용) supersede 필요
