# 지도 마커와 공개 계정 화면 디자인 기준

TripMate 웹 화면은 `DESIGN.md`를 우선 디자인 기준으로 사용한다. 현재 기준은 Airbnb 계열의 흰 canvas, near-black text, Rausch accent, 부드러운 radius, 낮은 elevation이다. 웹페이지 스타일링은 Tailwind CSS 기반으로 작성한다.

## 화면 디자인 기준

| 항목 | 기준 |
| --- | --- |
| 기본 배경 | 흰색 또는 아주 옅은 `#f7f7f7` |
| 본문 글자 | `#222222` |
| 보조 글자 | `#6a6a6a` |
| 주요 CTA | Rausch `#ff385c` |
| 버튼 radius | 8px |
| 카드 radius | 14px 안팎. 단, AGENTS 기준에 맞춰 반복 카드 외 page section을 카드처럼 감싸지 않는다 |
| border | `#dddddd`, `#ebebeb` |
| shadow | 낮은 단일 shadow tier만 사용 |
| typography | letter spacing 0, viewport 폭 기반 font-size 스케일링 금지 |

새 public 화면, 로그인 화면, 가입 화면은 어두운 hero, 과한 gradient, 장식용 blob을 기본값으로 쓰지 않는다. 축제, 장소, 지도처럼 실제 데이터가 중심인 화면은 정보를 바로 읽을 수 있게 만든다.

## 로그인 화면 기준

사용자 로그인 화면은 관리자 로그인과 분리한다.

Desktop:

- 좌측: 축제 정보 패널
- 우측: 로그인 정보 패널
- 로그인 정보에는 이메일, 비밀번호, 로그인 버튼, 비밀번호 찾기, 회원가입 링크를 둔다.

Mobile:

- 상단: 로그인 정보
- 하단: 축제 정보

축제 정보:

- 1월부터 12월까지 월 탭을 가로로 보여준다.
- 기본값은 현재 KST 기준 월이다.
- 월 탭을 누르면 해당 월의 축제를 보여준다.
- 첨부 레퍼런스처럼 월 탭 아래에는 썸네일이 있는 세로 카드 리스트를 둔다. 큰 히어로/카드 그리드보다 빠르게 훑는 구조를 우선한다.
- 축제 카드에는 월 badge, 축제명, 기간, 위치, 기준 날짜를 넣는다.
- 각 월은 계절감을 주되, DESIGN.md의 흰 canvas와 Rausch CTA를 해치지 않는 연한 배경색을 사용한다.

계절 배경 기준:

| 계절 | 월 | 배경 방향 |
| --- | --- | --- |
| 봄 | 3, 4, 5 | 밝은 꽃/연두 계열 tint |
| 여름 | 6, 7, 8 | 따뜻한 coral/sun tint |
| 가을 | 9, 10, 11 | amber/leaf tint |
| 겨울 | 12, 1, 2 | 차가운 blue/mist tint |

## 가입 화면 기준

사용자 가입 화면은 관리자 화면과 분리하고, 일반 사용자 계정 생성 흐름으로 보이게 한다.

Desktop:

- 좌측: TripMate 브랜드와 짧은 안내 문구
- 우측: 회원가입 form

Mobile:

- 상단: 브랜드와 안내
- 하단: 회원가입 form

폼 기준:

- 입력 필드는 56px 높이, 8px radius, `#dddddd` border를 사용한다.
- focus는 `#222222` border만 사용하고 과한 glow를 쓰지 않는다.
- primary CTA는 Rausch `#ff385c`를 사용한다.
- 성공/오류 메시지는 form 아래에 hairline border가 있는 작은 상태 block으로 표시한다.
- 일반 가입 화면에 관리자 사용자 화면 링크를 노출하지 않는다.

문구 기준:

- 가입 화면의 보조 문구는 시스템 설명보다 사용자가 바로 이해할 수 있는 짧은 가치나 다음 행동을 우선한다.
- “이메일은 로그인 식별자로 사용됩니다”, “이메일 인증을 마치면 여행 계획과 저장한 장소를 이어서 관리할 수 있습니다”처럼 기능 설명은 화면 기본 문구로 쓰지 않는다.
- 추천 톤은 “일정과 장소를 한곳에 모아두세요”, “필수 정보부터 빠르게”처럼 1문장, 20자 안팎의 표현이다.

## 지도 마커 팔레트

맵 마커 색상은 `airbnb-marker-palette.html`의 16색 팔레트를 기준으로 한다. 공통 primary marker는 Rausch `#ff385c`를 사용한다. 같은 지도 안에서 색이 너무 많아지지 않도록 사용자 일정, 추천 POI, 시스템 데이터 source type별로 색상 사용 범위를 제한한다.

초기 권장 매핑:

| source type | 색상 기준 | 비고 |
| --- | --- | --- |
| 사용자 저장 장소 | Rausch `#ff385c` | 가장 높은 우선순위 |
| 축제/이벤트 | coral/red 계열 `#ff5a5f` | 장소와 별도 레이어. Maki `music` |
| 기상청 추천 여행코스 | mint/green 계열 | 추후 확정 전까지 별도 source type으로만 구분 |
| 휴게소/교통 | blue 계열 | 도로/이동 맥락 |
| 주유소/유가 | amber 계열 | 가격/연료 맥락 |
| 의료/약국 | red 계열 | 안전/응급 맥락 |
| 편의시설 | neutral/gray 계열 | 지도 피로도 낮춤 |

정확한 hex 목록은 팔레트 HTML을 유지하고, 구현 시 CSS 변수 또는 TypeScript constant로 승격한다.

## Maki icon 사용 기준

맵 마커와 장소 정보 icon은 Mapbox Maki icon을 내려받아 사용한다. Maki는 지도 POI를 위한 오픈소스 icon set이며, TripMate에서는 SVG asset을 `apps/web/public/maki/`에 둔다.

초기 사용 후보:

| 용도 | Maki icon |
| --- | --- |
| 일반 마커 | `marker` |
| 축제/공연 | `music`, `theatre` |
| 박물관/미술관 | `museum` |
| 캠핑장 | `campsite` |
| 수목원/정원 | `garden` |
| 음식점 | `restaurant` |
| 주유소 | `fuel` |
| 주차장 | `parking` |
| 병원 | `hospital` |
| 약국 | `pharmacy` |
| 화장실 | `toilet` |
| 도서관 | `library` |

Maki icon은 지도 marker 내부 glyph 또는 장소 상세 보조 icon으로 사용한다. provider 원문 카테고리와 TripMate `place_categories.category_code`가 충돌하면 TripMate 카테고리를 우선한다.

## 축제 레이어 동작

축제 데이터는 장소 데이터와 별도 DB 테이블에서 관리한다. 지도에서는 별도 source layer로 다루고, 기본 상태에서는 켜지 않는다.

동작 기준:

- 지도 위 상세보기/레이어 버튼에서 `축제` checkbox를 켜면 `GET /public/festivals/map-markers` 결과를 표시한다.
- 축제 marker는 coral/red 계열 `#ff5a5f`와 Maki `music` icon을 기본값으로 사용한다.
- marker 클릭 상세에는 축제명, 일정, 개최장소, 운영시간 또는 관련정보 텍스트, 연락처, 홈페이지, 주소를 보여준다.
- 상세의 “추가” 버튼은 로그인 사용자의 여행 날짜에 `resource_type = festival` 일정 항목을 추가한다.
- 여행 일정 타임라인은 장소만 받는 구조가 아니라 `trip_plan_items`를 사용해 장소, 축제, 향후 둘레길/드라이브 코스 같은 타입을 함께 받을 수 있게 한다.
