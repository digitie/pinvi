# 지도 마커와 공개 계정 화면 디자인 기준

TripMate 웹 화면은 `DESIGN.md`를 우선 디자인 기준으로 사용한다. 현재 기준은 Airbnb 계열의 흰 canvas, near-black text, Rausch accent, 부드러운 radius, 낮은 elevation이다. 웹페이지 스타일링은 Tailwind CSS 기반으로 작성한다.

예외: 지도 마커 색상은 `airbnb-marker-palette.html`의 16색 팔레트가 `DESIGN.md`보다 우선한다. 마커의 shape, radius, shadow, typography 주변 룩앤필은 `DESIGN.md`를 따르되, category/source 색상은 16색 팔레트 안에서 고른다.

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
- 로그인 정보에는 이메일, 비밀번호, 로그인 버튼, Google/Naver/Kakao 소셜 로그인 버튼, 비밀번호 찾기, 회원가입 링크를 둔다.

Mobile:

- 상단: 로그인 정보
- 하단: 축제 정보

소셜 로그인 버튼:

- 이메일 로그인 버튼 아래에 `또는` 구분선을 두고 Google, Naver, Kakao 버튼을 세로로 배치한다.
- 버튼 높이는 48px 이상, radius는 8px, 너비는 form과 같은 full-width를 사용한다.
- 버튼 label은 `Google로 계속하기`, `Naver로 계속하기`, `Kakao로 계속하기`처럼 provider와 행동을 함께 말한다.
- 접근성 label은 화면 label과 같은 의미를 유지한다. icon만 있는 버튼으로 만들지 않는다.
- Google 버튼은 흰 배경, 얇은 border, near-black text를 기본으로 한다.
- Naver 버튼은 `#03C75A` 배경과 흰 text를 기본으로 한다.
- Kakao 버튼은 `#FEE500` 배경과 near-black text를 기본으로 한다.
- provider 공식 brand asset을 사용할 수 있으면 self-host하고, 외부 CDN hotlink는 하지 않는다.
- provider client secret이나 REST API key는 프론트엔드 코드와 `NEXT_PUBLIC_*` 환경변수에 넣지 않는다.
- 버튼 클릭은 API start endpoint로 top-level navigation한다. `fetch`로 OAuth flow를 시작하지 않는다.
- provider 설정이 없으면 production에서는 버튼을 숨기고, local/dev에서는 disabled 상태와 설정 누락을 확인할 수 있게 한다.
- 관리자 로그인 화면에는 소셜 로그인 버튼을 넣지 않는다.

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

맵 마커 색상은 `airbnb-marker-palette.html`의 16색 팔레트를 기준으로 한다. 이 팔레트는 marker 색상에 한해 `DESIGN.md`보다 우선한다. 같은 지도 안에서 색이 너무 많아지지 않도록 source type과 category별 기본값을 제한하고, 16색 밖의 임의 색은 추가하지 않는다.

16색 팔레트:

| key | 이름 | hex | 권장 용도 |
| --- | --- | --- | --- |
| `rausch` | Rausch | `#FF385C` | 시그니처 / 추천 / 선택 |
| `coral` | Coral | `#FF7E5F` | 축제 / 이벤트 |
| `terracotta` | Terracotta | `#D2603A` | 자연 / 투어 |
| `amber` | Amber | `#E89B3C` | 음식 / 맛집 |
| `saffron` | Saffron | `#D9A441` | 문화 / 전시 |
| `olive` | Olive | `#8B9D52` | 차분한 자연 |
| `sage` | Sage | `#7BA889` | 소프트 그린 |
| `forest` | Forest | `#2A9D7F` | 액티비티 |
| `teal` | Teal | `#3A8B96` | 바다 / 수상 |
| `sky` | Sky | `#428BFF` | 교통 / 안내 |
| `indigo` | Indigo | `#3D5A80` | 시티 / 행정 |
| `lavender` | Lavender | `#A78AC0` | 소프트 라벤더 |
| `luxe` | Luxe | `#460479` | 프리미엄 / 특별 레이어 |
| `plus` | Plus | `#92174D` | 특별 추천 / Plus 맥락 |
| `berry` | Berry | `#B83A65` | 베리 핑크 / 보조 강조 |
| `charcoal` | Charcoal | `#3F3F3F` | Default 카테고리 |

초기 권장 매핑:

| 상태/source type | 시각 기준 | 비고 |
| --- | --- | --- |
| 사용자 저장 장소 | `charcoal` 또는 category 색 | 기본은 `charcoal`, category가 있으면 아래 category mapping 적용 |
| 선택된 장소/일정 | 원래 category 색 + ring/scale/z-index/badge | 선택 상태만 무조건 Rausch로 덮지 않음 |
| 날짜별 일정 순서 | `rausch` 또는 category 색 + order badge | 일정의 핵심 흐름은 Rausch 사용 가능 |
| draft 장소 | `charcoal` + `marker-stroked` | 저장 전 상태 |
| 축제/이벤트 | `coral` + `attraction` | 장소와 별도 레이어 |
| 자연/투어 | `terracotta`, `olive`, `sage` | 자연 맥락 |
| 음식/맛집 | `amber` + `restaurant` | 맛집 맥락 |
| 문화/전시 | `saffron` + 문화 icon | 전시/문화 맥락 |
| 액티비티 | `forest` | 활동성 맥락 |
| 해수욕장/수상 | `teal` + `beach` | 바다/수상 맥락 |
| 휴게소/교통 | `sky` + `highway-rest-area` | 도로/이동 맥락 |
| 주유소/유가 | `amber` + `fuel` | 가격/연료 맥락 |
| 공공 리포트/행정 | `indigo` + `town-hall` | 시티/행정 맥락 |
| 편의시설/기타 | `charcoal` 또는 `lavender` | 지도 피로도 낮춤 |

마커 CSS 변수는 구현 시 아래 방향을 따른다.

```css
:root {
  --tm-marker-rausch: #ff385c;
  --tm-marker-coral: #ff7e5f;
  --tm-marker-terracotta: #d2603a;
  --tm-marker-amber: #e89b3c;
  --tm-marker-saffron: #d9a441;
  --tm-marker-olive: #8b9d52;
  --tm-marker-sage: #7ba889;
  --tm-marker-forest: #2a9d7f;
  --tm-marker-teal: #3a8b96;
  --tm-marker-sky: #428bff;
  --tm-marker-indigo: #3d5a80;
  --tm-marker-lavender: #a78ac0;
  --tm-marker-luxe: #460479;
  --tm-marker-plus: #92174d;
  --tm-marker-berry: #b83a65;
  --tm-marker-charcoal: #3f3f3f;
  --tm-marker-surface: #ffffff;
  --tm-marker-icon-on-color: #ffffff;
  --tm-marker-border: rgba(0, 0, 0, 0.08);
}
```

팔레트 source of truth는 `airbnb-marker-palette.html`이다. 구현용 TypeScript constant와 CSS 변수는 이 파일의 16색과 일치해야 한다.

## Maki icon 사용 기준

맵 마커와 장소 정보 icon은 Mapbox Maki icon을 내려받아 사용한다. Maki는 지도 POI를 위한 SVG icon set이며, TripMate에서는 필요한 SVG만 `apps/web/public/map-icons/maki/`에 self-host한다.

확인 기준:

- npm package: `@mapbox/maki`
- 2026-05-07 확인 버전: `8.2.0`
- source repo: `https://github.com/mapbox/maki`
- license: `CC0-1.0`
- icon 형식: 15px x 15px SVG source

구현 기준:

- `npm install --workspace apps/web --save-dev @mapbox/maki`로 설치한다.
- `apps/web/scripts/sync-maki-icons.mjs`에서 필요한 SVG만 `apps/web/public/map-icons/maki/{iconName}.svg`로 복사한다.
- runtime에서 raw GitHub, Mapbox CDN, 외부 URL을 참조하지 않는다.
- Maki 사용을 이유로 Mapbox GL, Mapbox token, Mapbox tile provider를 추가하지 않는다.
- Lucide icon은 UI action button 전용으로 쓰고, 지도 POI marker glyph는 Maki를 우선한다.

초기 사용 후보:

| 용도 | Maki icon |
| --- | --- |
| 일반 마커 | `marker` |
| draft 마커 | `marker-stroked` |
| 일정 순서/강조 | `star` |
| 축제/이벤트 | `attraction` |
| 해수욕장 | `beach` |
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
| 행정구역/지역 리포트 | `town-hall` |
| 기타 정보 | `information` |

Maki icon은 지도 marker 내부 glyph 또는 장소 상세 보조 icon으로 사용한다. provider 원문 카테고리와 TripMate `place_categories.category_code`가 충돌하면 TripMate 카테고리를 우선한다.

## 축제 레이어 동작

축제 데이터는 장소 데이터와 별도 DB 테이블에서 관리한다. 지도에서는 별도 source layer로 다루고, 기본 상태에서는 켜지 않는다.

동작 기준:

- 지도 위 상세보기/레이어 버튼에서 `축제` checkbox를 켜면 `GET /public/festivals/map-markers` 결과를 표시한다.
- 축제 marker는 16색 팔레트의 `coral` `#FF7E5F`와 Maki `attraction` icon을 기본값으로 사용한다. 선택된 축제는 같은 coral 색을 유지하되 ring, scale, z-index, badge로 강조한다.
- marker 클릭 상세에는 축제명, 일정, 개최장소, 운영시간 또는 관련정보 텍스트, 연락처, 홈페이지, 주소를 보여준다.
- 상세의 “추가” 버튼은 로그인 사용자의 여행 날짜에 `resource_type = festival` 일정 항목을 추가한다.
- 여행 일정 타임라인은 장소만 받는 구조가 아니라 `trip_plan_items`를 사용해 장소, 축제, 향후 둘레길/드라이브 코스 같은 타입을 함께 받을 수 있게 한다.
