# TripMate 디자인 기준

이 문서는 Airbnb에서 관찰한 소비자 여행 marketplace의 시각 원칙을 TripMate 작업에 맞게 정리한 참고 문서다. 특정 브랜드 자산을 그대로 복제하지 않고, 흰 배경, 사진 중심 정보 구조, 부드러운 shape, 절제된 강조색 같은 UX 원칙만 참고한다.

## 문서 언어 정책

TripMate의 모든 Markdown/RST 문서는 한글로 작성한다. Design token, code identifier, 명령어, URL, provider 원문은 필요한 경우 원문을 유지한다.

## 개요

여행 소비자 서비스는 사진과 장소성이 정보 위계를 만든다. 기본 canvas는 흰색, 본문은 거의 검정에 가까운 진한 ink, primary action에는 하나의 강한 accent color를 사용한다. 강조색은 CTA, search action, saved state처럼 실제 행동에만 제한적으로 쓴다.

Typography는 과하게 무겁지 않게 운용한다. 여행 서비스에서는 큰 글자보다 사진, 장소 card, 일정 밀도가 더 많은 정보를 전달한다. Hero headline도 지나치게 크지 않게 두고, 계획 화면에서는 compact heading과 list readability를 우선한다.

Shape 언어는 부드럽게 유지한다. Button은 8px radius, card image는 12~16px radius, search bar나 icon action은 pill/circle 형태가 어울린다. 단, admin/operation 화면은 장식보다 scan density와 예측 가능한 layout을 우선한다.

## 핵심 특징

- 하나의 primary accent를 중심으로 CTA, search button, save state를 연결한다.
- 대부분의 화면은 white/ink/neutral 계열로 두고 accent 사용량을 줄인다.
- 장소 card는 사진이 먼저 보이고, 그 아래에 이름, 거리, 날짜, 가격 같은 meta를 4~5줄 안에 배치한다.
- Global search는 목적지, 날짜, 인원 같은 여행 결정 단위를 분리해 보여준다.
- Footer와 dropdown은 과한 card surface보다 명확한 text column과 hairline separator를 쓴다.
- Shadow tier는 적게 둔다. 깊이는 layer를 많이 쌓기보다 사진, 여백, border, rounded clipping으로 만든다.
- 8px 기반 spacing을 사용하되 card grid는 너무 성기지 않게 유지한다.

## 색상

### Brand와 accent

- `colors.primary`: 핵심 CTA, search action, saved state에만 사용한다.
- `colors.primary-active`: pointer-down 또는 press state에 사용한다.
- `colors.primary-disabled`: disabled CTA 배경으로 사용한다.
- Sub-brand color는 특정 campaign이나 product area 안에서만 제한적으로 사용한다.

### Surface

- `colors.canvas`: 기본 page 배경. Public web은 light mode를 기본으로 설계한다.
- `colors.surface-soft`: disabled field, hover background, inline filter band에 사용한다.
- `colors.surface-strong`: icon button surface나 강한 neutral fill에 사용한다.

### Border와 hairline

- `colors.hairline`: search divider, table separator, footer divider, card border에 사용하는 기본 1px stroke.
- `colors.hairline-soft`: 긴 editorial body의 가벼운 separator.
- `colors.border-strong`: focus 이후 input outline 또는 disabled outline button에 사용한다.

### Text

- `colors.ink`: headline, body, nav link의 기본 text.
- `colors.body`: 긴 설명문에 쓰는 secondary text.
- `colors.muted`: meta line, inactive label, footer sub-label.
- `colors.muted-soft`: disabled link text.
- `colors.on-primary`: primary CTA 위의 text.

### Semantic

- Error color는 primary accent와 구분한다. 여행 서비스의 저장/예약 CTA와 validation error가 같은 색으로 보이면 행동 의미가 흐려진다.
- Legal link나 외부 링크에는 별도 link color를 사용할 수 있지만 사용 위치를 제한한다.
- Modal backdrop은 검정 50% 전후 scrim을 기본으로 한다.

## Typography

### Font family

Public consumer 화면은 둥글고 읽기 쉬운 sans-serif를 사용한다. Brand font가 없으면 Inter 또는 system stack을 사용한다. Admin/operation 화면은 dense table과 form을 읽기 쉬운 system stack도 허용한다.

### 위계

| Token | Size | Weight | 용도 |
|---|---:|---:|---|
| `typography.display-xl` | 28px | 700 | Public main headline |
| `typography.display-lg` | 22px | 500~600 | 상세 화면 title |
| `typography.display-md` | 20~21px | 600~700 | Section heading |
| `typography.title-md` | 16px | 600 | Card title, city link title |
| `typography.body-md` | 16px | 400 | 기본 본문 |
| `typography.body-sm` | 14px | 400 | Card meta, date, price |
| `typography.caption` | 13~14px | 500 | Search segment label, form label |
| `typography.badge` | 11~12px | 600 | 작은 badge |
| `typography.button-md` | 16px | 500 | Primary button |

Display weight는 절제한다. 여행 화면에서 가장 큰 위계는 사진과 위치 정보가 담당하고, type은 흐름을 돕는다. Rating이나 가격처럼 신뢰/결정에 직접 영향을 주는 숫자만 더 크게 다룬다.

## Layout

### Spacing system

- 기본 단위는 4px, 실무 배치는 8px 배수를 선호한다.
- Major section은 48~64px vertical padding을 사용한다.
- Card 내부 padding은 16~24px 범위에서 사용한다.
- Card grid gap은 16~24px를 기본으로 한다.
- Toolbar, filter, itinerary row는 반복 사용을 고려해 더 촘촘하게 설계한다.

### Grid와 container

- Public landing/editorial content는 max width 1200~1280px 안에서 중앙 정렬한다.
- Listing/detail 화면은 사진/본문과 reservation/action rail의 2-column 구조가 적합하다.
- Planning app 화면은 sidebar, map, itinerary panel, detail drawer처럼 작업 중심 panel 구조를 사용한다.
- Mobile에서는 action rail을 sticky bottom bar나 full-screen sheet로 전환한다.

### 여백 철학

Hero와 큰 section에는 충분한 여백을 주되, card grid와 itinerary list는 scroll 효율을 위해 밀도를 유지한다. 사용자는 여행지를 탐색할 때 많은 후보를 비교하므로 한 화면에 보이는 card 수가 중요하다.

## Elevation

Shadow는 한두 단계만 사용한다.

- Flat: body, footer, 일반 section
- Low shadow: card hover, search bar, dropdown, modal content
- Scrim: modal backdrop

Depth는 복잡한 shadow stack보다 사진, border, rounded clipping, white space로 만든다.

## Component 기준

### Button

- Primary button: accent fill, white text, 8px radius, 최소 44~48px height.
- Secondary button: white fill, ink text, 1px outline.
- Tertiary action: text button 또는 icon button. Hover에서는 underline 또는 surface-soft를 사용한다.
- Pill button: filter chip, category chip, featured CTA에 사용한다.

### Search surface

Global search는 destination/date/people 같은 segment를 분리하고 마지막 action은 원형 또는 강한 primary button으로 둔다. Mobile에서는 하나의 search pill을 눌러 full-screen search flow를 열게 한다.

### Navigation

Public top nav는 logo, product tab, account utility를 명확히 분리한다. 새 product나 campaign은 작은 badge로 표시하되 layout을 흔들지 않는다.

### Listing/place card

Place card는 photo-first다. Image plate를 안정적인 aspect ratio로 고정하고, title/meta/price/rating은 아래에 정리한다. Save heart는 image 위에 떠 있어도 hit target을 충분히 확보한다.

### Detail screen

Detail 화면은 큰 사진 영역, 핵심 요약, amenity/place info, review 또는 note, 예약/저장 action rail로 구성한다. TripMate의 plan detail에서는 예약 card 대신 일정 추가, 날짜 배치, 지도 표시, 메모 action을 우선한다.

### Form

Input은 56px 내외 높이, 8px radius, 명확한 label과 helper text를 사용한다. Focus state는 border 두께나 색으로 명확히 보여주고 glow는 최소화한다.

### Footer

Footer는 과한 대비 배경보다 canvas와 이어지는 white/neutral surface를 사용한다. Link column은 Support/Hosting/Product/Legal처럼 의미 단위로 묶고 mobile에서는 1-column으로 접는다.

## Responsive behavior

| 구간 | Width | 주요 변화 |
|---|---:|---|
| Mobile | < 744px | Nav 축약, search pill 단일화, card 1-column, detail action sticky bottom |
| Tablet | 744~1128px | Card 2-column, search bar 축소, side panel 간소화 |
| Desktop | 1128~1440px | Full nav, 3~4 column card grid, detail 2-column |
| Wide | > 1440px | Content max width를 유지하고 gutter가 여백을 흡수 |

Touch target은 최소 44px, 주요 CTA는 48px 이상을 목표로 한다. Date picker day cell은 40px 이상을 유지한다.

## TripMate에 적용할 때의 주의점

- Marketing hero보다 실제 planning surface를 먼저 만든다.
- Operational/admin 화면은 card 장식보다 table density, filter, bulk action, status visibility를 우선한다.
- 지도는 full-bleed 또는 작업 panel과 결합하되 itinerary가 map 없이도 편집 가능해야 한다.
- Demo data는 sample임을 명확히 표시한다.
- Text는 여행자의 다음 결정을 돕는 표현으로 쓴다.

## 알려진 빈틈

- 실제 hover color token은 추출하지 않는다. Hover는 subtle elevation 또는 neutral fill로 충분하다.
- Loading/skeleton은 각 화면의 data density에 맞게 별도 설계한다.
- Map styling은 provider tile과 marker design에 따라 별도 문서에서 다룬다.
- Sub-brand palette는 필요할 때 별도 scope로 정의한다.
