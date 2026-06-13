# SPEC V8 #4 — Admin · 디버그 (Pinvi 적용 노트)

원본: `spec_v8_4_admin.docx` (M장 Admin 13개 sub-section).

## 1. 목적 (M-1)

- 화려하지 않게, 데이터를 정직하게
- ETL 데이터 수신 / 회원가입·이메일·동의 / 여행·POI 동작 / 외부 API 상태 검증
- shadcn/ui Data Table 또는 TanStack Table — 단순 테이블 + 필터 + 페이지네이션 + JSON viewer

## 2. 13개 페이지 (M-2)

| 경로 | 내용 | Sprint |
|------|------|--------|
| `/admin` | 대시보드 (지표 카드 8개) | 3 |
| `/admin/users` / `/admin/users/{id}` | 사용자 목록/상세 + 디버그 액션 | 3 |
| `/admin/trips` / `/admin/trips/{id}` | 여행 목록/상세 + 멤버/POI/공유 토큰 | 3 |
| `/admin/features` | 라이브러리 feature 검색 (read-only, kor-travel-map admin API 결선 후) | 3 |
| `/admin/pois` | POI 검색 (`feature_link_broken_at` 필터) | 3 |
| `/admin/etl` | Dagit reverse-proxy + 자체 요약 | 5 |
| `/admin/api-calls` | 외부 API 호출 로그 (`app.api_call_log`) | 3 |
| `/admin/emails` | `app.email_queue` 목록 + 재발송 | 3 |
| `/admin/audit` | `app.admin_audit_log` (read-only, chain 검증) | 3 |
| `/admin/feature-requests` | 사용자 feature 요청 큐 → 라이브러리 적재 trigger | 6 |
| `/admin/category-mapping` | `app.category_mappings` | 6 |
| `/admin/seed` (dev only) | 8 시나리오 샘플 (운영 환경 차단 안전장치 후 결선) | 3 |
| `/admin/reset` (dev only) | DB 전체 reset (확인 다이얼로그/운영 라우트 미등록 후 결선) | 3 |

추가 (M-15) — `kor-travel-map` schema 가시화:

| 경로 | 내용 | Sprint |
|------|------|--------|
| `/admin/features/{id}/sources` | `feature.source_links` 표시 (source_role 필터) | 5 |
| `/admin/features/{id}/overrides` | `feature.overrides` (correction 이력) | 5 |
| `/admin/features/{id}/weather-values` | KMA 시간축 timeline | 5 |
| `/admin/weather-values` | 통합 weather 검색 | 5 |
| `/admin/provider-sync` | `provider_sync.state` 재시도/일시정지/재개 | 5 |
| `/admin/dedup-review` | Record Linkage 의심 쌍 좌우 비교 (K-4) | 5 |
| `/admin/integrity` | `app.data_integrity_violations` | 5 |
| `/admin/debug/logs` | Loki LogQL stream (WebSocket) | 5 |
| `/admin/debug/request/{request_id}` | 단일 요청 타임라인 추적 | 5 |

## 3. 공통 UI 패턴 (M-3)

```tsx
<AdminPage title="...">
  <FilterBar>
    <Select name="status" options={...} />
    <Input name="q" placeholder="검색..." />
    <DateRangePicker name="updated_at" />
  </FilterBar>
  <DataTable columns={...} rows={data} onRowClick={...} />
  <Pagination cursor={meta.cursor} hasMore={meta.has_more} />
</AdminPage>

<AdminDetailPage title="..." backHref="...">
  <Section title="기본 정보"><KeyValueGrid data={...} /></Section>
  <Section title="관계"><DataTable inline ... /></Section>
  <Section title="액션"><ActionButton ... /></Section>
  <Section title="Raw JSON" defaultCollapsed>
    <JsonViewer data={raw} />
  </Section>
</AdminDetailPage>
```

## 4. 권한 / RBAC (M-4 + M-14)

- `app.users.roles TEXT[]` (`is_admin BOOLEAN` 정정, M-14)
- 역할: `user` / `admin` / `operator` / `cpo`
- 미들웨어에서 강제 — 403 with no body (존재 자체를 숨김)
- 모든 mutating 액션 → `admin_audit_log` 자동 기록 (FastAPI middleware)
- dev-only 라우트는 환경변수 가드 + 운영에서 라우트 자체 미등록 (조건부 router include)

부트스트랩: `BOOTSTRAP_ADMIN_EMAIL` 환경변수 또는 첫 가입자 자동 승격 (선택).

## 5. CRUD 권한 매트릭스 (M-8)

| 리소스 | C | R | U | D | 비고 |
|--------|---|---|---|---|------|
| users | ✗ | ✓ | ✓ | ○ | 생성=가입. 삭제=soft + 30일 후 hard |
| trips | ✗ | ✓ | ✓ | ○ | 임의 생성 X |
| features | ✓ | ✓ | ✓ | ○ | 라이브러리에 위임 — Pinvi는 trigger만 |
| category_mappings | ✓ | ✓ | ✓ | ✓ | 자유 편집 |
| api_call_log | ✗ | ✓ | ✗ | ✗ | read-only |
| location_access_log | ✗ | ◐ | ✗ | ✗ | CPO만. chain 검증 |
| admin_audit_log | ✗ | ✓ | ✗ | ✗ | append-only |

`○` 조건부 / `◐` 사유 입력 등.

## 6. 검색 문법 (M-9)

자유 텍스트 + 필드 prefix:

```
q=홍길동                       # OR ILIKE
q=email:gmail.com              # field ILIKE
q=id:u-001                     # 정확 매칭
q="홍 길동"                    # 토큰 정확 매칭
q=-status:disabled             # NOT
q=created_at:>2026-01-01      # 비교
q=trip_count:>=5
```

알 수 없는 필드는 무시 (에러 X) — 점진적 결과.

faceted 필터 + 저장된 뷰 (개인 + 팀 공유). URL 쿼리 동기화.

## 7. ETL 현황 (M-10)

`/admin/etl`:

- Dagit 임베드 (옵션 1, 권장) + 자체 요약 페이지
- 자산 카드: 상태 / 마지막 실행 / 다음 실행 / 처리 건수 / [지금 실행] / [상세]
- 자산 상세: 30일 실행 이력 / 의존 그래프 / 에러 로그 / 입력 샘플 / 출력 메트릭 / 수동 trigger

본 저장소의 Dagster code location은 `apps/etl` (ADR-006).
`kor-travel-map`의 collect/load 함수는 asset에서 호출.

## 8. Record Linkage 검토 큐 (M-10 + K-4)

`/admin/dedup-review`:

- `dedup_review_queue` (`kor-travel-map` 소유) read
- 좌우 분할: A 후보 vs B 후보 (name/coord/address/category/raw_refs/리뷰 링크)
- 판정 액션: [같음→A로 병합] / [같음→B로 병합] / [다름→무시] / [의심→보류]
- 판정 결과 → 라이브러리에 callback (ML 학습 데이터 누적)

## 9. 데이터 일관성 (M-11)

`/admin/integrity` — `app.data_integrity_violations` 1차 소스 + Dagster 일 1회 검증.

룰 예시 (10건):

| 룰 | 대상 schema | 자동수정 |
|------|------|---------|
| orphan POI | app | ✓ |
| sort_order 중복 | app | ✓ |
| 일자 범위 초과 POI | app | ✗ |
| 이메일 미인증 7일 경과 | app | ✓ |
| audit log chain 깨짐 | app | ✗ (즉시 CPO 알림) |
| dangling parent_feature_id | feature (라이브러리에서 처리) | ○ |
| 동일 좌표 multiple features | feature | ○ |
| 권한 없는 동반자 | app | ○ |
| vworld bjd_lookup 누락 | feature | ✗ |
| price_values retention 위반 | feature | ✓ |

자동수정 가능: [자동 수정] → `admin_audit_log` 기록. 불가: 케이스별 수동.

## 10. 디버그 콘솔 (M-12)

`/admin/debug/logs`:

- Loki LogQL을 백엔드에서 호출 → WebSocket으로 push
- 필터: `level`, `service`, `request_id`, `user_id`, `trip_id`
- structlog JSON 출력 그대로 활용

`/admin/debug/request/{request_id}`:

- X-Request-Id 기반 단일 요청 타임라인
- FastAPI route hit → JWT verified → DB SELECT → 외부 API → DB INSERT →
  Dagster event → WebSocket broadcast → HTTP response
- 각 단계 소요 시간 + 외부 API raw 응답 + DB query EXPLAIN

DB slow query + 외부 API 모니터:

- 1초 이상 query 자동 표시
- provider 별 응답 시간 분포 + 실패율 + rate limit 잔여
- 실패 응답 raw 마지막 100건 보존

## 11. Seed / Reset (M-13)

`/admin/seed` 시나리오 8건:

- 새 사용자 + 첫 여행
- 동반자 동시 편집 (5명 WebSocket simulator)
- 만료 임박 공유 링크 (1일/3일/30일)
- 이메일 미인증 사용자
- Record Linkage 후보 5건
- ETL 실패 시뮬레이션 (외부 API mock fail)
- 대규모 POI (200개)
- audit log 샘플 (30일치)

안전장치 (Critical):

- `ENV=production` 시 라우트 자체 404 (조건부 router include)
- seed 실행은 `admin_audit_log` 기록
- `/admin/reset`: "내 admin 비밀번호" + "RESET" 키워드 입력 강제

## 12. 시나리오 (M-7)

PR 머지 전 verify checklist로 활용:

1. ETL 잘 도는지: `/admin` → `/admin/etl` → `/admin/api-calls` → `/admin/features?updated_after=24h`
2. 회원가입 잘 되는지: `/signup` → `/admin/users?status=pending_verification` → `/admin/emails` → 클릭 후 상태 변화
3. 동반자 초대: A로 trip 생성 + B 초대 → `/admin/trips/{id}` → `/admin/emails` → B 가입 후 `joined_at`
4. feature 링크 broken: `/admin/features` DELETE → `/admin/pois?feature_link_broken=true` → snapshot 폴백 확인

## 13. Sprint 매핑

| SPEC V8 항목 | Sprint | 본 저장소 산출물 |
|------|--------|------------------|
| Admin 뼈대 (M-3) | Sprint 3 | `apps/web/app/admin/layout.tsx` + 공통 컴포넌트 |
| `/admin/users` ~ `/admin/pois` (M-2) | Sprint 3 | `apps/web/app/admin/{users,trips,features,pois}/...` |
| `roles` RBAC (M-14) | Sprint 3 | `apps/api/app/api/v1/admin/deps.py` |
| `admin_audit_log` chain (M-14) | Sprint 3 | `apps/api/app/middleware/admin_audit.py` |
| `/admin/api-calls`, `/admin/emails`, `/admin/audit`, `/admin/audit/location` | Sprint 3 | `apps/web/app/admin/...` |
| `/admin/seed` + 안전장치 (M-13) | Sprint 3 | 환경 조건 + 8 시나리오 |
| `/admin/etl` Dagit 임베드 (M-10) | Sprint 5 | reverse proxy + 자체 요약 |
| `/admin/dedup-review` (K-4) | Sprint 5 | `dedup_review_queue` 호출 |
| `/admin/features/{id}/sources/overrides/weather` (M-15) | Sprint 5 | 라이브러리 schema 가시화 |
| `/admin/provider-sync` (M-15) | Sprint 5 | `provider_sync.state` 관리 |
| `/admin/integrity` (M-11) | Sprint 5 | `data_integrity_violations` |
| `/admin/debug/logs` Loki stream (M-12) | Sprint 5 | WebSocket LogQL |
| `/admin/debug/request/{id}` (M-12) | Sprint 5 | X-Request-Id 타임라인 |
| `/admin/feature-requests`, `/admin/category-mapping` | Sprint 6 | 라이브러리 trigger UI |

## 14. 관련 문서

- `docs/spec/v8/02-backend.md` H-6 (Admin API)
- `docs/spec/v8/01-data.md` (`admin_audit_log` chain)
- `docs/spec/v8/00-infrastructure.md` (Loki, Sentry deep link)
- `docs/kor-travel-map-integration.md` (M-15 라이브러리 schema 호출)
