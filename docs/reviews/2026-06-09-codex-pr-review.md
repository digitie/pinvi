# Codex PR 사후 리뷰 종합 — 3라운드 (2026-06-09)

> **대상**: Codex가 올린 머지 완료 PR **14건** — #85, #86, #87, #89~#94, #96, #99, #100, #101, #107.
> (#73~#83은 2라운드 `docs/reviews/2026-06-08-codex-pr-review.md`에서 리뷰 완료 — 중복 제외.)
> **각 PR 코멘트**: 해당 PR에 "리뷰 결과 (사후 리뷰, Claude)" 게시(병렬 5에이전트).
> **후속**: 본 종합의 [높음]/[중간]을 T-183~187로 backlog 승격 + **코드 수정까지 반영**(본 라운드는
> 리뷰→수정 일괄, 사용자 지시).

---

## 0. 총평

- **신규 [높음] 2건** — 둘 다 **#100 backup hotswap**(운영 활성화 전 선결): cut-over 후 GRANT
  미복원(permission denied) + `--schema-only`(FK) 먼저 후 `--data-only` 무비활성 적재(FK 순서/순환
  실패). 비가역 cut-over라 무결성·가용성 영향이 커 우선 닫는다.
- **[중간]** — trip 권한/PII(#85/#101), websocket 부하(#91), trip cursor 의미·정합(#96), geofence
  단일헤더 약점(#90), 위치감사 chain 풀스캔(#107), backup 동시성/audit 고립(#100).
- **대체로 양호** — #86(보안 fail-open 반전), #87(feature_id opaque), #92(audit hash chain race),
  #93(money string), #94(storage alias), #99(POI rise/set)는 의도한 결함을 **실제로 닫았고** 잔존은
  대부분 낮음(문서·테스트·방어심화).

### PR별 verdict 요약
| PR | 주제 | verdict | 최고 잔존 |
|----|------|---------|-----------|
| #85 | trip detail view builder | 견고하나 companion에 PII/공유메타 노출 scope 확장 | 중간 |
| #86 | resend webhook opt-in | fail-open을 명시 opt-in으로 정확히 반전, clean | 낮음 |
| #87 | feature_id opaque string | read/Protocol/schema/builder 일관, 무결 | 낮음 |
| #89 | reset 후 access token 무효화 | 견고, fail-open/bypass 없음 | 낮음 |
| #90 | geofence trusted-proxy | fail-closed 정확, 단 단일헤더 strict 약점 | 중간 |
| #91 | ws backpressure 분리 | 의도 달성, 부하 시 잔존 2건 | 중간 |
| #92 | admin audit hash chain | advisory lock+UNIQUE 이중방어, race 닫힘 | 낮음 |
| #93 | money response string | 응답 표현 완전 통일, clean | 낮음 |
| #94 | storage attachment alias | 대칭 구현 정합 | 낮음 |
| #96 | trip list cursor parity | 형식 견고하나 offset cursor + 기본 bucket 변경 | 중간 |
| #99 | POI rise/set 노출 | N+1 회피·일관, clean | 낮음 |
| #100 | backup restore hotswap | 입력안전·골격 양호, cut-over 무결성/가용성 리스크 다수 | **높음** |
| #101 | trip subresource APIs | IDOR 차단 OK, 쓰기권한/입력신뢰/shared 보강 필요 | 중간 |
| #107 | admin priority3 views | RBAC·마스킹·테스트 견고, chain 풀스캔 개선점 | 중간 |

---

## 1. 긴급성순 통합 TODO

### 🔴 높음 (#100 — 운영 활성화 전 선결, → T-183)
1. **cut-over 후 GRANT 미복원** — `pg_dump --no-privileges`로 복원 → 앱 role이 신 스키마 owner가
   아니면 switch 직후 `permission denied`. switch 후 GRANT 재적용 또는 단일 owner 전제 명시.
2. **FK 적재 순서 실패** — `--schema-only`(FK 포함) 먼저, `--data-only`를 트리거/FK 비활성 없이
   적재 → FK 순서·순환 시 적재 실패. `SET session_replication_role = replica` 또는 제약을 데이터 후 생성.

### 🟡 중간
3. **[#101] companion 쓰기권한 미강제** (→ T-184) — `_is_companion` viewer가 day 삭제(POI cascade)·
   첨부·재정렬 가능. editor/co_owner 이상만 쓰기 허용하는 권한 헬퍼 도입.
4. **[#101] 첨부 metadata 클라 입력 무검증** (→ T-184) — `public_url`/`storage_key`/`bucket` 무검증
   `create_attachment(**payload)`. `public_url` 서버 파생 + prefix/bucket allowlist.
5. **[#85] companion에게 다른 companion `invited_email`/`user_id` + share_link 메타 노출** (→ T-184) —
   비-owner viewer에 PII. companions/share_links를 owner/co_owner 전용 또는 invited_email 마스킹.
6. **[#101] 비로그인 shared GET 무제한 쓰기 + rate limit 부재** (→ T-184) — `last_used_at` 매요청
   commit + 문서의 분당 60회 미구현. rate limit 구현 또는 갱신 best-effort화.
7. **[#100] API 트리거 drain 자기사살** (→ T-183) — drain이 자기 api 컨테이너 stop → 반쪽 swap +
   audit 유실. API 경로 drain은 read-only 전환류로.
8. **[#100] 동시성 advisory lock 부재 + restore_id 초 해상도 충돌** (→ T-183) — pg advisory lock +
   uuid/ms restore_id.
9. **[#100] cut-over audit가 스왑된 스키마에 기록·라이브 이력 고립** (→ T-183) — 별도 연결/previous
   스키마에 기록.
10. **[#91] grace 윈도우 raw 소켓 누수** (→ T-185) — 거부 후 슬롯 반환하나 소켓 ~30초 유지 →
    connect→spam→reconnect 누적으로 cap 초과 half-closed 소켓 → FD/mem DoS. grace 연결 별도 추적 또는
    abuser 즉시 disconnect.
11. **[#91] 동일 websocket 동시 `send_json`** (→ T-185) — `_broadcast` gather가 같은 소켓에 동시 전송
    → 이벤트(version) 순서/프레임 인터리브 미보장. per-connection 송신 직렬화.
12. **[#96] offset 인코딩 cursor + 기본 정렬 → page skip/중복** (→ T-186) — keyset(updated_at,trip_id)
    전환.
13. **[#96] 무필터 `GET /trips` 의미 변경(과거 제외, bucket 기본 future)** (→ T-186) — 호출부 회귀 확인,
    전체는 `bucket=all`.
14. **[#90] geofence mTLS 단일헤더 strict 약점** (→ T-187) — 헤더만으론 origin 직타 spoof 가능(default
    "SUCCESS" 추정). network CIDR 병행 강제 + 헤더값 secret 취급.
15. **[#107] 위치감사 조회마다 전체 chain 풀스캔 O(n)** (→ T-187) — 필터/limit 무시. 반환 윈도우만
    검증 또는 별도 캐시 엔드포인트.

### 🟢 낮음 (코드/문서/테스트 — 일부만 코드 반영, 나머지 문서 표기)
- [#86] `.env.example` 2개 `ALLOW_UNSIGNED=true` 출하 → example 기본 false. **(코드 반영)**
- [#93] money 지수표기 직렬화 가설 → 백엔드 `Decimal` quantize 보장. **(코드 반영)**
- [#99] `poi_rise_set_to_dict` 수동 필드 중복 → `model_validate`로 단일화. **(코드 반영)**
- [#89] 보호 라우트마다 User SELECT 1회(즉시 무효화 트레이드오프, 인지). geofence role resolver
  token_version 미확인(미악용, 정합화).
- [#87] 응답 feature_id에 저장 suffix 노출 vs canonical 내부 batch(회귀 아님, 문서화).
- [#90] CIDR가 `request.client.host` 의존(현재 안전, `--proxy-headers` 추가 시 위험 — 문서화);
  `_trusted_proxy_networks()` 매요청 재파싱 → boot 캐시.
- [#92] isolation(RC) 전제 주석; migration 사전 dedup 부재 주석.
- [#94] mismatch reject dead-code 주석; "Deprecated"↔"지원 alias" 문구 통일.
- [#96] `q` strip 후 1자/공백 미적용; `ilike` `%`/`_` 미이스케이프; date_from NULL end_date 처리;
  trips만 meta cursor(pois/notice 규약 불일치). **(일부 코드 반영)**
- [#99] 시간대 표현 계약(timestamptz +00:00 vs docs +09:00) 문서화.
- [#100] 검증이 users 존재만 확인; 실패 시 구조화 phases 손실; `app_previous_*` 정리 정책;
  `_request_uuid` 잘못된 X-Request-Id 조용히 랜덤 대체.
- [#101] owner transfer 대상 임의 사용자(수락 절차); `_to_attachment_response` 미존재 필드 전달;
  soft delete가 trip.updated 발행; optimize 빈 day 오류 혼동.
- [#107] error_message 무마스킹; 좌표 4자리 마스킹 강도; `require_role` user status 미확인(기존).

---

## 2. 후속 처리 (T-183~187) + 코드 수정

본 라운드는 사용자 지시로 **리뷰→코드 수정을 일괄** 진행한다. 승격 태스크:

- **T-183 [높음] #100 backup hotswap 무결성/가용성** — GRANT 복원, FK 적재순서, self-kill drain,
  advisory lock + restore_id, audit 고립.
- **T-184 [중간] #101/#85 trip 권한·PII·첨부검증·shared rate limit** — companion 쓰기권한, PII 마스킹,
  첨부 입력검증, shared rate limit.
- **T-185 [중간] #91 websocket** — grace 소켓 누수, per-conn send 직렬화, shutdown drain.
- **T-186 [중간] #96 trip list cursor** — keyset 전환, bucket 기본 회귀, q/ilike escape.
- **T-187 [중간] #90/#107** — geofence CIDR 병행, 위치감사 chain 윈도우 검증.

> 코드 반영 결과는 후속 PR에 기록하고 본 문서의 항목별 ✅로 추적한다.

### 코드 반영 결과 (2026-06-09, 동일 PR)
- ✅ **T-184** (#101/#85): `get_trip_for_user_write`(owner/co_owner/editor) — day/attachment/
  trip-update/optimize(persist) 쓰기 게이트, viewer read-only. `build_trip_view(include_management)`
  로 비-owner에 `invited_email` 마스킹 + share_links 비노출. `AttachmentCreate` bucket pattern +
  storage_key traversal 거부 + public_url http(s) 검증. shared `last_used_at` 1분 throttle. +회귀 테스트.
- ✅ **T-186** (#96): 기본 `-updated_at` keyset cursor(updated_at,trip_id) 전환 + `ilike` %/_/\ 이스케이프.
- ✅ **T-185** (#91): rate-limit grace 동안 broker 슬롯 유지(cap 우회/FD 누수 차단) + `RealtimeConnection.send_lock`
  연결별 송신 직렬화. 기존 테스트를 새 불변식으로 갱신.
- ✅ **T-187** (#90/#107): geofence strict 모드 mTLS-header 신뢰에 CIDR 앵커 강제. 위치감사 chain
  `_is_location_window_broken`(per-row self-consistency + 앵커 링크) — 풀스캔 제거.
- ✅ **T-183** (#100 높음): restore-hotswap.sh FK 적재 `session_replication_role=replica` + swap 전
  GRANT 재적용(`PINVI_RESTORE_APP_ROLE`). backup_service restore_id uuid suffix + `_restore_lock` 직렬화.
  후속 보강으로 DB `pg_try_advisory_lock`, API-trigger self-kill drain guard, previous-schema
  success audit reflection을 추가해 T-183 잔여를 닫았다.
- ✅ 낮음: `.env.example` 2개 `ALLOW_UNSIGNED=false`(#86).
- **잔여(후속 task로 유지)**: #99 rise_set model_validate·#93 money quantize 등 낮음(저위험·문서/가설).
