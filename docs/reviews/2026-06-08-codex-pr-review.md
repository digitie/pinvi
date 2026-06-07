# Codex PR 사후 리뷰 종합 — 2라운드 (2026-06-08)

> **대상**: Codex가 올린 머지 완료 PR **11건** — #73–#83.
> 대부분 직전 리뷰(2026-06-07, `docs/reviews/2026-06-07-codex-pr-review.md`)에서 도출한
> **[높음] 후속 T-154~T-161**과 감사 항목(T-137/T-126/T-127)을 구현한 것이라, 각 PR이
> 해당 결함을 **실제로 닫았는지**를 1차 검증 목표로 삼았다.
> **각 PR 코멘트**: 해당 PR에 "리뷰 결과 (사후 리뷰)" 게시.

---

## 0. 총평 — 수렴(convergence) 확인

- **직전 라운드의 [높음] 9건이 모두 코드로 해소됐다.** 보안 4건(resend/access-reason/reset/geofence),
  가용성 2건(WS), 계약·무결성 2건(money/audit-atomic), 문서 1건(anchor) — 전부 회귀 테스트
  동반 수정. **이번 라운드엔 신규 [높음]/차단 이슈 0건.**
- 남은 것은 **잔존 [중간]/[낮음]** — 대개 "방어 한 겹 더"·"테스트 가드"·"문서 표기" 수준.
  단, 운영 오설정에 의존하는 **fail-open 잔존 2건**(#74 env 기본값, #77 secret 미주입
  outage)과 **동시성 race 2건**(#76 refresh 회전, #80 hash-chain head)은 보안/무결성
  관점에서 우선 닫는 게 좋다.

### 직전 [높음] → 이번 검증 결과
| 후속 | PR | 결과 |
|------|----|------|
| T-154 resend C-22 | #74 | ✅ fail-closed + base64 둘 다 수정 (잔존: env 기본 fail-open 中) |
| T-155 access reason PII | #75 | ✅ 완전 해소 (header→reject query, URL 미포함 e2e) |
| T-156 reset 세션 폐기 | #76 | ✅ refresh 전부 폐기 (잔존: access 15분 창·refresh race 中) |
| T-157 geofence origin | #77 | ✅ Cloudflare 발신 HMAC 검증 (잔존: outage 가드·IP/mTLS 中) |
| T-158 WS guards | #78 | ✅ rate limit·cursor·backpressure·cap 4종 (잔존: grace 슬롯·coupling 中) |
| T-159 money zod | #79 | ✅ 응답 string 정규식 (잔존: admin union·schema 테스트 中) |
| T-160 audit atomic | #80 | ✅ 6개 호출처 단일 트랜잭션 (잔존: hash-chain head fork 中) |
| T-161 search anchor | #82 | ✅ 완전 해소 (TODO 없음) |
| T-137 curated plans | #73 | ✅ 안전 rename 마이그레이션 (잔존: storage 필드 alias 中) |
| T-126 POI route 정본 | #81 | ✅ 단일 경로 + 코드 일치 (잔존: §5.1 중복 文 低) |
| T-127 MCP 정본 | #83 | ✅ A-02/06/12/20 정합 (잔존: list_trips parity 中) |

---

## 1. 긴급성순 통합 TODO (잔존)

### 🟡 중간 (보안·무결성·가용성 잔존)
1. **[#74] resend 운영 fail-open 잔존** — `_allows_unsigned_resend_webhook`가 환경 문자열
   게이트인데 `tripmate_environment` 기본이 `"development"` → 운영이 명시적으로 덮어쓰지
   않으면 무서명 통과. allow-list(opt-out)→opt-in 플래그 또는 prod secret 강제로 반전.
2. **[#76] reset 후 access JWT(15분) 미무효화** — refresh는 끊겼지만 탈취 access는 TTL 동안
   생존. token version/jti denylist 또는 TTL 단축.
3. **[#76] refresh 회전 race** — `refresh_user_session`이 row lock 없이 select→revoke→insert
   → 동시 동일 token 이중 회전 TOCTOU. `with_for_update()`/조건부 `UPDATE` rowcount.
4. **[#77] geofence outage 풋건** — `enabled && block_unknown && !secret` 시 전 트래픽 451
   (fail-closed지만 silent outage). startup 검증/경고 추가.
5. **[#77] geofence 방어 단일화** — shared-secret 단일이라 유출 시 전면 우회. Cloudflare IP
   allowlist 또는 mTLS 한 겹 + proxy header 로깅 금지/회전.
6. **[#78] WS rate-limit grace가 cap 잠식** — 거부 후 30초 close 지연 동안 연결이 cap 슬롯을
   계속 점유 → 슬롯 고갈 벡터. grace 단축 또는 즉시 disconnect.
7. **[#78] `publish_event` await가 actor HTTP 경로를 최대 2초 결합** — 느린 구독자 1명이
   POI/trip 응답 지연. broadcast fire-and-forget 분리.
8. **[#80] 감사 hash-chain head fork** — `prev_hash=MAX(log_id)`를 동시 트랜잭션이 같이 읽어
   체인 분기 가능. `prev_hash` unique 또는 advisory lock.
9. **[#79] money 표현 3갈래** — admin 응답이 `z.union([string,number])`로 남음. 응답을
   `NonNegativeDecimalStringSchema`로 통일 + `packages/schemas` round-trip 테스트 추가.
10. **[#73] storage `AttachmentResponse` 필드 비대칭** — notice-plans는 alias 유지인데 storage는
    `curated_*` 신규명. 호환 정책 통일.
11. **[#83] MCP `list_trips` parity** — `bucket`/`cursor` 누락(실제 `GET /trips`와 불일치) +
    search_features HTTP(ADR-026) vs stale "함수 직접 호출" 표현 정리.

### 🟢 낮음 (문서·테스트·정규화)
- [#74] svix-id replay dedup. [#75] reveal query 파라미터 제거·명시 거부.
- [#76] 로그인-상태 비번 변경 시 helper 강제; reset 후 구 refresh 401 e2e.
- [#77] block_unknown 기본 False 재검토; `_roles_set` casing 정규화(DB 대문자 role 우회 실패).
- [#78] websocket.md presence.cursor 표 longitude/latitude·legacy 수용 명시; per-minute 테스트.
- [#79] 응답 money regex 지수표기 케이스. [#80] force_verify rollback 테스트; commit 강제 헬퍼.
- [#73] 모델 누락 CHECK(`__table_args__`); system-notice용 신규 `notice_plans` 테이블.
- [#81] `trips.md` §5.1 중복 payload 링크 축약; reorder 단일형 문서 정리.
- [#83] Sprint 6 `app.mcp_tokens` postgres-schema 반영.

---

## 2. 후속 처리 제안

- 신규 [높음]은 없으나, 위 [중간] 1~8(특히 fail-open 2건 + race 2건)은 보안/무결성
  영향이라 **T-162~T-169**로 backlog 승격(`docs/tasks.md`).
- 이번 라운드는 "감사 → 구현 → 리뷰 → 잔존 보강" 루프가 **수렴 단계**임을 보여준다. 잔존은
  대부분 방어심화·테스트 가드라, v0.2.0(실시간/운영) 진입 전 한 번에 처리 가능한 규모다.
- 검증 메모: #78 리뷰가 초기에 "ADR-035 미존재"로 본 것은 **오탐**(ADR-035 =
  `docs/architecture/websocket-broker.md` 실재) — 본 종합에서 정정함.
