# kor-travel-map 발 cross-repo 검토 결정 반영 — Pinvi 측 (2026-06-10)

> **출처**: kor-travel-map repo에서 수행한 3-시스템(kor-travel-map · Pinvi ·
> kor-travel-concierge) 완성도·정합성 교차 검토. 전체 보고서는 kor-travel-map
> `docs/reports/service-completeness-review-2026-06-10.md` + 결정 이력
> `decisions-needed-2026-06-10.md`(D-01~13 전 항목 종결) + 액션 플랜
> `consistency-uplift-plan-2026-06-10.md`. kor-travel-map 측 정본 반영 = ADR-050~052 +
> tasks T-217a~g (PR #334).
> **기준 커밋**: kor_travel_map `origin/main` `0e45bd7` · Pinvi `origin/main` `4a10a5b` ·
> kor-travel-concierge `origin/main` `a443ca0`.

## 1. Pinvi에 영향 있는 확정 사항

| 결정 | 내용 | Pinvi 영향 |
|---|---|---|
| kor_travel_map T-216a~g 머지 (`0e45bd7`) | RFC7807 problem+json · envelope payload/meta 분리(`meta.page.next_cursor`) · batch `data.found` · in-bounds `max_items` · `meta.cluster` | **T-181 잔여 lockstep 대기 해제 — 즉시 실행 가능.** client의 `items` 파싱은 현재 전 결과 silent-missing |
| ADR-051 (kor_travel_map) | 사용자 feature 제안 반영의 전송 구간 = **기존 `/v1/admin/features*` change API(#317)** 공식 승인. 별도 suggestions API 안 만듦 | DEC-05·T-177/T-179/T-180 설계 그대로 진행. 잔여 합의 5건(§7)은 kor_travel_map T-217c가 확정·회신 |
| D-11 | 출처 태깅은 **익명** — Pinvi 불투명 참조 ID(suggestion_id)만, kor_travel_map 개인정보 비저장 | T-179 승인 호출 페이로드 설계 기준 |
| D-12 (kor_travel_map ADR-050) | reject/tombstone/deactivate로 **inactive된 feature는 batch `found`에 status와 함께 노출**(`missing` 아님) | snapshot fallback과 별개로 "철회/폐업됨" 표시 분기 (T-175/T-178) |
| D-05 (kor_travel_map ADR-050) | YouTube(kor-travel-concierge) 발 feature는 **검수 통과분만** kor_travel_map에 적재됨 | Pinvi 도달분은 전부 검수 통과 — UI는 출처 표시에 집중 |
| D-06 | Pinvi admin 표면: `/admin/features` 편집은 read-only+릴레이로 축소, `/admin/seed`·`/admin/reset` placeholder 제거, `/admin/category-mapping`은 `GET /v1/categories` 뷰로 대체. **`/admin/etl`은 유지** — KASI류 Pinvi 고유 ETL 잡 관제(D-13 확인: kor_travel_map 적재와 중복 없음) | admin IA 정리 task 후보 |
| D-09 | v0.1.0 게이트 "연동 후 출시"로 재평가 | DEC-06 재평가 — 외부 블로커 없음, 남은 건 T-181 잔여 + T-172~176 배선 |

## 2. 이번 검토로 갱신된 Pinvi 문서

- `docs/kor-travel-map-integration.md` — 2026-06-06 "kor_travel_map HTTP 미존재" 경고 블록을 현재
  상태(✅ `/v1` 완비)로 교체, 전 경로 `/v1` 정정, batch `found`, `/debug/health|version`
  제거 반영. (그 실측은 stale 본 체크아웃(b775c74) 오판 — **형제 repo 실측은 fetch 후
  origin/main 기준** 교훈.)
- `docs/integrations/kor-travel-map-rest-api.md` — 0e45bd7 재대조 노트, §7 잔여 2건
  (batch `found`·`meta.cluster`) **kor_travel_map 수용 완료** 반영, T-181 대기 해제, batch
  경로/응답 키 갱신.

## 3. 신규 발견 오류 (코드/설정 — 후속 수정 대상, 문서만 선반영)

1. **admin base 포트 오인**: `PINVI_KOR_TRAVEL_MAP_ADMIN_BASE_URL` 기본 9012로 가정하나
   **9012는 kor_travel_map admin UI(Next.js)**, admin **API는 9011 `/v1/admin/*`**. T-180
   admin client는 9011 base로 설계할 것 (`config.py` 기본값/의미 재정의).
2. batch 파싱 `data.get("items")` (`apps/api/app/clients/kor_travel_map.py`) — 정본은
   `found` (T-181 잔여).
3. in-bounds `limit` 파라미터 전송 — 정본은 `max_items`, 현재 silent no-op (T-181 잔여).

## 4. 신규 액션 후보 (기존 task에 없는 것)

| 후보 | 내용 | 비고 |
|---|---|---|
| 출처 배지 UX | YouTube 발 feature(provider `kor-travel-concierge-youtube`, marker P-13)에 출처 배지 + 영상 링크/타임스탬프 카드 | kor_travel_map T-217f(evidence 노출 형태 확정) 후속 |
| kind 화이트리스트 | kor_travel_map 7-kind 중 v0.1 표시 kind와 카드 형태(event 기간/price 유가/notice/route) 기획 명시 | |
| 공유 뷰 feature 권한 | `/shared/[tripId]/[token]` 비로그인 흐름의 feature proxy 인가 경로 점검 | |
| 지도 성능 정책 | in-bounds 디바운스 + TanStack Query 캐시 + zoom별 `cluster_unit` 기준 명시 | |
| inactive 표시 분기 | D-12 — `found`+status(inactive)를 "철회/폐업됨"으로 표시, `missing`(삭제/없음)과 구분 | T-175/T-178에 합류 가능 |

## 5. kor_travel_map 측에서 회신 예정 (T-217c — §7 합의 5건)

review_mode(이중 검수 여부) / idempotency_key 멱등 / 출처 태깅 필드(suggestion_id,
익명) / admin 인증 방식(9011 `/v1/admin/*`) / closure(`DELETE` vs `deactivate`) —
확정 시 `docs/integrations/kor-travel-map-rest-api.md` §7 갱신.
