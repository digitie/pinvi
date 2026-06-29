# Sprint 6 / v1.0.0 상세 실행 계획

> T-260 산출물. Sprint 6의 남은 구현 task를 그룹·의존성·게이트·병행 관점으로 정리한다.
> 단위 task의 정본 backlog는 `docs/tasks.md`, 완료 이력은 `docs/tasks-done.md`, 작성 규칙은
> `docs/tasks-rule.md`, 마일스톤 표는 `docs/sprints/README.md`·`docs/sprints/SPRINT-6.md`다.

## 1. 범위와 원칙

- **v1.0.0 = Web/API/Admin 운영 출시.** `apps/mobile`(Sprint M-1)과 user-facing AI companion은
  release blocker에서 제외한다(T-284). AI companion 관련 T-113/T-272/T-285는 2026-06-29 사용자
  지시로 열린 backlog에서 제거했고, 향후 필요 시 기존 `kor-travel-concierge` API를 활용한다.
- Docker 이미지는 운영 노드 로컬 checkout + 로컬 build 기준. ARM 이미지/GHCR 배포는 범위 밖(ADR-040/042/047).
- 노드 간 DB live sync 미사용(ADR-039). dev/prod 분리(ADR-047).
- 신규 결정은 ADR로 박는다(다음 신규 = ADR-054). 신규 native 의존성은 운영/ARM 빌드 영향을 먼저 평가한다.

## 2. 현재 완료 상태 (Sprint 6 진입 시점, 2026-06-29)

- **legal/ops 운영 표면(T-275~T-282)**: incident console, retention 실행, email suppression, DSR,
  content moderation, RBAC grant/revoke, user lifecycle, rate-limit/abuse — 머지 완료.
- **보안 1차(T-283)**: threat model / security review 정리.
- **scope gate(T-284 mobile)**: 문서화 완료. T-113/T-285 AI 관련 task는 2026-06-29 사용자 지시로 제거.
- **병행 트랙(claude)**: T-289/290(WS reconnect/conflict UX, #310), T-291(ETL run-failure sensor, #312),
  T-261~263(스마트 정렬 2-opt, #315, ADR-053), T-292(integrity pagination), T-264(category override, #316, ADR-052),
  T-267(Backup/Restore UI hot-swap, #319), T-287(Trip Day optimistic lock, #321).
- **Admin 보강(T-265)**: `/admin/notice-plans` 작성기, POI editor, 첨부 업로드, Admin API CRUD 완료.
- **Sprint 5/v0.2.0 게이트**: 대부분 완료, release/tag만 T-259로 분리.

## 3. 남은 Task Backlog (그룹별)

### A. MCP 외부 인터페이스

- **T-266** MCP 운영 실증 — MCP 서버(T-112)는 구현됨. Claude Code MCP client 등록 → `list_trips`/
  `search_features` 호출 성공 실증(E2E 시나리오 7) + 토큰 발급/회수 운영 확인.

### B. 한국 전용 geofencing (ADR-018)

- **T-268** 3중 안전망 — FastAPI `middleware/geofence.py`(구현됨, T-109/142/187) 위에 nginx geo +
  Cloudflare WAF 설정/문서 마감. KR 외 IP 451 + VPN 검증.

### C. 법무 / 컴플라이언스

- **T-269** LBS / 법무 4문서 / 동의 UX — `docs/legal/{terms-of-service,privacy-policy,lbs-terms,location-consent}.md`
  (변호사 검토 placeholder) + 동의 UX. PIPA/LBS 운영 표면은 T-275~282로 구현됨; 본 task는 문서/동의 흐름.

### D. 운영 / 성능 / 보안

- **T-270** 성능 / 부하 / 보안 점검 — `tests/load/*`, `tests/security/*`. T-283 보안 리뷰와 중복 영역은 조율.

### E. 범위 제거 / 미래 분리

- **T-113 / T-271 / T-272 / T-285 제거** — 2026-06-29 사용자 지시로 열린 backlog에서 제외했다.
  AI companion 연동이 다시 필요하면 신규 repo 신설이 아니라 기존 `kor-travel-concierge` API를
  활용하는 consumer/client 통합 task로 정의한다.

### F. 정합/잔여

- **T-286** Cross-track review gap closure — #238 리뷰 44 gap + PR #264 리뷰를 task/문서/검증으로 매핑.
- **T-291-etl-sql-tests** — ETL asset 원시 SQL 실행 테스트(etl Postgres fixture) + pii_retention audit
  retention 정책 분리(api/zod 파급). ETL 격리 트랙.

### G. 릴리즈

- **T-259** v0.2.0 release gate — Admin live full catalog + release notes/tag/GitHub Release. (선행 릴리즈)
- **T-273** v1.0.0 E2E / Live Gate — E2E 10 시나리오 + Odroid/N150 양쪽 smoke + backup 핫스왑 훈련 +
  geofence 검증.
- **T-274** v1.0.0 릴리즈 — tag + Release notes + journal/resume 마감.

## 4. 병행 / 충돌 회피 (tasks-rule §8)

- **codex 핫존**: `apps/api/app/api/v1/admin/*`, `app/services/*`(admin 백엔드). 같은 PR에서 동시 수정 회피.
- **claude 콜드존 우선**: 프론트(`apps/web` 비-admin), `packages/*`, `apps/etl`, 신규 모듈, 문서/법무.
- 신규 task 진입 전 `git fetch`, `tasks.md`/`resume.md`/`journal.md`/열린 PR 확인. 선점된 도메인은 조율.
- 공통 추적 문서(`tasks.md`/`resume.md`/`journal.md`/`decisions.md`)는 빠르게 머지해 충돌 창을 줄인다.
  ADR 번호는 claim 직전 `다음 ADR 번호`를 재확인한다.

## 5. DoD → Task 매핑 (요약)

| SPRINT-6 DoD                                                            | Task                                                                  |
| ----------------------------------------------------------------------- | --------------------------------------------------------------------- |
| optimize 엔드포인트 + 스마트 정렬 UI                                    | ✅ T-261~263 (ADR-053)                                                |
| category-mapping                                                        | ✅ T-264 (ADR-052)                                                    |
| PIPA incident/DSR/retention/suppression/moderation/RBAC/lifecycle/abuse | ✅ T-275~282                                                          |
| Day optimistic lock / conflict                                          | ✅ T-287                                                              |
| notice plan 작성기                                                      | ✅ T-265                                                              |
| MCP 외부 인터페이스 실증                                                | T-266                                                                 |
| Backup/Restore UI 핫스왑                                                | ✅ T-267                                                              |
| 한국 전용 geofencing                                                    | T-268                                                                 |
| 법무 4문서 / 동의 UX                                                    | T-269                                                                 |
| 성능/부하/보안 점검                                                     | T-270, T-283(1차)                                                     |
| Odroid+N150 운영 smoke                                                  | 제거(T-271)                                                           |
| AI companion 분리                                                       | 제거(T-113/T-272/T-285), 필요 시 기존 `kor-travel-concierge` API 활용 |
| cross-track gap closure                                                 | T-286                                                                 |
| ETL SQL 테스트 / audit retention                                        | T-291-etl-sql-tests                                                   |
| 릴리즈                                                                  | T-259 → T-273 → T-274                                                 |

## 6. ADR 현황 (Sprint 6 관련)

- **확정**: ADR-053(경로 최적화), ADR-052(category mapping).
- **참조**: ADR-018(geofencing), ADR-019(MCP), ADR-020(AI 분리), ADR-022(backup 핫스왑), ADR-023(하드웨어).
- **신규 후보**: 없음(현재). 신규 결정 발생 시 ADR-054부터 부여.
