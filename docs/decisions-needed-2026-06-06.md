# 결정 필요 항목 (2026-06-06 감사)

> 사용자(소유자) 결정이 필요한 항목만 모았다. 각 항목은 **배경 → 선택지 → 권고 →
> 결정 시 후속**. 결정되면 `docs/audit/2026-06-06-doc-impl-audit.md` §8의 ADR/Task로
> 반영하고 해당 문서를 갱신한다.
> 표기: ☐ 미결 / ☑ 결정됨(결정값과 날짜 기입).

---

## DEC-01 — krtour-map 통합 모델 (가장 중요) ☐
**배경**: TripMate는 ADR-026(2026-06-04)로 "krtour-map = OpenAPI HTTP 계약(포트
9011)"으로 전환 선언했으나, krtour-map 저장소는 9개월간 **in-process 함수
라이브러리**(ADR-003, "HTTP 없음")로 만들어졌고 HTTP는 인증 없는 debug-UI(8087,
`/features` bbox·`/features/{id}`만)뿐이다. TripMate 통합 문서가 참조하는
krtour 산출물(`krtour-map-admin` 패키지, `openapi.user.json`, 포트 9011,
`/tripmate/features/batch`)은 **실재하지 않는다**. (상세 `docs/krtour-map-requirements.md` §0)

**선택지**
- **(A) in-process 라이브러리로 복귀** — ADR-026 철회, TripMate가 `python-krtour-map`
  의존 + `AsyncKrtourMapClient` DI + feature DB engine 주입. krtour는 HTTP 불요,
  누락 client 메서드만 채움. 네트워크 hop 0(단일 노드 유리). 단 TripMate가 feature
  DB에 직접 연결(스키마 결합 ↑).
- **(B) krtour-map 운영급 HTTP 서비스 신설** — ADR-026 유지. krtour가 인증 있는 운영
  API(포트 9011/9012, 전 엔드포인트, OpenAPI+drift gate) 신설. TripMate는 httpx
  client 구현. 프로세스/배포 격리. 단 krtour에 큰 신규 표면 + 네트워크 hop.
- **(C) 하이브리드** — 우선 (A)로 v0.1.0 빠르게 출시, 후속 Sprint에 (B)로 승격.

**권고**: 사실관계상 krtour-map 전체 설계가 (A) 전제다. 단일 노드 성능·작업량 모두
(A)가 유리. 격리가 꼭 필요하면 (C). **(A) 또는 (C) 권고.** ※ 어느 쪽이든 §DEC와
무관하게 krtour는 누락 능력(near/batch/search 등)을 먼저 구현하면 됨.

**결정 시 후속**: ADR-027 작성, `docs/krtour-map-integration.md`·`features.md`·
SPRINT-4 재작성(T-148), C-01 client 구현 방향 확정.

---

## DEC-02 — 정규 `feature_id` 포맷 ☐
**배경**: 3곳이 다름 — TripMate 문서 `f_{bjd}_{kind[0]}_{sha1[:16]}`, krtour 실제
`{kind}:{hash}`(추정, 확인요망), TripMate **코드는 UUID**(버그).
**선택지**: (A) krtour `make_feature_id` 출력이 정본(권고 — feature 소유자가 krtour) /
(B) TripMate 문서 포맷으로 krtour가 맞춤.
**권고**: (A). krtour가 포맷을 명문화(ADR-028), TripMate 코드의 UUID 가정 제거(T-125).

---

## DEC-03 — `notice_plans` 명칭 충돌 ☐
**배경**: `app.notice_plans`가 "큐레이션 여행 템플릿"(slug/destination/notice_pois)과
"시스템 공지"(body/priority/audiences) 두 뜻으로 동명 정의 충돌(D-01/04).
**선택지**: (A) 큐레이션을 `app.curated_trip_plans`로 개명, `notice_plans`는 공지
전용 / (B) 반대로.
**권고**: (A). 사용자 대면 "추천 여행"은 `curated_trip_plans`, 운영 공지는
`notice_plans` 유지. ADR-029 + 스키마 정본화(T-137).

---

## DEC-04 — 지도 클러스터링 책임 ☐
**배경**: `/features/in-bounds`가 zoom별 시도/시군구/읍면동 클러스터를 기대하나 krtour
client는 클러스터링 안 함(개별 행만). TripMate `cluster_query.py`는 있으나 미연결.
**선택지**: (A) krtour DB 집계로 서버에서 클러스터(권고 — 단일 노드 대역폭·성능) /
(B) krtour는 raw, TripMate가 로컬 집계.
**권고**: (A). DEC-01과 함께 ADR-027 부속으로.

---

## DEC-05 — 사용자 feature 제안 (재적재와 완전 분리) ☑ (확정 2026-06-08)
**핵심 교정**: **재적재(feature-update-request)와 사용자 제안은 완전히 다른 작업이다.**
이 둘을 묶지 않는다.

**(A) 재적재 = krtour-map Admin 기능 — TripMate 사용자 제품과 무관**
- `POST /admin/feature-update-requests`(= scope 재적재/Dagster job)는 **krtour-map 운영자**가
  krtour-map admin(포트 9012 / admin 콘솔)에서 쓰는 기능이다.
- **TripMate 일반 사용자에게 노출되지 않으며, 사용자 제안 흐름에도 들어가지 않는다.**
  TripMate 제품은 재적재를 surface하지 않는다(필요 시 krtour admin이 직접 운영).

**(B) 사용자 제안 = TripMate가 소유, 승인 시 krtour "feature 추가 API"로 추가**
- **(레이어 1) 사용자 제안 큐 — TripMate `app`(user 도메인)**: `app.feature_suggestions`
  (requester_user_id, type[new_place|correction|closure], target_feature_id?, name, coord,
  categories[], note, status[pending|approved|rejected|added|duplicate], reviewed_by_admin_id?,
  krtour_ref?, created_at, resolved_at). 사용자 endpoint `POST /features/requests`(즉시 201) +
  `GET /features/requests/{id}`. per-user rate-limit + dedup. 감사 C-12의 미존재 테이블 실체화.
- **(레이어 2) TripMate Admin 검사/승인/거절 — admin 도메인**: `/admin/feature-requests`
  목록/검수 + `POST /admin/feature-requests/{id}/approve|reject` (RBAC admin/operator + audit).
  **승인 시 krtour-map의 feature 추가 API로 feature를 추가한다.** 재적재 호출과 무관.

**✅ krtour feature 추가 API 구현됨(krtour PR #317, 2026-06-09)**: `POST /admin/features`(create) /
`PATCH /admin/features/{id}` / `DELETE /admin/features/{id}` 신설(place/event). version 0(provider)/
1(user) 분리 + 재적재 보존. 응답에 `feature_id`/`request_id`/state. (계약 §
`docs/integrations/krtour-map-rest-api.md` §2.9, 요구사항 K-15.) → T-179 actionable.
**남은 하위 결정(연동 합의, krtour PR #317 코멘트로 질의 중)**:
- **review_mode**: krtour 기본 `require_review`인데 TripMate가 이미 Admin 검수 → 이중 검수 방지.
  krtour `immediate` / TripMate `create→approve` 2-step / 요청 단위 override 중 합의.
- idempotency_key 멱등, 출처 태깅, admin 인증(9012), closure(DELETE vs deactivate).

**근거**: 경계(검수/남용/PII는 TripMate user 도메인), 재적재(운영)와 제안(사용자)은 별개 도메인.

---

## DEC-06 — v0.1.0 출시 게이트 ☐
**배경**: v0.1.0 DoD가 krtour HTTP client + 라이브 feature read(T-066, 보류)에 묶임.
**선택지**: (A) snapshot-only로 v0.1.0 출시(라이브 feature는 v0.2.0) / (B) krtour
연동까지 v0.1.0 보류.
**권고**: DEC-01 결과에 종속. (A)면 지도에 캐시/snapshot만 — UX 제한. 사용자 우선순위
질문.

---

## DEC-07 — 외부 API 규약 정본 ☐
**배경**: envelope 4종, pagination 4종, 좌표 4종, datetime 2종, id 명명, 버전 prefix
(`/` vs `/v1`), 에러 taxonomy가 제각각(A-03/04/07/08/10/22 등).
**제안 정본**(승인/수정 요망):
- list = `{"data": [...], "meta": {...}}`(배열 직접), 단건 = `{"data": {...}}`
- 사용자 list 페이지네이션 = **cursor**; admin/S3 예외만 명문
- 좌표 = `{"longitude":..,"latitude":..}`(lng-first, 6자리)
- datetime = ISO8601 `+09:00`
- id 필드 = `<entity>_id`
- URL 버전 prefix = **`/v1` 노출**(라우터가 이미 `api/v1`) ← 또는 `/` 무prefix 중 택1
- 생성 성공 = 영속 리소스 생성 시 `201`, 그 외 `200`
**결정 시 후속**: ADR-030, `common.md`/`api-contract.md` 정본화 + per-domain 일괄정렬.

---

## DEC-08 — POI delete 정책 ☐
**배경**: pois.md "미정", admin.md "hard delete"로 충돌(A-15).
**선택지**: (A) soft delete(deleted_at) — 복구/공유 안정 / (B) hard delete.
**권고**: (A) soft. ADR-031.

---

## DEC-09 — `trip_day_pois.feature_id` nullable ☐
**배경**: 현재 NOT NULL → krtour에 없는 "자유 메모 장소"를 일정에 못 넣음(D-18).
**선택지**: (A) nullable + 사용자 좌표 경로 허용(권고 — 기본 계획 UX) / (B) 유지.
**권고**: (A). ADR-031 부속.

---

## DEC-10 — LBS 위치로그 보존 vs 해시체인 ☐
**배경**: 6개월 보존 DELETE가 `location_access_log` tamper-evident 해시체인을 깨뜨림.
정책 미결(D-12).
**선택지**: (A) archive 테이블로 이동 후 체인 연속 보장(권고) / (B) delete + rehash.
**권고**: (A). compliance/lbs-act.md 확정 + T-142 인접.

---

## 결정 기록란
| DEC | 결정 | 날짜 | 비고 |
|-----|------|------|------|
| DEC-01 | ☑ **(B) 운영급 HTTP 서비스** | 2026-06-06 | 사용자. ADR-027. krtour가 HTTP 신설 필요 |
| DEC-02 | ☑ krtour `make_feature_id` 정본(문자열) | 2026-06-06 | 권고 기본값 적용. ADR-028 |
| DEC-03 | ☑ 큐레이션→`curated_trip_plans` 분리 | 2026-06-06 | 사용자. ADR-029 |
| DEC-04 | ☑ 서버(krtour DB 집계) 클러스터링 | 2026-06-06 | 권고 기본값 적용. ADR-027 부속 |
| DEC-05 | ☑ **재적재(krtour admin, 비노출)와 사용자 제안 완전 분리**. 사용자 제안=TripMate→Admin 검사/승인→krtour feature 추가 API로 반영 | 2026-06-08 | 사용자 확정. feature 추가 API = **krtour PR #317로 구현됨(2026-06-09)** → T-179 actionable. review_mode 등 연동 합의 진행. §DEC-05 본문 |
| DEC-06 | ☑ **krtour 연동까지 대기**(snapshot 조기출시 안 함) | 2026-06-06 | 사용자. sprints/README v0.1.0 게이트 |
| DEC-07 | ☑ 제안 기본값 + `/v1` 노출 | 2026-06-06 | 사용자. ADR-030 |
| DEC-08 | ☑ POI **soft delete** | 2026-06-06 | 권고 기본값 적용. ADR-031(예정) |
| DEC-09 | ☑ `trip_day_pois.feature_id` **nullable** | 2026-06-06 | 권고 기본값 적용. ADR-031 부속(예정) |
| DEC-10 | ☑ 위치로그 **archive 테이블** 이동 + 체인 연속 | 2026-06-06 | 권고 기본값 적용. T-142 인접 |

> DEC-02/04/05/08/09/10은 저위험 권고 기본값으로 채택했다. DEC-05(요청 큐 소유권)와
> DEC-08~10은 구현 진입(T-137/T-138/T-142) 시 이견이 있으면 재론 가능.
