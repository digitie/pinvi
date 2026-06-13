# Claude PR 사후 리뷰 종합 (2026-06-10)

> **대상**: Claude(`agent/claude-*`)가 2026-06-08 00:00 KST 이후 올린 PR **23건** —
> #84, #88, #95, #97, #98, #102~#106, #109, #110, #113~#123.
> 사용자가 요청한 "최근 2일, closed PR 포함 전체" 범위로 확인했다. 리뷰 시작 뒤 새로
> 머지된 #122/#123도 같은 라운드에 포함했다.
> **기존 리뷰/댓글**: 각 PR에는 GitHub Actions `MCP 기반 리뷰 필요` 알림만 있었고,
> 사람/agent의 상세 review 또는 inline comment는 없었다.
> **각 PR 코멘트**: 해당 PR에 "리뷰 결과 (사후 리뷰, Codex)" 코멘트를 게시한다.
> **후속**: 아래 [높음]/[중간]은 본 PR에서 코드 수정까지 반영한다.

---

## 0. 총평

- 문서 PR(#84/#88/#95/#97/#103~#106)은 kor-travel-map 외부 계약과 DEC-05/ADR-048 추종을
  정리했고, 현 main과 충돌하는 차단 결함은 없었다.
- 구현 PR은 kor-travel-map client(#102/#113), feature 제안(#110), geo/regions(#114/#115),
  location audit outbox/cache(#116/#117), 좌표 `lon`/`lat` 정렬(#119), 첨부/RustFS(#120~#123)
  순서로 빠르게 누적됐다.
- 신규 차단급 결함은 **위치 감사 인증 주체 추적**, **첨부 storage ref 신뢰**, **admin
  큐레이션 upload 권한**에서 확인했다. 모두 같은 라운드에서 수정한다.

---

## 1. 긴급성순 통합 TODO

### 🔴 높음

1. **[#116] location-audit outbox가 인증 사용자를 안정적으로 받지 못함**
   - `LocationAuditMiddleware`는 `request.state.user_id`를 기대하지만 인증 의존성이 이를
     세팅하지 않았다. 또한 `X-User-Id` 헤더를 신뢰하면 정상 요청은 audit 누락되고,
     spoof header가 있으면 다른 사용자로 기록될 수 있다.
   - 수정: `get_current_user_id()`가 검증된 user id를 `request.state.user_id`에 저장한다.
     `LocationAuditMiddleware`는 더 이상 `X-User-Id`를 읽지 않고, `RequestIdMiddleware`가 저장한
     request id를 사용한다. `/features/requests`는 검증된 body 좌표를
     `request.state.location_audit_coord`로 넘겨 outbox 좌표도 보존한다. spoof 회귀 테스트를
     추가한다.

2. **[#120/#121] trip/POI 첨부 metadata가 임의 bucket/storage_key를 참조 가능**
   - `AttachmentCreate`는 경로 traversal만 막고, 서버가 발급한 presigned key인지 검증하지 않았다.
     이후 download-url PR(#121)이 DB row 기준으로 presigned GET을 만들기 때문에, 악성 row가
     다른 bucket/key를 가리킬 여지가 있었다.
   - 수정: metadata 등록 시 bucket이 `PINVI_RUSTFS_BUCKET`과 같고,
     `storage_key`가 `user-uploads/{trip_attachment|poi_attachment}/{current_user_id}/` prefix인지
     검증한다. 위반 시 422 `INVALID_ATTACHMENT_STORAGE_REF`.

3. **[#123] admin 큐레이션 첨부도 같은 storage ref 신뢰 문제가 생김**
   - #123이 `/admin/notice-plans/*/attachments` metadata 등록을 추가했지만, trip 첨부와
     동일하게 임의 `bucket`/`storage_key`를 받아 저장했다.
   - 수정: admin 큐레이션 metadata 등록 시
     `user-uploads/{curated_plan_attachment|curated_poi_attachment}/{admin_user_id}/` prefix만
     허용한다. 위반 시 422 `INVALID_ATTACHMENT_STORAGE_REF`.

### 🟡 중간

4. **[#123] `/storage/upload-urls`가 `curated_*` 목적을 일반 사용자에게도 발급**
   - metadata 등록은 admin 전용이지만, presigned PUT 발급은 목적별 권한을 보지 않았다. 일반
     사용자가 `curated_plan_attachment` prefix 객체를 만들 수 있어 orphan object/저장소 남용
     경로가 열린다.
   - 수정: `curated_plan_attachment` / `curated_poi_attachment` presigned 발급은 admin role만
     허용하고, 비권한은 기존 admin 규약처럼 404로 숨긴다.

5. **[#119] `/features/nearby` query가 `lng`로 남아 `lon`/`lat` 결정과 어긋남**
   - 좌표 응답/대부분 query는 `lon`/`lat`로 정렬됐지만 `/features/nearby`만 `lng`를 받았다.
   - 수정: query parameter를 `lon`으로 바꾸고, legacy `lng` 요청은 422로 거부하는 회귀 테스트를
     추가한다.

### 🟢 낮음 / 추적 유지

- **[#102/#113] kor-travel-map HTTP client는 도입됐지만 `/features/*` router cutover는 T-173/T-174
  잔여 작업**이다. 이번 리뷰 결함은 아니며, `docs/tasks.md`의 기존 kor-travel-map 연동 queue를
  유지한다.
- **[#122] `/admin/rustfs/*` 객체 관리는 admin 전용 + DB 참조 보호가 들어가 있어 새 차단
  결함은 없었다.** 다만 #123 metadata 검증 부재 때문에 참조 row 자체를 신뢰할 수 있게 보강한다.

---

## 2. PR별 요약

| PR | 주제 | verdict | 후속 |
|----|------|---------|------|
| #84 | Codex PR 2라운드 리뷰 종합 | 적정 | 없음 |
| #88 | kor-travel-map REST 계약 청사진 | 적정 | T-170~T-178 queue 유지 |
| #95 | DEC-05 feature 제안/재적재 분리 | 적정 | 없음 |
| #97 | DEC-05 correction + K-15 필요 | 적정 | kor_travel_map feature change queue 유지 |
| #98 | RustFS settings 배선 | 적정 | 첨부 metadata 검증은 #120~#123 후속에서 처리 |
| #102 | T-170/T-171 kor_travel_map client/config | 적정 | router cutover는 기존 T-173/T-174 |
| #103~#106 | kor_travel_map PR #316/#317 반영 문서 | 적정 | 없음 |
| #109 | Codex 3라운드 후속 정리 | 적정 | 없음 |
| #110 | feature 제안 type/target 노출 | 적정 | 없음 |
| #113 | 외부 `/v1` hard cutover | 적정 | kor_travel_map 미머지 envelope/problem+json 추종 대기 |
| #114/#115 | kor-travel-geo `/geo/*`·`/regions/*` | 적정 | 없음 |
| #116 | location-audit outbox | **수정 필요** | 인증 user/request id state 저장 |
| #117 | feature TTL cache | 적정 | 없음 |
| #118 | 리뷰 잔여 낮음 묶음 | 적정 | 없음 |
| #119 | 좌표 `lon`/`lat` 정렬 | **수정 필요** | `/features/nearby` query `lon` |
| #120/#121 | trip/POI 첨부 하드닝/download-url | **수정 필요** | storage ref 검증 |
| #122 | `/admin/rustfs/*` 객체 관리 | 적정 | 없음 |
| #123 | admin 큐레이션 첨부 | **수정 필요** | storage ref 검증 + curated upload admin gate |

---

## 3. 코드 반영 결과

- ✅ #116: `RequestIdMiddleware`가 `request.state.request_id`를 저장하고,
  `get_current_user_id()`가 인증된 user id를 `request.state.user_id`에 저장한다.
  `LocationAuditMiddleware`는 spoof 가능한 `X-User-Id`를 버리고 state 값만 사용한다.
  `/features/requests` body 좌표도 state로 넘겨 `location_audit_outbox`에 보존한다.
- ✅ #120/#121/#123: `rustfs_storage.validate_attachment_storage_ref()` 공통 검증을 추가하고,
  trip/POI 및 admin 큐레이션 metadata 등록에 적용했다.
- ✅ #123: `/storage/upload-urls`의 `curated_plan_attachment` /
  `curated_poi_attachment` 목적은 admin role만 발급한다.
- ✅ #119: `/features/nearby` query를 `lon`/`lat`로 정렬하고, legacy `lng` 요청 거부 테스트를
  추가했다.

검증 명령과 결과는 PR 본문과 `docs/journal.md`에 기록한다.
