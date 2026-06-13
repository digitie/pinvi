# MCP 후보 도구 가이드 (비정본)

> **정본**: Pinvi가 외부로 노출하는 MCP 서버 계약은
> [`docs/architecture/mcp-server.md`](./mcp-server.md)가 단일 진실이다(ADR-019).
> Sprint 6 1차 외부 MCP는 `list_trips`, `get_trip`, `list_pois`,
> `search_features`, `get_user_profile` 5개 read-only tool만 제공한다.

본 문서는 v1에서 넘어온 후보 tool 아이디어와 구현 체크리스트를 보존한다. 아래 도구는
ADR-019 1차 외부 MCP에 자동 포함되지 않는다. Pinvi 외부 MCP에 추가하려면
ADR-019 amendment 또는 후속 ADR, scope 설계, 사용자 UI/보안 검토가 필요하다.

## 1. 일반 원칙

- 외부 MCP 1차는 **read-only만** 허용한다. draft 생성, pending 적재, admin DB 작업은
  future 후보이며 별도 ADR 없이는 노출하지 않는다.
- 장소 / 주소 / provider 원문처럼 사용자 화면에 영향 주는 데이터는 즉시 confirm X —
  `pending` 또는 검수 대상 상태
- 비밀값은 MCP 설정 / 환경변수로만 주입 (절대 prompt에 노출 X)
- 좌표는 EPSG:4326 `(longitude, latitude)` 순서
- 주소 매핑: 도로명 exact → 지번 exact → 법정동 point-in-polygon → not_found.
  **fuzzy matching 기본 X**

## 2. 권한 모델

| 후보 tool | 상태 | 권한 기준 |
|----------|------|----------|
| `address_code_lookup` | 후보. 구현 시 `kor-travel-geo` v2 REST 경유 | 사용자 본인 read-only |
| `youtube_place_import` | 후보. dry-run 또는 pending 후보 적재만 | 운영자 + 사용자 trigger |
| `gemini_research` | 후보. 사용자 본인 키 사용 | 사용자 본인 |
| `pinvi_db_admin` | 외부 MCP 금지. Admin HTTP/UI로만 처리 | CPO + admin |
| `search_features` | ADR-019 1차 정본 tool | 사용자 본인 read-only |

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

- Pinvi 측 MCP 또는 kor-travel-geo 측 MCP (주소 데이터 소유 서비스에 더 가까움)
- Pinvi에서 제공할 때도 `kor-travel-geo` **v2 REST**를 호출한다. `kor_travel_geo`
  in-process 함수 호출은 사용자 대면/MCP 경로에서 쓰지 않는다(ADR-025).
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

- 추출 후보를 외부 place/search provider에 즉시 질의 X
  (라이선스 / 제휴 / TOS)
- 일반 사용자도 dry_run으로 사용 가능 — 비밀 데이터 노출 X

## 5. 후보 tool 구현 예시

아래 예시는 후보 tool 구현 감각을 남긴 것이다. `apps/api/app/mcp/server.py`의 실제
등록 tool 목록과 schema는 `mcp-server.md` §4를 따른다.

```python
# candidate only — apps/api/app/mcp/server.py 정본이 아님
from mcp.server import Server

server = Server("pinvi-candidate-tools")


@server.tool("address_code_lookup")
async def address_code_lookup(query_type: str, value: dict) -> dict:
    # kor-travel-geo v2 REST 호출
    result = await app_state.kor_travel_geo_client.lookup(query_type, value)
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
