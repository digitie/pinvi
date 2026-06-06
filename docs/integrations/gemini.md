# Gemini Deep Research (사용자 키)

각 사용자가 자신의 Gemini API 키를 등록하여 POI 보강 정보를 생성하는 **사용자
주도 enrichment**. v1 시점 design-only — v2에서도 코드 작성 단계 진입 후
(Sprint 5+) 적용.

## 1. 정책 (v1 시점 결정 유지)

- **자동 schedule X** — 사용자가 명시적으로 trigger
- API 키 원본은 **DB / 로그 / Sentry에 절대 저장 X**:
  - `secret_ref` (환경변수 이름 또는 vault 참조)
  - `masked_fingerprint` (`AIza...****`)
  - 검증 상태 (`last_verified_at`, `last_verification_status`)
- 결과는 **별도 테이블** — provider-confirmed source data와 분리
- UI에 "Gemini 생성 요약/조사 결과" 라벨 + 출처/인용 표시 (할루시네이션 위험)
- YouTube URL 직접 전달 (`file_data.file_uri` 모드, preview unstable)
- 사용자 키와 시스템 키 분리:
  - 사용자 manual run → 사용자 키
  - admin/system batch (auto-monitor) → 시스템 키

## 2. DB 모델 (app schema)

### 2.1 `app.user_provider_keys`

```sql
CREATE TABLE app.user_provider_keys (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                  uuid NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
  provider                 varchar(32) NOT NULL,        -- 'gemini'
  secret_ref               varchar(255) NOT NULL,        -- vault key or env var name
  masked_fingerprint       varchar(64) NOT NULL,         -- 'AIza...XXXX'
  is_enabled               boolean NOT NULL DEFAULT true,
  last_verified_at         timestamptz,
  last_verification_status varchar(32),                 -- 'ok' | 'invalid' | 'rate_limited'
  created_at               timestamptz NOT NULL DEFAULT now(),
  updated_at               timestamptz NOT NULL DEFAULT now(),
  deleted_at               timestamptz
);

CREATE UNIQUE INDEX user_provider_keys_active_provider_uidx
  ON app.user_provider_keys (user_id, provider)
  WHERE deleted_at IS NULL;
```

### 2.2 `app.gemini_research_runs`

```sql
CREATE TABLE app.gemini_research_runs (
  id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                 uuid NOT NULL REFERENCES app.users(user_id),
  feature_id              text NOT NULL,                -- 라이브러리 feature_id reference
  idempotency_key         varchar(80) NOT NULL,         -- (user_id, feature_id, prompt_version, day_bucket)
  gemini_key_ref          varchar(255) NOT NULL,        -- secret_ref
  model                   varchar(64) NOT NULL,         -- 'gemini-2.5-flash' etc
  prompt_version          varchar(32) NOT NULL,
  prompt                  text NOT NULL,
  input_context_summary   jsonb,                        -- 입력 요약 (좌표/이름/주변 등)
  status                  varchar(16) NOT NULL DEFAULT 'queued', -- queued|running|succeeded|failed|canceled
  result_summary          text,                          -- 요약 본문
  result_sections         jsonb,                         -- {요약, 방문포인트, 주의사항, ...}
  sources                 jsonb,                         -- 인용 [{url, title, accessed_at}]
  error_code              varchar(64),
  error_message           text,
  started_at              timestamptz,
  finished_at             timestamptz,
  created_at              timestamptz NOT NULL DEFAULT now(),
  UNIQUE (idempotency_key)
);

CREATE INDEX gemini_runs_user_feature_idx ON app.gemini_research_runs (user_id, feature_id);
CREATE INDEX gemini_runs_status_idx ON app.gemini_research_runs (status) WHERE status IN ('queued', 'running');
```

## 3. 결과 섹션 (`result_sections`)

```jsonc
{
  "요약": "...",
  "방문 포인트": ["...", "..."],
  "주의사항": "...",
  "교통/주차": "...",
  "가족/아이 동반 적합성": "...",
  "비 오는 날 대안": "...",
  "출처/근거": [
    { "url": "...", "title": "...", "accessed_at": "..." }
  ]
}
```

UI는 섹션별 collapsible.

## 4. API endpoint (v2 단계)

### 4.1 `POST /users/me/provider-keys`

```http
POST /users/me/provider-keys
Content-Type: application/json
Cookie: tripmate_access=...

{
  "provider": "gemini",
  "api_key": "AIza..."        // body로만 받음, 즉시 vault/secret store 저장
}
```

- 서버: vault에 저장 → `secret_ref` 받음 → `masked_fingerprint` 계산 → DB row
- 응답 201: `{ "data": { "id": "uuid", "provider": "gemini", "masked_fingerprint": "AIza...XXXX", "is_enabled": true } }`
- **응답에 raw key 절대 X**

### 4.2 `POST /users/me/provider-keys/{id}/verify`

vault에서 secret 가져와 Gemini API ping → `last_verified_at` 갱신.

### 4.3 `DELETE /users/me/provider-keys/{id}`

- vault에서 secret 삭제 + DB row `deleted_at = now()`
- 진행 중인 `gemini_research_runs` cancel

### 4.4 `POST /trips/{trip_id}/pois/{poi_id}/research`

```http
POST /trips/{trip_id}/pois/{poi_id}/research
Content-Type: application/json

{
  "prompt_version": "v1",
  "include_youtube_urls": ["https://youtube.com/watch?v=..."]   // 선택
}
```

- 사용자 키 활성 확인
- `gemini_research_runs` row 생성 (`status='queued'`)
- 비동기 worker가 Gemini 호출
- 응답 202: `{ "data": { "run_id": "uuid", "status": "queued" } }`

### 4.5 `GET /trips/{trip_id}/pois/{poi_id}/research/runs`

목록.

### 4.6 `GET /research/runs/{run_id}`

상세 + 진행 상황.

## 5. YouTube URL 모드

Gemini 2.5는 `file_data.file_uri`로 YouTube URL 전달 가능 (preview, unstable):

```python
import google.generativeai as genai

genai.configure(api_key=user_key)
model = genai.GenerativeModel('gemini-2.5-flash')

response = model.generate_content([
    {"file_data": {"file_uri": "https://youtube.com/watch?v=..."}},
    "이 영상에서 언급된 장소를 추출하고, 각 장소의 방문 포인트와 주의사항을 한국어로 요약해 줘.",
])
```

- 비디오 파일 자체 다운로드 X — URL passthrough만
- private / unlisted 영상은 skip
- 캡션 / 설명 / 대표 프레임 long-term 저장 X
- 사진/프레임을 public default image로 쓰지 않음 (라이선스 검토 전)

## 6. 추출된 장소 후보

YouTube/Gemini 결과의 장소 이름/주소/좌표는 **즉시 confirmed feature로 적재하지
않음**:

- TripMate `app.youtube_place_candidates` (또는 `app.gemini_place_candidates`)에
  `status='pending'`으로 저장
- Admin이 검수 후 라이브러리에 `feature_request`로 promote

자세히는 [`youtube-intelligence.md`](./youtube-intelligence.md).

## 7. Rate limit / Quota

- 사용자 키: Gemini 자체 quota (Free tier 분당 15 요청 등 — 변경 가능)
- TripMate 자체 한도: 사용자 당 일 50회 (Sprint 결정)
- 시스템 키: 신중하게 — auto-monitor batch는 batch당 N건 cap

## 8. UI

- 프로필 화면 `/profile/integrations/gemini` — API 키 등록 / 검증 / 해제
- POI 상세 패널 — "Gemini로 더 알아보기" 버튼 (키 있을 때만 enable)
- 결과는 별도 패널 (`GeminiResearchPanel.tsx`) — "Gemini 생성" 라벨 + 출처 링크

## 9. AI agent 구현 체크리스트

- [ ] `app.user_provider_keys` + `app.gemini_research_runs` Alembic
- [ ] vault / secret store 결정 (Hashicorp Vault / AWS Secrets Manager / 단순 암호화 DB) — ADR
- [ ] `apps/api/app/services/secrets.py` (vault wrapper)
- [ ] `apps/api/app/services/gemini/{client,research}.py` (google-generativeai SDK)
- [ ] `apps/api/app/api/v1/research.py` 라우터
- [ ] Worker (Dagster sensor 또는 별도 process)
- [ ] PII 마스킹 — Sentry / Loki에서 키 패턴 `AIza[\w-]+` 정규식 필터
- [ ] UI panel `apps/web/components/poi/GeminiResearchPanel.tsx`
- [ ] `docs/compliance/pipa.md` Google 위탁자 명시
