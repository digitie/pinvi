# `GET /search` — 통합 장소 검색 (source-tagged)

ADR-054의 통합 검색 계약 정본. feature(kor-travel-map) + address(kor-travel-geo) + 내
POI(Pinvi) + Kakao/Naver Local(표시 전용)을 **단일 `PlaceSearchResult[]`**로 합쳐 반환한다.
provider 계약·약관은 `docs/integrations/kakao-naver-local.md`, feature 경계는
`docs/integrations/kor-travel-map-rest-api.md`, 주소는 `docs/integrations/kor-travel-geo.md`.

> `/features/search`(feature-only)는 이 엔드포인트로 **대체·삭제**됐다. feature 텍스트 검색은
> 이제 `source=feature` 행으로 나온다.

## 요청

```
GET /search?q=<검색어>&limit=<n>&lat=<위도>&lon=<경도>
```

| 파라미터 | 타입 | 필수 | 비고 |
|----------|------|------|------|
| `q` | string(2–120) | 필수 | 검색어(최소 2자). 클라이언트는 디바운스·in-flight 취소 유지 |
| `limit` | int(1–50) | 아니오 | 소스별 상한(기본 10). Naver는 자체 상한 5로 clamp |
| `lat` / `lon` | float | 아니오 | **"내 주변 검색"일 때만**. 함께 와야 하며 좌표를 **Kakao에만** 전달(§위치 감사) |

인증 필요(로그인 쿠키). 좌표가 오면 위치정보 제3자 제공으로 감사된다(아래).

## 응답 — `Envelope<PlaceSearchResponse>`

```jsonc
{
  "data": {
    "results": [ /* PlaceSearchResult, internal → kakao → naver 순 */ ],
    "degraded_sources": ["kakao"]   // 5xx/타임아웃/키 미설정/쿼터로 비운 소스
  }
}
```

### `PlaceSearchResult`

| 필드 | 타입 | 채워지는 source | 비고 |
|------|------|------------------|------|
| `source` | `feature\|my_poi\|address\|kakao\|naver` | 전부 | 결과 출처 태그 |
| `name` | string | 전부 | 표시명(Naver는 `<b>` 태그 strip 후) |
| `coord` | `{lon,lat}\|null` | 대부분 | 좌표 미상이면 리스트 표시만(지도 핀 불가) |
| `feature_id` | string\|null | feature, feature-linked my_poi | 정본 feature 참조 |
| `poi_id`·`trip_id`·`trip_title` | string\|null | my_poi | 내 POI 역참조 |
| `external_id` | string\|null | kakao, naver | provider opaque id(Naver는 `link` 정규화). 저장은 external_ref만 |
| `address`·`road_address` | string\|null | address, kakao, naver | 지번/도로명 |
| `category` | string\|null | feature, kakao, naver | 표시 전용 |
| `marker_color`·`marker_icon` | string\|null | feature | 팔레트/maki |
| `provider_url` | string\|null | kakao, naver | 카카오맵/네이버 지도 back-link(attribution 필수) |
| `phone` | string\|null | kakao, naver | **표시 전용, 절대 저장 금지**(ADR-054 §7) |

## 동작

- **정렬**: internal(feature → address → my_poi) → **kakao** → **naver**. 부분 degrade에도 안정적.
- **internal-first short-circuit**: 내부 결과 수 ≥ `PINVI_PLACE_SEARCH_INTERNAL_THRESHOLD`(K, 기본 5)
  이면 Kakao/Naver를 **호출하지 않는다**(쿼터 방어, §쿼터).
- **degraded_sources**: 한 소스가 5xx/타임아웃/키 미설정/쿼터/비활성이면 해당 소스명만 담고
  나머지로 `200`을 반환한다. 검색 전체를 실패시키지 않는다. provider 비활성(`*_ENABLED=false`)도
  `kakao`/`naver`를 degraded에 넣는다.
- **표시 전용**: Kakao/Naver 응답의 provider 파생 콘텐츠(phone/address/category/title)는 DB에
  persist하거나 다른 서비스로 forward하지 않는다. POI/feature-request로 저장되는 것은
  user-authored name+coord+note + opaque `external_ref{provider,external_id,deep_link_url}`뿐이다.

## 위치 감사 (위치정보 제3자 제공, ADR-054 §9)

`lat`/`lon`이 함께 오면(=“내 주변 검색”) 핸들러가 `request.state.location_audit_coord`를 세팅하고,
`middleware/location_audit.py`가 `/search` → `third_party_place_search`로 적재한다. 좌표는
Kakao에만 전달하며(Naver는 좌표 파라미터 없음), 좌표 없는 키워드 검색은 감사 대상이 아니다.
좌표 전달은 기존 위치 동의 flow 뒤에 게이트한다(`docs/compliance/lbs-act.md`).

## 관련

- `docs/integrations/kakao-naver-local.md` — Kakao/Naver Local provider 계약·약관·attribution·쿼터.
- `docs/decisions.md` — ADR-054(외부 provider 표시 전용), ADR-056(detail-card enrichment).
