# SPRINT-6 — 마무리 + 출시 준비

- **상태**: proposed
- **선행**: Sprint 5 DoD 완료
- **목표**: 일정 자동 최적화, Admin 보강, 컴플라이언스 (LBS 신고 + 법무 4 문서),
  E2E + 성능 + 보안 점검 — 외부 정식 출시 가능 상태
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
  - 운영 환경 (Odroid M1S) 배포 smoke test 통과
  - 백업 + 복구 훈련 1회

## 산출물

### 백엔드

- `apps/api/app/services/route_optimizer.py` (OR-Tools)
- `apps/api/app/api/v1/optimize.py` (`POST /trips/{id}/days/{day_index}/optimize`,
  `GET /trips/{id}/days/{day_index}/distance-matrix`)
- `apps/api/app/api/v1/admin/{feature_requests,category_mappings}.py`
- `apps/api/app/services/distance_matrix.py` (PostGIS + 카카오 모빌리티 + cache)

### 프론트엔드

- `apps/web/components/poi/OptimizeDialog.tsx` (미리보기 + 옵션 + 적용)
- `apps/web/app/admin/feature-requests/page.tsx`
- `apps/web/app/admin/category-mapping/page.tsx`
- `apps/web/components/admin/CategoryMappingEditor.tsx` (P-01~P-16 색상 + maki 선택)

### 컴플라이언스

- `docs/compliance/lbs-act.md` — 신고 상태 추적
- `docs/compliance/pipa.md` — PIPA 2024 점검 매트릭스
- `docs/legal/terms-of-service.md` (placeholder + 변호사 검토)
- `docs/legal/privacy-policy.md`
- `docs/legal/lbs-terms.md`
- `docs/legal/location-consent.md`

### 인프라 / 운영

- `infra/odroid/README.md` (배포 절차)
- `scripts/{odroid-docker-doctor,backup-db,restore-db}.sh`
- `infra/docker-compose.app.yml` 최종
- nginx + Let's Encrypt + certbot 설정
- DDNS 또는 Cloudflare Tunnel

### 테스트

- `apps/web/tests/e2e/{signup_to_trip,companion_realtime,smart_sort,share_link,admin_audit,etl_ingestion}.test.mjs`
- `tests/load/api_p95_latency.py` (locust 또는 hey)
- `tests/security/csp_cors_rate_limit.py`

### ADR

- ADR-NNN: OR-Tools 경로 최적화 정책 (POI ≤10/11-20/20+ 분기)
- ADR-NNN: 카테고리 매핑 운영 정책 (라이브러리 default + DB override + 사용자 custom)
- ADR-NNN: 운영 배포 (Odroid M1S + DDNS + Cloudflare Tunnel)
- ADR-NNN: 백업 / 복구 정책 (RTO 1h / RPO 24h + 분기 1회 훈련)

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

## 종료 체크리스트

- [ ] DoD 모두 통과
- [ ] E2E 6 시나리오 통과
- [ ] 운영 환경 smoke test 통과
- [ ] 첫 외부 사용자(가족 베타) 가입 + 여행 생성 성공
- [ ] `docs/journal.md` Sprint 6 종료 + v1.0 출시 엔트리
- [ ] `docs/resume.md` 진척도 → v1 출시 / v2 후보 백로그

## v1 출시 후 (post-Sprint 6)

- v2 후보: PWA, Redis Streams, 푸시 알림, 사진 업로드, 다국어, 결제, AI 추천,
  GPX 업로드, 공개 여행 / 커뮤니티, 댓글
- `docs/tasks.md`에 T-100 ~ T-200 백로그로 관리
