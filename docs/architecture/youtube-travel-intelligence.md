# YouTube + Gemini 여행 인텔리전스 (v2 design-only)

YouTube 채널 / playlist / 영상 모니터링 + Gemini 비디오 분석으로 여행 장소
후보 추출. v1 design-only — v2 단계 (v1.0 출시 후) 검토.

## 1. 정책

- 전체 동영상 파일 저장 X — Gemini API에 YouTube URL 직접 전달 (`file_data.file_uri`)
- 장소 후보는 `python-krtour-map`의 `Feature` + `SourceRecord` + `SourceLink`
  계약 + TripMate `media_asset` 구조와 연결
- Agent는 DB에 직접 접속 X — MCP 경유
- Agent는 YouTube 영상 파일 직접 다운로드 X
- Gemini-추론 주소는 confirmed 저장 X (`pending` 상태만)
- private / unlisted 영상 skip
- 캡션 / 설명 / 대표 프레임 long-term 저장 X
- 사진 / 프레임을 public default image로 쓰지 않음 (라이선스 검토 전)

## 2. 아키텍처

```
┌─────────────────────────────────────────┐
│ Main AI Agent (TripMate v2 chat / admin)│
│   - 사용자 / 운영자 트리거                  │
│   - DB 직접 접근 X                       │
└─────────────────────────────────────────┘
      │ MCP call
      ▼
┌─────────────────────────────────────────┐
│ Monitoring & Media MCP                  │
│   - YouTube RSS poll                    │
│   - videos.list 보강                    │
│   - Gemini video analyze                │
│   - 장소 후보 추출 → DB MCP에 write     │
└─────────────────────────────────────────┘
      │ MCP call
      ▼
┌─────────────────────────────────────────┐
│ TripMate DB MCP                         │
│   - read/write app.youtube_* tables     │
│   - 모든 write는 pending / draft        │
│   - 운영자 검수 후 promote              │
└─────────────────────────────────────────┘
```

## 3. DB 테이블 (TripMate `app` schema)

### 3.1 `app.youtube_monitor_sources`

```sql
CREATE TABLE app.youtube_monitor_sources (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_kind     VARCHAR(16) NOT NULL,    -- 'channel' | 'playlist' | 'video'
  source_external_id VARCHAR(64) NOT NULL,  -- YouTube channel/playlist/video id
  display_name    VARCHAR(255),
  is_active       BOOLEAN NOT NULL DEFAULT true,
  last_polled_at  TIMESTAMPTZ,
  last_error      TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_kind, source_external_id)
);
```

### 3.2 `app.youtube_video_records`

```sql
CREATE TABLE app.youtube_video_records (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  monitor_source_id UUID NOT NULL REFERENCES app.youtube_monitor_sources(id),
  video_external_id VARCHAR(32) NOT NULL,
  title            VARCHAR(255),
  description_snippet VARCHAR(500),       -- 일부만, 전체 저장 X
  published_at     TIMESTAMPTZ,
  duration_seconds INTEGER,
  privacy_status   VARCHAR(16),            -- 'public' | 'unlisted' | 'private'
  view_count       BIGINT,
  fetched_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (video_external_id)
);
```

### 3.3 `app.youtube_analysis_runs`

```sql
CREATE TABLE app.youtube_analysis_runs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  video_id        UUID NOT NULL REFERENCES app.youtube_video_records(id),
  initiated_by    VARCHAR(16) NOT NULL,    -- 'user' | 'system'
  user_id         UUID REFERENCES app.users(user_id),
  gemini_key_ref  VARCHAR(255),            -- secret_ref
  model           VARCHAR(64),
  prompt_version  VARCHAR(32),
  status          VARCHAR(16) NOT NULL DEFAULT 'queued',  -- queued|running|succeeded|failed
  result_summary  TEXT,
  raw_response    JSONB,                    -- 일부만, long-term 보존 X (purge job)
  error_code      VARCHAR(64),
  error_message   TEXT,
  started_at      TIMESTAMPTZ,
  finished_at     TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 3.4 `app.youtube_place_candidates`

```sql
CREATE TABLE app.youtube_place_candidates (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_run_id UUID NOT NULL REFERENCES app.youtube_analysis_runs(id),
  extracted_name  VARCHAR(255) NOT NULL,
  extracted_address TEXT,
  extracted_lng   NUMERIC(9, 6),
  extracted_lat   NUMERIC(9, 6),
  evidence_snippet TEXT,                    -- "10분 25초 화면에 보이는 간판" 등
  legal_dong_code TEXT,                      -- 주소 매칭 후
  address_match_method VARCHAR(32),          -- 'road_exact' | 'jibun_exact' | 'point_in_polygon' | NULL
  feature_id_promoted TEXT,                  -- 라이브러리에 confirm 후 채움
  status          VARCHAR(16) NOT NULL DEFAULT 'pending',  -- pending | promoted | rejected
  reviewer_id     UUID REFERENCES app.users(user_id),
  reviewed_at     TIMESTAMPTZ,
  reject_reason   TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## 4. YouTube Data API quota

- 일 10,000 units
- `search.list` = 100 units (피함)
- `videos.list` = 1 unit (선호)
- `playlistItems.list` = 1 unit
- `channels.list` = 1 unit

전략:

- RSS feed `https://www.youtube.com/feeds/videos.xml?channel_id=<CHANNEL_ID>` 2시간 주기 polling (quota 0)
- 신규 영상 발견 시 `videos.list`로 메타 + 시간 확인
- `search.list`는 운영자 명시 트리거만

## 5. 주소 매핑 우선순위

1. 자막 / 영상 텍스트에서 추출된 명시 주소 → Juso exact 매칭
2. 명시 좌표 + V-WORLD point-in-polygon
3. 기존 `feature.features`와 높은 신뢰도 매칭
4. 이름만 → `pending`, 검색 노출 X

**fuzzy address matching 금지** (라이브러리도 동일).

## 6. Gemini API

```python
import google.generativeai as genai

genai.configure(api_key=user_or_system_key)
model = genai.GenerativeModel('gemini-2.5-flash')

response = model.generate_content([
    {"file_data": {"file_uri": "https://youtube.com/watch?v=..."}},
    """
    이 영상에서 언급된 장소를 추출하고 다음 JSON 스키마로 응답해 주세요:
    {
      "places": [
        {
          "name": "...",
          "address": "...",
          "lat": ...,
          "lng": ...,
          "evidence": "...",
          "confidence": 0.0~1.0
        }
      ]
    }
    """
])
```

- 최대 10 video per request
- 1 FPS sampling
- private / unlisted skip
- 결과 JSON parse → `youtube_place_candidates` insert (`status='pending'`)

## 7. 운영 흐름

```
1) 운영자가 YouTube 채널 등록 → app.youtube_monitor_sources
2) RSS poll (2h) → app.youtube_video_records
3) (사용자 trigger or auto-monitor) → app.youtube_analysis_runs (queued)
4) Worker가 Gemini 호출 → 결과 parse → app.youtube_place_candidates (pending)
5) Admin /admin/youtube/candidates에서 검수 → promote or reject
6) promote 시 → 라이브러리에 feature_request 또는 직접 적재 (라이브러리 API)
```

## 8. AI agent / MCP

자세히는 [mcp-tools.md](./mcp-tools.md).

`youtube_place_import` MCP tool:

- input: video URL
- output: 추출된 candidate 목록 (`pending`)
- 항상 dry-run 가능

## 9. AI agent 체크리스트

v2 단계 진입 시:

- [ ] `app.youtube_*` 4 테이블 Alembic
- [ ] Gemini API (`google-generativeai` SDK) 통합
- [ ] YouTube RSS poll 워커 (Dagster)
- [ ] `app.youtube_place_candidates` 검수 Admin UI
- [ ] promote → 라이브러리 `feature_request` 또는 적재 호출
- [ ] PII 마스킹 (영상 내 사람 이름 / 전화번호)
- [ ] 라이선스 검토 (대표 프레임 default image 사용 시)
- [ ] `docs/integrations/gemini.md` cross-ref
