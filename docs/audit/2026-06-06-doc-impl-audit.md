# 문서·구현 정합성 감사 (2026-06-06)

> **목적**: Sprint 1~4 진행 중 계획이 자주 바뀌고 Task 단위로 여러 AI 에이전트가
> 작업하면서 누적된 **모순·불일치·누락·미흡**을 전수 점검해 한 곳에 모은다.
> 중점: ① 실제로 동작 가능한가 ② 목적에 맞게 최적화됐나 ③ **외부 노출 API가
> 일관·완결한가** ④ 빠진 기능은 없나.
> **방법**: 문서 전체 + `apps/api`·`apps/web`·`apps/etl` 코드 + `python-krtour-map`
> 저장소(HEAD `b775c74`)를 2026-06-06에 대조.
> **병합 안내**: 각 발견에 **제안 Task(T-)** 또는 **제안 ADR(ADR-)** 를 붙였다.
> 이 문서의 §8 매핑표를 보고 `docs/tasks.md` / `docs/decisions.md`로 lift한다.
> 다음 빈 번호: **Task = T-123**, **ADR = ADR-027**(이 저장소 namespace).
> **결정 필요 항목**은 `docs/decisions-needed-2026-06-06.md`로 분리(DEC-01~).

발견 ID 규칙(증거 추적용): `P-`계획/프로세스, `A-`외부 API, `C-`코드 vs 문서,
`D-`기능/도메인. 심각도 high/med/low.

---

## 0. 요약 — 가장 중요한 5가지

1. **[치명] krtour-map 통합 모델이 두 저장소에서 정반대다.** TripMate는 HTTP
   계약(ADR-026, 포트 9011, `/features/in-bounds`·`/tripmate/features/batch`)을
   믿지만, krtour-map은 **in-process 함수 라이브러리**(ADR-003, "HTTP 없음")로
   만들어졌고 HTTP는 인증 없는 debug-UI(포트 8087, `/features` bbox·`/features/{id}`
   뿐)만 존재한다. TripMate 통합 문서가 참조하는 krtour-map 산출물(`krtour-map-admin`
   패키지, `openapi.user.json`, 포트 9011)은 **실재하지 않는다**. → **DEC-01**.
   상세·요구사항은 `docs/krtour-map-requirements.md`.
2. **[높음] feature read 경로 전체가 미연결.** `apps/api/.../etl_bridge/krtour_map.py`
   client 싱글톤이 항상 `None`(`TODO(sprint-4-PR-B2)`) → `/features/*` 전부 `503`.
   `apps/api/app/clients/krtour_map.py`(문서가 가정한 HTTP client)는 존재하지 않는다
   (C-01). v0.1.0 출시 게이트가 여기에 묶여 있다(P-12 → **DEC-06**).
3. **[높음] 외부 API 표면이 일관되지 않다.** list envelope 4종(`data`배열 /
   `data.items` / `data.<plural>` / `data.rows`), 페이지네이션 4종(cursor / page+limit
   / limit+offset / continuation token), 좌표 표현 4종, datetime offset 2종(`+09:00`
   vs `Z`)이 혼재(A-03/04/07/08). → **DEC-07**(규약 정본 1개 확정 후 일괄 정정).
4. **[높음] 핵심 도메인 테이블·기능이 데이터 모델에 빠졌거나 충돌.** `notice_plans`가
   "큐레이션 여행 템플릿"과 "시스템 공지" 두 뜻으로 동명 충돌(D-01 → **DEC-03**);
   `security_incidents`·`notice_pois`·`plan_poi_attachments`·`feature_requests` 등
   참조되지만 스키마에 없음(D-03/04, C-12); PIPA가 요구하는 `users` 컬럼
   (`password_hash`·`nickname`·`gender`·`email_status` 등)이 스키마에 없음(D-02/09).
5. **[중] 외부 노출 API에 빠진 기능 다수.** WebSocket 실시간 계층 전무(C-03),
   `/regions/*`·`/geo/*`·`/public/*` 미구현(C-02/04), trip 하위 리소스(일정/멤버
   초대/공유 뷰/첨부/복제) 미구현(C-06), MCP 토큰 발급 엔드포인트 미명세(A-12),
   여행 검색·내보내기(PDF/GPX)·동반자 초대 흐름 부재(D-16/17/06).

---

## 1. 결정 필요 (요약 — 본문은 `docs/decisions-needed-2026-06-06.md`)

| DEC | 주제 | 막는 것 | 제안 ADR |
|-----|------|---------|----------|
| DEC-01 | krtour-map 통합 모델: in-process vs 운영 HTTP | feature 전 기능 | ADR-027 |
| DEC-02 | 정규 `feature_id` 포맷(3곳 불일치) | feature read 전부 | ADR-028 |
| DEC-03 | `notice_plans` 명칭 충돌 해소(큐레이션 vs 공지) | notice/공지 도메인 | ADR-029 |
| DEC-04 | 지도 클러스터링 책임(krtour DB 집계 vs TripMate 로컬) | in-bounds 성능 | ADR-027 부속 |
| DEC-05 | feature 갱신요청 큐 소유권(krtour vs TripMate app) | feature request | ADR-027 부속 |
| DEC-06 | v0.1.0 출시 게이트: snapshot-only 출시 vs krtour 연동 대기 | 릴리즈 | — |
| DEC-07 | 외부 API 규약 정본(envelope/pagination/coord/datetime/버전 prefix) | API 전반 | ADR-030 |
| DEC-08 | POI delete 정책(soft vs hard) | POI/Admin | ADR-031 |
| DEC-09 | `trip_day_pois.feature_id` nullable(자유 메모 POI 허용) | 계획 UX | ADR-031 부속 |

---

## 2. krtour-map 경계 (가장 큰 결함)

→ 전용 문서 `docs/krtour-map-requirements.md`로 분리(krtour-map 에이전트용).
여기서는 TripMate 측 정정 항목만:

| ID | 심각도 | 문제 | 제안 |
|----|--------|------|------|
| C-01 | high | feature HTTP client(`clients/krtour_map.py`) 미존재, etl_bridge stub만 → `/features/*` 503 | T-066 구현(DEC-01 후) |
| A-05/D-07 | high | `docs/krtour-map-integration.md`·`features.md`가 실재하지 않는 krtour 산출물(포트 9011, `openapi.user.json`, `/tripmate/features/batch`) 참조 | DEC-01 확정 후 통합 문서 재작성 |
| C-07 | high | `/features/in-bounds` 파라미터(`bbox=` 단일 vs `sw_/ne_` 4개)·응답(`{features,clusters}` vs `{cluster_unit,items}`) 코드↔문서 불일치 | T-124 |
| C-09 | med | 코드가 `feature_id`를 UUID로 취급(`features.py`, `trip_view_builder.py:90` `uuid.UUID(...)`) — 문자열이어야 함 | T-125(DEC-02) |
| C-10/11/12 | med | FeatureSummary/weather/feature-request 필드명 코드↔문서 불일치 | T-124 |

---

## 3. 외부 노출 API 일관성·완결성

### 3.1 일관성 (규약 정본 필요 — DEC-07)
| ID | 심각도 | 문제 | 정본 제안 |
|----|--------|------|-----------|
| A-03 | high | list envelope 4종 혼재(`data`배열/`data.items`/`data.<plural>`/`data.rows`) | `data`=배열 + `meta` 하나로 |
| A-04 | high | 페이지네이션 4종(cursor/page+limit/limit+offset/continuation) | 사용자 list=cursor, 예외만 명시 |
| A-07 | med | 좌표 표현 4종(`{longitude,latitude}`/`[lng,lat]`/평면/GeoJSON), WS는 `{lat,lng}` lat-first | `{longitude,latitude}` 객체, lng-first |
| A-08 | med | datetime `+09:00` vs `Z`(admin) 혼재 | `+09:00` 통일(또는 admin 예외 명문) |
| A-09 | med | 현재 사용자 객체 `data`(flat) vs `data.user`(nested) | `data.user`로 통일 |
| A-16/17 | med | id 필드 `<entity>_id` vs bare `id`; POI 라벨 `title_snapshot`/`name`/`label`/`memo` 4종 | 명칭 표준화 |
| A-18/19 | med | admin 쿼리 문법 2종, `lng,lat,radius_m` vs `longitude,latitude,radius_meters` | 파라미터명 통일 |
| A-10 | med | API 버전 prefix `/` vs `/v1` 미확정(README/common/api-contract 3곳 불일치) | DEC-07에 포함 |
| A-22/24/11 | med | `410 TRIPS_OWNED`·`SORT_ORDER_CONFLICT`·`DB_UNAVAILABLE` 등 표준 에러표 밖 코드 | 에러 taxonomy 정비 |

### 3.2 완결성 / 빠진 기능
| ID | 심각도 | 문제 | 제안 Task |
|----|--------|------|-----------|
| A-01/C-16 | high | POI 생성 경로 이중(`POST /trips/{id}/pois` vs `/trips/{id}/days/{day_index}/items`) — 두 API 문서가 서로 다름 | T-126(경로 1개로) |
| A-02/C-? | high | MCP 문서 2종이 상호 모순(mcp-server.md=읽기전용 5툴 vs mcp-tools.md=DB쓰기 admin툴) | T-127(ADR-019 정본화) |
| A-06 | high | MCP `list_trips` status enum(`draft/active/archived`)이 실제 trip status(`draft/planned/in_progress/completed/archived`)와 불일치 | T-127 |
| C-03 | high | WebSocket 실시간 계층 전무(`ws.py`/broker 없음) — trips/pois 문서의 broadcast 약속 미구현 | T-128(Sprint 5) |
| A-12 | med | MCP 토큰 발급/회수 엔드포인트(`/users/me/mcp-tokens`,`/admin/mcp-tokens`) 미명세 | T-127 |
| A-13/C-02 | med | `/geo/*`(ADR-025) 및 `/regions/*` 엔드포인트 미명세·미구현 | T-129 |
| A-14 | low | README index에 `GET /search`·`/health/external` 누락 | T-123(문서) |
| A-15/C-? | med | POI delete soft vs hard 미결(pois.md "미정" vs admin.md "hard") | DEC-08 |
| A-25/29 | low | avatar 업로드 2모드 미결, 201 vs 200 규칙 부재 | DEC-07 부속 |

---

## 4. 코드 vs 문서 (동작 가능성)

| ID | 심각도 | 문제 | 제안 |
|----|--------|------|------|
| C-04 | high | `/public/*`(해변/축제) 라우터·서비스 미존재 | T-130(krtour 연동 후) |
| C-05 | high | `GET /trips/{id}`가 trip 메타만 반환. `trip_view_builder.build_trip_view`는 완성됐으나 **어떤 라우터도 호출 안 함**(dead code) | T-131(builder 연결) |
| C-06 | high | trip 하위 리소스(DELETE/copy/days/day-items/members/shared view/attachments/optimize) 대부분 미구현 | T-132(분할) |
| C-08 | high | Admin(T-050/T-104 "완료")이 상당수 placeholder(`/admin/{trips,pois,features,etl,seed,reset,...}` 페이지가 `Placeholder.tsx`; priority-3 엔드포인트 미구현) | P-05 정정 + T-133 |
| C-14 | med | `POST /auth/refresh` 미구현 + refresh 토큰이 `user_sessions`에 미저장 → 문서상 refresh 흐름 불가 | T-134 |
| C-15 | med | `GET /trips` 페이지네이션 코드(`limit`만) vs 문서(`bucket`+`cursor`) | T-124 |
| C-17 | med | `GET /admin/audit/location`(CPO) 미구현 — 미들웨어는 쓰는데 읽는 라우터 없음 | T-133 |
| C-18 | med | POI 응답 `rise_set` 필드 미노출(데이터·ETL은 있으나 schema/응답에 없음) | T-135 |
| C-13 | med | 통합 `GET /search`(features+addresses+my_pois) 미구현(코드는 features만) | T-129 |
| C-19 | med | `services/cluster_query.py` 어디서도 호출 안 함(테스트만) | DEC-04 후 연결/삭제 |
| C-20 | low | OAuth `GET /auth/oauth/providers`·`DELETE /auth/oauth/google` 구현됐으나 미문서화 | T-123(문서) |
| C-21 | low | share-link 호스트 하드코딩(`app.tripmate.local`), zoom 하한 코드(5) vs 문서(7) | T-123 |
| C-22 | med | Resend webhook 서명 검증 no-op(미인증 입력으로 `email_queue` 변경) | T-136(보안) |

> **동작하는 것(오탐 방지)**: auth(register/verify/login/logout/me/password-reset),
> Google OAuth(start/callback/link/unlink/providers), consents, trips
> create/list/get/patch + share token, POI CRUD/reorder, notice-plans(list/get/copy),
> storage presigned, admin(users/audit/emails/backup), KASI ETL(T-067)는 **실구현**.
> 가장 큰 단일 결함은 C-01(krtour 연동)이고 C-04/05/09~13이 거기에 연쇄된다.

---

## 5. 기능/도메인 완결성·최적화

| ID | 심각도 | 문제 | 제안 |
|----|--------|------|------|
| D-01 | high | `app.notice_plans` 두 정의 충돌(큐레이션 템플릿 vs 시스템 공지) | DEC-03 → T-137 |
| D-02 | high | PIPA/auth가 쓰는 `users` 컬럼(`password_hash,nickname,gender,birth_year_month,residence_sigungu_code`) 스키마에 없음 | T-138 |
| D-03 | high | `app.security_incidents` 테이블 미정의(침해통지/`/admin/incidents`가 참조) | T-138 |
| D-04 | high | 큐레이션 plan 테이블(`notice_pois`,`plan_poi_attachments`) 정본 스키마에 없음; 첨부 모델 2종(단일 4-target vs polymorphic) 공존 | DEC-03 → T-137 |
| D-05 | high | 실시간 협업 백엔드(presence/충돌해소) 설계 문서 없음. `trip_day_pois`는 단일 작성자 optimistic lock뿐 | T-128(Sprint 5 설계) |
| D-06 | high | `trip_companions`·`trip_invite` 템플릿 있으나 **초대 흐름 엔드포인트 없음**; `share_links.visibility='comment'`인데 댓글 모델/ API 없음 | T-132/T-139 |
| D-08 | med | krtour 계약에 없는 소비처 호출(`/features/nearby`,`/{id}/weather`,`/regions/*`,`/features/requests`) | krtour-requirements K-3/K-6/K-8 |
| D-10 | med | `notice_pois.budget`가 복사 대상 `trip_day_pois`에 컬럼 없음 → 예산 silently drop, 여행 예산 기능 자체 부재 | T-140 |
| D-11 | med | trip↔지역 구조적 연결 없음(`region_hint` 자유텍스트뿐) → 텔레그램 brief의 지역 날씨/주유 질의 불가 | T-141 |
| D-12 | med | LBS 6개월 보존 DELETE가 `location_access_log` 해시체인 깨뜨림 — 보존/체인연속 정책 미결 | DEC-10 |
| D-13 | med | korea-only 3단 geofence admin 우회가 토큰 `roles` claim 의존인데 토큰엔 subject만(DB RBAC) → 출장 admin이 451 | T-142 |
| D-15/21 | med | social-login(Google-only) vs map-marker-design(3버튼); frontend.md가 ADR-015로 삭제된 Kakao 어댑터 잔존 | T-143(문서정정) |
| D-16/17 | med | 여행/장소 검색 UX 문서 없음; 여행 내보내기(PDF/GPX/print) 설계 없음(기록·공유 제품인데) | T-144 |
| D-18 | med | `trip_day_pois.feature_id` NOT NULL → krtour에 없는 자유 메모 POI 불가 | DEC-09 |
| D-19 | med | backup 핫스왑이 2× DB(2× 디스크/RAM) 전제 — Odroid M1S에서 비현실적 | T-145(동일호스트 schema-swap 확정) |
| D-20/26 | med | location-audit 동기 체인해시 + trip view마다 krtour batch+join(캐시 없음) — 단일 노드 hotspot | T-146(async outbox + feature 캐시) |
| D-22 | med | kraddr-geo v2(ADR-025) integration 문서·CLAUDE 의존성 누락 | T-143 (※ `kraddr-geo.md`는 이미 존재 — CLAUDE §4 stack에만 추가) |
| D-24 | low | korea-only 3중 geofence(WAF+nginx GeoIP2+app)가 단일 Cloudflare tunnel 뒤에선 과잉 | T-142 |
| D-23/D-25 | low | rise/set 재계산 정책 미결; gemini.md의 `UNIQUE ... WHERE` 인라인은 invalid PG 문법 | T-147(문서정정) |

---

## 6. 계획/프로세스 정합성

| ID | 심각도 | 문제 | 제안 |
|----|--------|------|------|
| P-01 | high | SPRINT-4 backend가 in-DB spatial/`feature` schema join 전제 — ADR-026(HTTP, feature schema 직접접근 금지)와 충돌 | T-148(DEC-01 후 SPRINT-4 재작성) |
| P-03 | high | Gemini가 README/AGENTS/SKILL의 현재 책임 목록에 남음 — ADR-020(별 repo 분리)·T-107 deferred와 충돌 | T-149(문서정정) |
| P-04 | high | sprint 상태 drift: README는 Sprint4~6 "proposed"인데 PR #15/#16 merged, T-109/110/115 done; sprint 헤더 status가 머지 현실과 불일치 | T-150 |
| P-05 | med | `tasks.md` "보류"에 `[x]` 완료 항목(T-100~104,107) 혼재 — 보류와 완료 동시 불가 | T-150 |
| P-06 | med | T-111이 `tasks.md`에 2번 정의 | T-150 |
| P-07/08 | med | auth-token/RBAC/audit-chain ADR 미기록; SPRINT 문서 곳곳 `ADR-NNN` placeholder 미할당 | T-151(ADR 백필) |
| P-02/14/19 | med | SPRINT-1 ADR 참조 번호 오류(ADR-010/011/016↔실제); ADR-011 지도항목 supersede 표기 누락 | T-150/T-151 |
| P-09/15/20 | med | resume.md "박힌 ADR"가 016에서 끊김(017~026 누락); 헤드라인 상태 구식; 죽은 ADR-028 후보 | T-150 |
| P-10/13/17/18/21 | low | `release-plan.md` dangling link; 머지표 PR#15/16 누락; `python-kraddr-map` 오타; agent-guide 잔여 bullet/구식 trailer; MCP 토큰 경로 3곳 불일치 | T-150 |
| P-11 | low | SPRINT-5 Dagster asset 수(4 vs 5~6) 불일치 | T-150 |
| P-12 | med | v0.1.0 게이트가 보류 항목(T-066, krtour client)에 의존 | DEC-06 |

---

## 7. 외부 노출 API — 종합 평가

- **일관성**: 현재 **낮음**. envelope/pagination/coord/datetime/id/파라미터명/버전
  prefix가 도메인마다 제각각(§3.1). 정본 규약 1개(DEC-07 → ADR-030)를 박고
  `common.md`·`api-contract.md`를 단일 출처로 만든 뒤 per-domain 문서를 일괄 정렬해야
  한다.
- **완결성**: feature/지도(krtour 의존), 실시간, regions/geo/public, trip 하위 리소스,
  MCP 토큰, 검색/내보내기/동반자 초대가 **미완**. CRUD 짝 누락(생성만 있고 수정/삭제
  없음)이 trips·admin에 다수.
- **빠진 기능(제품 목적 대비)**: 여행 **검색**, 여행 **내보내기/공유 렌더**, **동반자
  초대/댓글**, **예산**, **실시간 협업** — "계획·기록·공유" 제품의 핵심인데 설계가
  비었거나 흩어져 있다(D-05/06/10/16/17).

---

## 8. 병합 매핑표 (→ `docs/tasks.md` / `docs/decisions.md`로 lift)

### 8.1 제안 Task (그대로 `tasks.md`에 붙일 수 있는 형식)
> 번호는 기존 최고치(T-122) 다음부터. 실제 병합 시 충돌하면 재배정.

```
- [ ] T-123 — 문서 정합 일괄 정정(README index/머지표/오타/dangling link/OAuth·share 문서화)  (A-14,C-20,C-21,P-10,P-13,P-17,P-18)
- [ ] T-124 — /features/* 코드↔문서 계약 정렬(in-bounds 파라미터·응답, trips 페이지네이션, 필드명)  (C-07,C-10,C-11,C-15)
- [ ] T-125 — feature_id 문자열化(코드의 UUID 가정 제거)  (C-09, DEC-02 후)
- [ ] T-126 — POI 생성 경로 단일화(/trips/{id}/pois 정본, days/items 정정)  (A-01,C-16)
- [ ] T-127 — MCP 외부 인터페이스 정본화(mcp-server.md 권위, mcp-tools 재범위, status enum, 토큰 엔드포인트)  (A-02,A-06,A-12)
- [ ] T-128 — 실시간 협업 백엔드 설계 + WS 계층(presence/충돌해소) (Sprint 5)  (C-03,D-05)
- [ ] T-129 — /search 통합 + /geo/*·/regions/* 명세·구현  (A-13,C-02,C-13)
- [ ] T-130 — /public/* 구현 (krtour 연동 후)  (C-04)
- [ ] T-131 — GET /trips/{id}에 build_trip_view 연결  (C-05)
- [ ] T-132 — trip 하위 리소스(days/day-items/members/shared/attachments/copy/optimize) 구현 분할  (C-06,D-06)
- [ ] T-133 — Admin priority-3 엔드포인트·페이지 실구현(or 상태 강등)  (C-08,C-17)
- [ ] T-134 — POST /auth/refresh + user_sessions 영속화  (C-14)
- [ ] T-135 — POI 응답 rise_set 노출  (C-18)
- [ ] T-136 — Resend webhook Svix 서명 검증  (C-22)
- [ ] T-137 — notice/curated-plan 스키마 정본화(DEC-03 후)  (D-01,D-04)
- [ ] T-138 — users 누락 컬럼 + security_incidents 테이블 추가  (D-02,D-03,D-09)
- [ ] T-139 — 동반자 초대 흐름 + 댓글 모델/visibility 정리  (D-06)
- [ ] T-140 — 여행 예산(budget/currency) 도메인 + 복사 흐름  (D-10)
- [ ] T-141 — trip↔지역 구조적 연결(POI 좌표 유도 or region code)  (D-11)
- [ ] T-142 — geofence admin 우회 RBAC 소스 정정 + nginx 티어 정리  (D-13,D-24)
- [ ] T-143 — 지도/소셜 문서 정정(Kakao 어댑터 제거, Google-only, kraddr-geo stack 추가)  (D-15,D-21,D-22)
- [ ] T-144 — 여행/장소 검색 UX + 내보내기(PDF/GPX/print) 설계  (D-16,D-17)
- [ ] T-145 — backup 핫스왑 동일호스트 schema-swap 확정(2×DB 폐기)  (D-19)
- [ ] T-146 — location-audit async outbox + feature 캐시(N+1 제거)  (D-20,D-26)
- [ ] T-147 — 잔여 문서 정정(rise/set 정책, gemini.md partial unique index 문법)  (D-23,D-25)
- [ ] T-148 — SPRINT-4 backend 재작성(HTTP 경계 반영)  (P-01, DEC-01 후)
- [ ] T-149 — Gemini 책임 목록 정정(README/AGENTS/SKILL)  (P-03)
- [ ] T-150 — 계획/추적 문서 정합화(sprint status/보류·완료/중복 T-111/ADR refs/resume)  (P-04~21)
- [ ] T-151 — 미기록 ADR 백필(auth-token/RBAC/audit-chain) + placeholder 번호 할당  (P-07,P-08)
```

### 8.2 제안 ADR (→ `docs/decisions.md`, 다음 번호 ADR-027~)
```
- ADR-027 — krtour-map 통합 모델 확정(in-process vs 운영 HTTP) + 클러스터링/요청큐 소유권  (DEC-01/04/05)
- ADR-028 — 정규 feature_id 포맷  (DEC-02)
- ADR-029 — notice_plans 명칭 충돌 해소(curated_trip_plans 분리)  (DEC-03)
- ADR-030 — 외부 API 규약 정본(envelope/pagination/coord/datetime/버전 prefix/에러 taxonomy)  (DEC-07)
- ADR-031 — POI delete 정책 + feature_id nullable(자유 메모 POI)  (DEC-08/09)
```

### 8.3 결정 필요(별도 문서)
→ `docs/decisions-needed-2026-06-06.md` (DEC-01 ~ DEC-10). 사용자 결정 후 위
ADR/Task에 반영.

---

## 9. 부록 — 증거 ID ↔ 원천
P-* = 계획/프로세스 감사, A-* = 외부 API 감사, C-* = 코드 vs 문서 감사,
D-* = 기능/도메인 감사. 각 발견의 file:line은 감사 당시 본문 기준이며 병합 시
재확인한다. krtour-map 대조는 `python-krtour-map` HEAD `b775c74` 기준.
