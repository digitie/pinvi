# Provider 정책과 TODO

이 문서는 현재 구현되지 않았거나 제한적으로만 쓰는 provider/API의 정책과 TODO를 모은다. 구현된 ETL 상세는 다른 `docs/data-sources/*.md` 문서를 따른다.

## Kakao/Naver/Google 장소 provider

현재 상태:

- Kakao Map JavaScript SDK는 지도 UX의 기본 지도 provider로 계획되어 있다.
- Kakao Local API 장소 검색 adapter는 제품 불변조건상 우선 provider지만, 현재 문서 기준에서는 실제 adapter 구현 전 계약 정리 단계다.
- Naver/Google/일반 검색 조합은 정책 검토 후 확장한다.

저장 정책:

- 외부 provider 원문 전체를 장기 저장하지 않는다.
- Kakao 응답은 내부 정규화 필드 추출과 TTL cache 위주로 처리한다.
- Naver Open API 검색 결과는 장기 저장용 원본 DB로 삼지 않는다.
- Google `place_id` 외 Maps Content는 장기 저장 대상으로 가정하지 않는다.
- Google Places/Geocoding 콘텐츠를 비 Google 지도 위에 결합 표시하지 않는다.
- provider별 출처와 재조회 시각은 남긴다.

참고 URL:

- Kakao Local 공통: `https://developers.kakao.com/docs/ko/local/common`
- Kakao Local 개발가이드: `https://developers.kakao.com/docs/ko/local/dev-guide`
- Naver Local Search: `https://developers.naver.com/docs/serviceapi/search/local/local.md`
- Naver Blog Search: `https://developers.naver.com/docs/serviceapi/search/blog/blog.md`
- Naver News Search: `https://developers.naver.com/docs/serviceapi/search/news/news.md`
- Naver Encyclopedia Search: `https://developers.naver.com/docs/serviceapi/search/encyclopedia/encyclopedia.md`
- Naver Web Search: `https://developers.naver.com/docs/serviceapi/search/web/web.md`

## 한국천문연구원 KASI

상세 설계는 `docs/architecture/kasi-calendar-schema.md`에 있다. 현재 구현은 후속 작업이다.

TODO 후보:

| dataset | 설명 URL | 용도 |
| --- | --- | --- |
| `kasi_special_day` | `https://www.data.go.kr/data/15012690/openapi.do` | 공휴일/국경일/24절기 |
| `kasi_lunisolar_day` | `https://www.data.go.kr/data/15012679/openapi.do` | 음양력/간지/율리우스 적일 |
| `kasi_rise_set` | `https://www.data.go.kr/data/15012688/openapi.do` | 일출/일몰/월출/월몰 |

착수 조건:

- 여행 날짜/장소 모델과 cache key를 확정한다.
- 같은 날짜/좌표에 대한 fresh cache가 있으면 API를 다시 호출하지 않는다.
- 사용자 개인 API key 구조가 필요한 기능과 data.go.kr 공용 key 기능을 혼동하지 않는다.

## MCP 후보

현재 상태:

- `youtube_place_mcp`와 `address_code_lookup_mcp`는 TODO 후보로만 둔다.
- 별도의 사용자 지시가 있기 전까지 MCP 설계, 구현, 스캐폴딩, 의존성 추가, 테스트 추가를 하지 않는다.
- YouTube 여행 정보 수집 상세 설계는 `docs/architecture/youtube-travel-intelligence.md`에 문서화한다. 현재는 구현 전 설계 상태다.

후속 의사결정:

- 자동 YouTube 모니터링에 시스템/관리자 Gemini key를 쓸지, 사용자 개인 Gemini key만 허용할지 결정한다.
- YouTube MCP가 영상 자막만 읽을지, 댓글/설명/링크까지 읽을지 결정한다.
- YouTube 원문 중 저장 가능한 범위를 법무/정책 기준으로 결정한다.
- Gemini YouTube URL 직접 분석 실패 시 전체 영상 다운로드 fallback을 허용할지 결정한다. 현재 추천 기본값은 허용하지 않는 것이다.
- 대표 프레임 이미지를 공개 UI에 노출할지, 관리자 검수 화면에서만 사용할지 결정한다.
- 주소 코드 조회 MCP가 로컬 DB만 볼지, 운영 DB 또는 read-only replica를 볼지 결정한다.
- MCP 구현 착수 지시가 내려진 뒤 `docs/data-sources.md`, 관련 execplan, 보안/비밀정보 정책을 먼저 갱신한다.

## 향후 장소성 공공데이터 후보

새 데이터셋을 구현하기 전에는 출처, 갱신주기, 저장 정책, 주소 매핑, 카테고리 매핑, 테스트 기준을 먼저 문서화한다.

행정안전부 문화/생활/건강 계열:

- 숙박, 민박, 박물관/미술관, 전통사찰, 한옥체험업, 관광숙박업, 농어촌민박업, 영화상영관, 관광펜션업
- 전문휴양업, 관광유람선업, 공연장, 일반야영장, 종합휴양업, 관광공연장업
- 테마파크업, 일반테마파크업, 종합테마파크업, 지방문화원, 영화상영업, 관광궤도업
- 공중화장실정보, 생활_골프장, 생활_목욕장업, 전국온천현황
- 건강_약국, 건강_의료법인, 건강_의원

기타 후보:

- 건강보험심사평가원 병원정보(`opendata.hira.or.kr`)
- 행정안전부 생활안전지도
- 주차장 표준데이터
- 도서관 표준데이터
- 렌터카업체 표준데이터
- 박물관미술관 표준데이터 보강
