# MCP 도구 표준 (TripMate)

Claude Code / Claude Agent SDK에서 사용하는 Model Context Protocol(MCP) 도구
가이드. v1 `docs/architecture/mcp-tools.md` 정리. v2 단계 (Sprint 5+) 또는 v2.

## 1. 일반 원칙

- MCP는 TripMate 앱 DB를 직접 수정할 수 있으므로 **기본 동작은 read-only 또는
  draft 생성**
- 장소 / 주소 / provider 원문처럼 사용자 화면에 영향 주는 데이터는 즉시 confirm X —
  `pending` 또는 검수 대상 상태
- 비밀값은 MCP 설정 / 환경변수로만 주입 (절대 prompt에 노출 X)
- 좌표는 EPSG:4326 `(longitude, latitude)` 순서
- 주소 매핑: 도로명 exact → 지번 exact → 법정동 point-in-polygon → not_found.
  **fuzzy matching 기본 X**

## 2. 권한 모델

| MCP tool | 권한 |
|----------|------|
| `address_code_lookup` | 누구나 (read-only) |
| `youtube_place_import` | 운영자 + 사용자 trigger |
| `gemini_research` | 사용자 본인 (자기 키 사용) |
| `tripmate_db_admin` (v2) | CPO + admin |
| 라이브러리 `feature_search` 등 | 운영자 + 사용자 |

## 3. `address_code_lookup` (v2)

주소 / 좌표 → 행정 코드 lookup.

### 3.1 Input

```jsonc
{
  "query_type": "address" | "coord" | "code",
  "value": {
    // address
    "address_text": "부산광역시 수영구 광안동",
    // coord
    "longitude": 129.118,
    "latitude": 35.155,
    // code
    "code": "2611010100",
    "code_type": "legal_dong"
  }
}
```

### 3.2 Output

```jsonc
{
  "matched_by": "road_exact" | "jibun_exact" | "code_exact" | "point_in_polygon" | "not_found",
  "result": {
    "sido_code": "26",
    "sigungu_code": "26110",
    "legal_dong_code": "2611010100",
    "road_name_code": "...",
    "full_region_name": "부산광역시 수영구 광안동",
    "centroid": { "longitude": 129.118, "latitude": 35.155 }
  }
}
```

### 3.3 책임

- TripMate 측 MCP 또는 라이브러리 측 MCP (라이브러리에 더 가까움)
- 라이브러리 `python-kraddr-geo` 호출 — TripMate는 함수 호출 경유
- 주소 문자열 fuzzy matching X

## 4. `youtube_place_import` (v2)

YouTube URL → 장소 후보 추출.

### 4.1 Input

```jsonc
{
  "video_urls": ["https://youtube.com/watch?v=..."],
  "prompt_version": "v1",
  "dry_run": true,                     // 기본 true
  "use_user_key": true,                // 사용자 본인 키 사용 (false면 시스템 키 — admin only)
  "user_id": "uuid"
}
```

### 4.2 Output

```jsonc
{
  "candidates": [
    {
      "video_external_id": "abc123",
      "name": "광안리 해수욕장",
      "address": "...",
      "longitude": 129.118,
      "latitude": 35.155,
      "evidence": "10분 25초 화면 간판",
      "confidence": 0.85,
      "address_match_method": "road_exact"
    }
  ],
  "analysis_run_id": "uuid",
  "dry_run": true                       // dry_run=false면 app.youtube_place_candidates에 적재
}
```

### 4.3 운영

- 추출 후보를 Kakao / Naver / Google place provider에 즉시 질의 X
  (라이선스 / 제휴 / TOS)
- 일반 사용자도 dry_run으로 사용 가능 — 비밀 데이터 노출 X

## 5. MCP 서버 구현

```python
# apps/api/app/mcp/server.py
from mcp.server import Server

server = Server("tripmate-mcp")


@server.tool("address_code_lookup")
async def address_code_lookup(query_type: str, value: dict) -> dict:
    # kraddr-geo v2 REST 호출
    result = await app_state.kraddr_geo_client.lookup(query_type, value)
    return {"matched_by": result.matched_by, "result": result.as_dict()}


@server.tool("youtube_place_import")
async def youtube_place_import(
    video_urls: list[str], prompt_version: str, dry_run: bool, user_id: str
) -> dict:
    # 권한 검사 + Gemini 호출
    ...


if __name__ == "__main__":
    server.run()
```

## 6. AI agent 작업 체크리스트

새 MCP tool 추가 시:

- [ ] read-only / dry-run 기본
- [ ] 입력 schema 명시 (Pydantic)
- [ ] 권한 검사 (admin / user / CPO)
- [ ] 비밀값 환경변수만
- [ ] 좌표 lon-lat 순서
- [ ] fuzzy matching X
- [ ] `app.youtube_place_candidates` 같은 pending 테이블에만 write
- [ ] 본 문서 § 추가
- [ ] `docs/integrations/mcp-tools.md` (외부 사용자 가이드) — 작성 결정 시
