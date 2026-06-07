# Codex PR 사후 리뷰 종합 (2026-06-07)

> **대상**: Codex(`agent/codex-*`)가 올린 머지 완료 PR **20건** — #50, #52–#65, #67–#71.
> (#51·#66은 Claude 작성이라 제외.) 다수가 2026-06-06 정합성 감사
> (`docs/audit/2026-06-06-doc-impl-audit.md`)의 후속 Task를 구현한 것이라, 각 PR이
> 해당 감사 항목을 **실제로 닫았는지**를 중점 검증했다.
> **각 PR 코멘트**: 해당 PR에 "리뷰 결과 (사후 리뷰)" 코멘트로 게시함.
> **긴급성 정의**: 높음=보안/데이터무결성/가용성/운영사고 또는 계약 깨짐, 중간=정합성/누락
> 기능/테스트 공백, 낮음=품질/문서 미세.

---

## 0. 총평

- **감사 백로그 대부분이 실구현으로 닫혔다**(stub 아님). 특히 D-13(geofence #60),
  C-14(auth refresh #71), C-22(resend #70), C-03/D-05(WS #63), D-02/D-03(schema #64),
  D-06(comments #65), D-10(budget #67), D-11(region #69)이 데이터/엔드포인트 수준으로 실현.
- **단, "닫혔다"가 "완결"은 아니다.** 보안 PR 2건(#70, #71)과 가용성 PR 1건(#63)에서
  **잔존 결함**을 확인했다 — 아래 [높음] 참조. 특히 **#70은 C-22를 완전히 닫지 못했다**
  (secret 미설정 fail-open + Svix base64 디코드 버그).
- 공통 약점: ① admin 상태변경의 **status+audit 비원자성**(#50/#52/#53), ② 응답
  **money/snapshot 필드 타입·이름 불일치**(#61/#67), ③ 음성 권한 테스트(403/401) 공백.

---

## 1. 긴급성순 통합 TODO

### 🔴 높음 (보안·무결성·가용성·계약)
1. **[#70] resend webhook fail-open 제거** — `TRIPMATE_RESEND_WEBHOOK_SECRET` 미설정 시
   서명검증을 통째로 건너뜀(`config.py:43` 기본 `""`). 운영 누락 시 C-22 취약점 재현 →
   미설정이면 fail-closed(401/503), dev만 `settings.debug` 게이트.
2. **[#70] Svix secret base64 디코드 버그** — `_decode_svix_secret`가 `altchars=b"-_"`로
   디코드해 표준 base64 `whsec_` secret이 깨짐 → **운영 서명이 전부 mismatch**. 표준
   `b64decode`로 교정 + 표준 secret 테스트(대칭 테스트가 버그를 가림).
3. **[#50] PII가 URL에 남음** — `access_reason`을 query string으로 전송(`admin.ts` getUser,
   `users.py:144`). nginx log/히스토리/프록시에 평문. 이미 지원하는 `X-Access-Reason`
   헤더(또는 body)로 전환.
4. **[#71] 비밀번호 재설정이 기존 refresh session 미폐기**(`auth.py:225`) — 계정 탈취 후
   재설정해도 탈취 세션 유효. 재설정 시 해당 user 활성 session 전부 revoke.
5. **[#60] geofence header spoof 우회** — `CF-IPCountry` 무검증 신뢰 + nginx GeoIP2를
   3중→선택으로 강등 → Cloudflare 우회 직접 접근 시 `CF-IPCountry: KR`로 무력화. fallback에
   Cloudflare 발신 검증(공유 시크릿 헤더/IP allowlist/mTLS) 추가.
6. **[#63] WS rate limit + cursor 증폭 차단** — 문서 §7(초당 5/분당 60) 미구현,
   `presence.cursor` 무검증 전체 재방송으로 fan-out DoS(`ws.py:295-307`).
7. **[#63] WS broadcast backpressure + 연결 수 캡** — `_broadcast`가 timeout 없는 순차
   await(`realtime_broker.py:461-470`)라 느린 1 소켓이 trip 전체 블록.
8. **[#67] 응답 money 필드 Zod 타입 깨짐** — 백엔드는 `Decimal`→문자열인데
   `poi.ts:64`/`notice-plan.ts:14`는 `z.number()` → 응답 파싱 reject. `z.string()`/
   `z.coerce.number()`로 정합.
9. **[#53] admin link-status 변경과 audit append 비원자** — 사이 실패 시 상태만 바뀌고
   감사 누락(해시체인 위배). 단일 트랜잭션으로. (#50/#52도 같은 패턴)

### 🟡 중간 (정합성·누락 기능·테스트)
- **[#54] README `GET /search` 앵커 깨짐** — `#26-get-search`→`#27-get-search`(A-14 fix가
  도입한 dangling).
- **[#70] svix-id replay dedup** 도입(멱등 보강).
- **[#71] refresh rotation atomic UPDATE/row lock**(동시 요청 이중 발급) + **revoked replay 시
  family 전체 폐기**(reuse detection).
- **[#60] 운영 `async_session_factory` DB role 경로 통합 테스트**(현재 resolver 분기만 테스트).
- **[#63] `publish_event` HTTP 경로 예외 격리** + **presence.cursor 좌표 lng-first 통일**(A-07).
- **[#64] security_incidents** ORM CheckConstraint 이름 = migration 이름 정합 + **PII 보존/
  마스킹 정책**(schema §8) + `/admin/incidents`·breach 트리거 구현(Sprint 6).
- **[#65] comments** limit 상한+최신순/커서 + **visibility='comment' shared-token 댓글 경로
  구현해 D-06 종결**.
- **[#67] trip/day 예산 집계·cap** 후속 슬라이스(현재 POI 단위만).
- **[#69] POI 자동 보강의 trip version 무단 증가 + broadcast 누락** 정리 + **region code
  유효성 강화**(`{2,5,8,10}`/참조 FK)와 행정 level 기록.
- **[#61] feature `title` vs POI snapshot `name` vs `title_snapshot` 키 통일**(A-17).
- **[#62] backup 디스크 가드 기준을 dump size→live schema 실측**으로 + **T-111 restore
  스크립트 schema명 검증+confirm 가드** 요건 명문화.
- **[#59] gemini partial unique index를 Alembic에 동일 이름·WHERE 반영.**
- **[#55] data-sources/data-policy/pipa의 Gemini "현재 책임" 잔존 표현 정정**(ADR-020).
- **[#68] 두 reminder 워크플로 공통 concurrency group**(head SHA 중복 댓글 레이스).
- **[#50] reveal RBAC를 admin 전용으로 좁히고 UI/문서 정합 + reveal POST 분리.**
- **[#52] admin 엔드포인트별 RBAC(403)·404 테스트 + #53 동일.**

### 🟢 낮음 (품질·문서)
- [#50] q LIKE 와일드카드 이스케이프 + reason 길이 검증; 음성 테스트.
- [#52] `_to_detail` owner email KeyError 방어 + status/visibility enum 검증.
- [#53] snapshot ilike 검색 인덱스 전략.
- [#56] README Sprint 5 셀에 T-067 추가; ADR-002 제목에 superseded 표기.
- [#57] SPRINT-1 krtour-map ADR-032 vs TripMate ADR-032 혼동 주석; admin-rbac.md 작성.
- [#58] CLAUDE §4 스택에 `python-kraddr-geo` 추가; 감사문서 T-143 체크박스 동기.
- [#59] rise/set snapshot UI 동작 단일안.
- [#61] `GET /trips` cursor sort 종속성 명문화; §2.7 addresses `/geo/search` 정렬.
- [#63] WS query token 로그 노출 완화 + 누락 테스트.
- [#64] `assigned_cpo_user_id` FK 인덱스.
- [#65] 비멤버/비작성자 403·중복초대 409 테스트; remove_companion 예외 분리.
- [#67] DB check 제약(소문자 currency·음수) 직접 테스트.
- [#68] monitor main 루프 PR 단위 예외 격리; synchronize debounce.
- [#69] manual 값 비덮어쓰기 guard 회귀 테스트; telegram brief 소비측 배선(D-11 완결).

---

## 2. PR별 요약

| PR | Task | 감사항목 | 머지판단 | 핵심 잔존 |
|----|------|----------|----------|-----------|
| #50 | T-119 admin users | C-08/C-17 | 조건부 적정 | access_reason PII URL(높음), reveal RBAC/POST(중) |
| #52 | T-120 admin trips | C-08 | 적정 | status+audit 원자성, 권한 테스트 |
| #53 | T-121 admin pois | C-08 | 적정 | audit 원자성(높음), 낙관락 |
| #54 | T-123 doc 정합 | A-14 등 | 적정(1건 잔존) | README `/search` 앵커 깨짐 |
| #55 | T-149 gemini | P-03 | 적정 | data-sources/pipa 잔존 표현 |
| #56 | T-150 추적정합 | P-04~21 | 적정 | Sprint5 셀 T-067 등 미세 |
| #57 | T-151 ADR 백필 | P-07/08 | 적정 | 번호 혼동 주석 |
| #58 | T-143 지도/소셜 | D-15/21/22 | 적정 | CLAUDE §4 kraddr-geo |
| #59 | T-147 doc tail | D-23/25 | 적정 | Alembic 인덱스 반영 |
| #60 | T-142 geofence | D-13/24 | 적정(보안 후속) | header spoof 우회(높음) |
| #61 | T-144 검색/내보내기 | D-16/17 | 적정 | snapshot 키 통일 |
| #62 | T-145 backup swap | D-19 | 적정 | 디스크 가드 기준, restore 가드 |
| #63 | T-128 realtime WS | C-03/D-05 | 조건부 승인 | rate limit·backpressure(높음) |
| #64 | T-138 security schema | D-02/03/09 | 적정 | 제약명/PII 보존/incidents 구현 |
| #65 | T-139 comments | D-06 | 적정 | visibility 경로·limit |
| #67 | T-140 budget | D-10 | 적정 | Zod money 타입(높음) |
| #68 | (pr-monitor MCP) | — | 적정 | 중복 댓글 레이스 |
| #69 | T-141 trip region | D-11 | 적정 | version 증가·region 검증 |
| #70 | T-136 resend webhook | C-22 | **조건부(미완결)** | fail-open + base64 버그(높음) |
| #71 | T-134 auth refresh | C-14 | 적정(보안 후속) | reset 미폐기(높음) |

---

## 3. 후속 처리 제안

- 위 [높음] 9건은 **신규 후속 Task로 즉시 등록** 권장(보안 4건: #70×2/#50/#71/#60,
  가용성 2건: #63×2, 계약/무결성 2건: #67/#53). 특히 **#70 두 건은 C-22가 사실상 미해결**
  이므로 T-136 재오픈 또는 신규 Task 필요.
- 공통 패턴(admin status+audit 원자성, money/snapshot 필드 정합, 음성 권한 테스트)은
  개별 PR이 아니라 횡단 정리 Task로 묶는 게 효율적.
- 본 종합은 `docs/tasks.md` 후속 백로그로 lift 가능한 형식(긴급성 라벨 + PR 출처)이다.
