## Pinvi 적용 메모

본 파일은 Airbnb 톤을 설명하는 reference다. Pinvi 구현에서는
`docs/design/styleseed-rules.md`를 추가 운영 규칙으로 적용한다. 즉 단일 Rausch
accent, semantic token, 44px touch target, focus-visible ring, 상태 UI 네 가지,
reduced-motion 대응을 UI 작업 체크리스트로 삼는다. 원본 reference의 shadow 값이
10% opacity까지 보이더라도 Pinvi 토큰은 StyleSeed 기준에 맞춰 최대 8% opacity로
낮춘다.

## Overview

Airbnb is the canonical example of a generous, photography-led consumer marketplace. The base canvas is **pure white** (`{colors.canvas}` — #ffffff) with deep near-black ink (`{colors.ink}` — #222222) for headlines and body, and a single voltage of **Rausch** (`{colors.primary}` — #ff385c) carrying every primary CTA, the search-button orb, the heart save state, and inline brand links. There is no secondary brand color in mainline marketing — the **Luxe purple** (`{colors.luxe}` — #460479) and **Plus magenta** (`{colors.plus}` — #92174d) tokens are sub-brand accents that only appear inside Airbnb Luxe / Plus contexts.

Type runs **Airbnb Cereal VF** (a custom variable font Airbnb licenses), with **Circular** as the historic in-house fallback and a system stack underneath. Cereal sits at modest weights — display headlines render at 22–28px in weight 500–600, not the heavy 700+ weights that financial or enterprise systems lean on. The hero h1 ("Inspiration for future getaways") on the homepage is just 28px / 700, which would feel small on a typical SaaS page; here it works because the layout leans on photography (city collage, property cards) for visual weight rather than typographic muscle.

The shape language is **soft**. Buttons are 8px radius (`{rounded.sm}`), property cards are ~14px (`{rounded.md}`), the search bar is fully pill-shaped (`{rounded.full}`), wishlist hearts and search orbs are circles (`{rounded.full}`), and category strip rounded corners run at 32px (`{rounded.xl}`). There is essentially no hard corner anywhere except the body grid itself — every interactive element is rounded.

**Key Characteristics:**

- Single accent color: `{colors.primary}` (#ff385c — "Rausch") carries every primary CTA, the search orb, the heart save state, and the brand wordmark. Used scarcely — most pages are 90% white + ink with one or two Rausch moments.
- Custom variable type: `Airbnb Cereal VF`. Display weights sit at 500–700, body at 400. Modest weight is intentional — the system trusts photography for visual heft.
- Three-product top nav: Homes, Experiences, Services — each with a hand-illustrated 32px icon and "NEW" badges (`{component.new-tag}`) on the two newer products. Active tab uses an underline rule (`{component.product-tab-active}`).
- Pill-shaped global search bar: white surface, fully rounded (`{rounded.full}`), divided by 1px hairlines into Where / When / Who segments, terminated by a circular Rausch search orb (`{component.search-orb}`).
- Property cards are photo-first: aspect-ratio rectangles with `{rounded.md}` corner clipping, swipeable image carousel, "Guest favorite" floating badge top-left, heart icon top-right, then 4–5 lines of meta beneath.
- Editorial dropdowns (footer, language picker) are clean text columns over the white canvas — no card surface, no shadow.
- The design system caps elevation at one shadow tier (`box-shadow: rgba(0,0,0,0.02) 0 0 0 1px, rgba(0,0,0,0.04) 0 2px 6px, rgba(0,0,0,0.1) 0 4px 8px`) — used on hover-floated cards and search/account dropdowns.
- 8px base spacing system, with major sections at `{spacing.section}` (64px) — generous but not airy enough to feel editorial-magazine; the marketplace density wants more cards per scroll.

## Colors

### Brand & Accent

- **Rausch** (`{colors.primary}` — #ff385c): The single brand color. Used for primary CTA backgrounds (Reserve, Continue), the search orb, the heart save state on property cards, and inline brand links. The most recognizable color in consumer travel.
- **Rausch Active** (`{colors.primary-active}` — #e00b41): The press / pointer-down variant — slightly more saturated. Used on `{component.button-primary-active}`.
- **Rausch Disabled** (`{colors.primary-disabled}` — #ffd1da): A pale tint used on disabled CTAs.
- **Luxe Purple** (`{colors.luxe}` — #460479): Sub-brand accent for Airbnb Luxe. Only appears inside Luxe-branded surfaces — never in mainline marketing.
- **Plus Magenta** (`{colors.plus}` — #92174d): Sub-brand accent for Airbnb Plus. Same scoping as Luxe — sub-product only.

### Surface

- **Canvas** (`{colors.canvas}` — #ffffff): The default page floor for every public page. Airbnb does not have a dark mode on the public web.
- **Surface Soft** (`{colors.surface-soft}` — #f7f7f7): The lightest fill — used on disabled fields, sub-nav hover backgrounds, and the inline search filter band.
- **Surface Strong** (`{colors.surface-strong}` — #f2f2f2): Slightly heavier fill — circular icon-button surface (e.g., the breadcrumb back-arrow and listing toolbar buttons).

### Hairlines & Borders

- **Hairline** (`{colors.hairline}` — #dddddd): The default 1px border tone — search bar dividers, table separators, footer column splitters, card 1px borders.
- **Hairline Soft** (`{colors.hairline-soft}` — #ebebeb): A lighter divider used on long-scrolling editorial body separators.
- **Border Strong** (`{colors.border-strong}` — #c1c1c1): A heavier stroke used on disabled outline buttons and form input outlines after focus.

### Text

- **Ink** (`{colors.ink}` — #222222): The dominant text color on light surfaces. Display headlines, body paragraphs, primary nav links, and most inline link text. Never pure black.
- **Body** (`{colors.body}` — #3f3f3f): A secondary running-text color used inside long-form review and amenity copy where ink would feel too heavy.
- **Muted** (`{colors.muted}` — #6a6a6a): Sub-titles inside city link blocks ("Cottage rentals", "Villa rentals"), inactive product-tab labels, footer category sub-labels, "View all" links.
- **Muted Soft** (`{colors.muted-soft}` — #929292): Disabled link text. Used very sparingly.
- **Star Rating** (`{colors.star-rating}` — #222222): The same ink token — Airbnb's star icon and "4.81" rating numbers all render in ink rather than a yellow/gold color, which is a deliberate brand choice (yellow stars feel cheap in travel context).
- **On Primary** (`{colors.on-primary}` — #ffffff): White text on Rausch CTAs.

### Semantic

- **Error** (`{colors.primary-error-text}` — #c13515): Inline error text for form validation. Distinct from Rausch — slightly darker, more saturated red.
- **Error Hover** (`{colors.primary-error-text-hover}` — #b32505): Darkens on link hover.
- **Legal Link Blue** (`{colors.legal-link}` — #428bff): Inline links inside legal copy (Privacy, Terms). Only used inside the legal sub-band.

### Scrim

- **Scrim** (`{colors.scrim}` — #000000 at 50% opacity): The global modal backdrop tone — date picker, login dialog, language picker. Stored as the base hex; opacity is applied at render time.

## Typography

### Font Family

The system runs **Airbnb Cereal VF** for everything — display, body, navigation, captions, microcopy. Fallbacks walk `Circular, -apple-system, system-ui, Roboto, "Helvetica Neue", sans-serif`. **Circular** is the historic in-house typeface still kept as the first non-variable fallback; system stacks back it up.

There is no separate display family. The variable font carries the entire scale.

### Hierarchy

| Token                         | Size | Weight | Line Height | Letter Spacing     | Use                                                            |
| ----------------------------- | ---- | ------ | ----------- | ------------------ | -------------------------------------------------------------- |
| `{typography.rating-display}` | 64px | 700    | 1.1         | -1px               | Listing detail rating display ("4.81")                         |
| `{typography.display-xl}`     | 28px | 700    | 1.43        | 0                  | Homepage h1 ("Inspiration for future getaways")                |
| `{typography.display-lg}`     | 22px | 500    | 1.18        | -0.44px            | Listing detail h1 ("Close to Fethiye Aliyah Bali Beach…")      |
| `{typography.display-md}`     | 21px | 700    | 1.43        | 0                  | Section heads inside listing detail ("What this place offers") |
| `{typography.display-sm}`     | 20px | 600    | 1.20        | -0.18px            | Sub-section titles ("Things to know")                          |
| `{typography.title-md}`       | 16px | 600    | 1.25        | 0                  | City link block titles ("Wilmington", "Athens")                |
| `{typography.title-sm}`       | 16px | 500    | 1.25        | 0                  | Footer column heads ("Support", "Hosting", "Airbnb")           |
| `{typography.body-md}`        | 16px | 400    | 1.5         | 0                  | Default running-text inside listing copy                       |
| `{typography.body-sm}`        | 14px | 400    | 1.43        | 0                  | Card meta lines, dates, prices, distance text                  |
| `{typography.caption}`        | 14px | 500    | 1.29        | 0                  | Search field segment labels ("Where", "When", "Who")           |
| `{typography.caption-sm}`     | 13px | 400    | 1.23        | 0                  | Footer legal line ("© 2026 Airbnb, Inc.")                      |
| `{typography.badge}`          | 11px | 600    | 1.18        | 0                  | "Guest favorite" floating badge text                           |
| `{typography.micro-label}`    | 12px | 700    | 1.33        | 0                  | Card amenity micro-labels ("Inline 6")                         |
| `{typography.uppercase-tag}`  | 8px  | 700    | 1.25        | 0.32px (uppercase) | "NEW" badge on product nav tabs                                |
| `{typography.button-md}`      | 16px | 500    | 1.25        | 0                  | Primary CTA button labels                                      |
| `{typography.button-sm}`      | 14px | 500    | 1.29        | 0                  | Pill button labels (category strip)                            |
| `{typography.link}`           | 14px | 400    | 1.43        | 0                  | Inline body links                                              |
| `{typography.nav-link}`       | 16px | 600    | 1.25        | 0                  | Top product-nav labels (Homes, Experiences, Services)          |

### Principles

Display weights stay modest. The homepage h1 at 28px / 700 is deliberately small — it tucks under the search bar so photography and the city-link grid carry visual hierarchy. The listing-detail h1 at 22px / 500 is even quieter; the listing photo banner does the work above it.

The single typographically loud moment in the entire system is the **rating display** (`{typography.rating-display}` — 64px / 700) on listing pages. That is the only place the system trusts type alone to carry hierarchy — rating numbers are a peak trust signal, so they get the loudest treatment.

### Note on Font Substitutes

If Airbnb Cereal VF and Circular are unavailable, **Inter** is the closest open-source substitute. Adjust display headlines down by ~2% in line-height to match Cereal's slightly tighter cap height; otherwise the proportions transfer cleanly.

## Layout

### Spacing System

- **Base unit:** 4px (with 2px micro-step).
- **Tokens:** `{spacing.xxs}` 2px · `{spacing.xs}` 4px · `{spacing.sm}` 8px · `{spacing.md}` 12px · `{spacing.base}` 16px · `{spacing.lg}` 24px · `{spacing.xl}` 32px · `{spacing.xxl}` 48px · `{spacing.section}` 64px.
- **Section padding (vertical):** `{spacing.section}` (64px) for major page bands; tighter than typical SaaS marketing (80–96px) because marketplace pages need higher card density per scroll.
- **Card internal padding:** `{spacing.lg}` (24px) for `{component.host-card}` and `{component.reservation-card}`; `{spacing.base}` (16px) for property-card meta block; `{spacing.sm}` (8px) for caption / date-row gutters.
- **Gutters:** `{spacing.base}` (16px) between cards in the homepage city grid; `{spacing.lg}` (24px) inside footer column gutters; `{spacing.xs}` (4px) on dense category-strip dividers.

### Grid & Container

- **Max content width:** ~1280px centered on the homepage and editorial pages. Listing detail pages cap closer to 1080px to keep the photo banner and reservation rail readable.
- **City link grid (homepage footer):** 6-column grid at desktop with each cell housing a city name in `{typography.title-md}` and a category sub-label in `{typography.body-sm}` muted.
- **Listing detail:** 2-column with photo / amenity body on the left (~64% width) and a sticky reservation card (`{component.reservation-card}`) on the right (~32%).
- **Footer:** 3-column link list (Support / Hosting / Airbnb) at desktop, collapsing to 1-column on mobile.

### Whitespace Philosophy

The system gives editorial bands 64px of vertical breathing room but compresses card grids — property and city-link cards sit just 16px apart. The contrast is intentional: the page reads as "open hero, dense marketplace below," reinforcing the marketplace nature without overwhelming the visitor at the fold.

## Elevation

The system has essentially **one shadow tier** plus the flat baseline.

- **Flat (no shadow):** Body, hero, footer, all editorial bands — 95% of surfaces.
- **Card hover float:** `box-shadow: rgba(0, 0, 0, 0.02) 0 0 0 1px, rgba(0, 0, 0, 0.04) 0 2px 6px 0, rgba(0, 0, 0, 0.1) 0 4px 8px 0` — applied to property cards on pointer hover, the search bar at rest, and the dropdown menus (account menu, language picker, date picker). This is the single shadow definition in the entire system.
- **Modal scrim:** `{colors.scrim}` rendered at 50% opacity — the global modal backdrop. Used on date pickers, login dialogs, language picker.

There are no progressive elevation tiers — the system either has the one shadow or none. Depth comes from photography, the white-on-white surface separation, and rounded-corner clipping rather than from layered shadows.

## Components

### Buttons

**`button-primary`** — Rausch fill, white text, 8px radius, 14×24px padding, 48px height, weight 500. The most common CTA across the system: "Reserve", "Continue", "Search", account-flow primaries.

**`button-primary-active`** — The press state. Background flips to `{colors.primary-active}`. No transform, no shadow change.

**`button-primary-disabled`** — Pale Rausch tint at #ffd1da with white text. Cursor not-allowed.

**`button-secondary`** — White fill with ink text and a 1px ink outline. 8px radius. Used for "Save", "Cancel", and inverse CTAs over Rausch surfaces.

**`button-tertiary-text`** — Plain ink text, no surface, no border. Underlined on hover. Used for "Show more" type links and modal close labels.

**`button-pill-rausch`** — A pill-shaped Rausch CTA used on featured cells (e.g., "Become a host" sub-CTA) — 9999px radius, 10×20px padding, 14px label.

### Search Surface

**`search-bar-pill`** — The signature global search bar. White fill, 9999px radius, 64px height, 1px hairline 1px-shadow border. Internally divided by vertical hairline rules into `{component.search-field-segment}` cells (Where / When / Who). Each segment holds an uppercase caption label above a placeholder line in `{typography.caption}`.

**`search-orb`** — The circular Rausch orb terminating the right edge of the search bar. 48×48px, fully rounded, white magnifying-glass icon centered. The hottest single color moment on the homepage.

### Top Navigation

**`top-nav`** — White surface, 80px height, 1px bottom hairline. The Airbnb wordmark sits flush left, the three product tabs (Homes / Experiences / Services) sit in the dead center, and account utilities (host link, language globe, account menu) sit flush right.

**`product-tab-active`** — Ink label in `{typography.nav-link}`, 32px hand-illustrated icon, 2px ink underline rule beneath the icon-label pair.

**`product-tab-inactive`** — Muted label, illustrated icon, no underline. Becomes active on click.

**`new-tag`** — A tiny rounded-pill badge (`{rounded.full}`) anchored top-right of an icon, carrying the uppercase "NEW" label in `{typography.uppercase-tag}` (8px / 700 with 0.32px tracking, uppercase). Used on Experiences and Services to signal recency.

### Listing Cards

**`property-card`** — A photo-first card. 1:1 aspect-ratio image with `{rounded.md}` corner clipping, image carousel dots overlay, "Guest favorite" floating badge top-left (`{component.guest-favorite-badge}`), and a heart icon top-right (`{component.icon-button-circle}` in default outlined state, Rausch-filled when saved). Beneath the image: 4–5 lines of meta — title (`{typography.title-md}`), distance / dates (`{typography.body-sm}` muted), and price ("$X night") right-aligned.

**`property-card-photo`** — The photo plate itself, separated as a token because some surfaces (wishlist, search results) reuse just the photo without the meta block.

**`experience-card`** — A taller-aspect card (4:5) for experience listings. Same `{rounded.md}` clipping, floating "NEW" badge top-left, heart top-right, and a single-line title beneath.

**`guest-favorite-badge`** — White rounded pill (`{rounded.full}`) at 11px / 600 weight. Sits over the photo with the system's only shadow tier applied for elevation.

### Listing Detail

**`rating-display-card`** — The signature listing-detail moment. A 64px / 700 rating number ("4.81") flanked left and right by tiny laurel-wreath SVG ornaments. Beneath the rating: "Guest favorite" tagline and a row of ink stat columns. The largest typographic weight in the whole system.

**`amenity-row`** — A 1-column list of amenity icons + ink labels in `{typography.body-md}`. 12px row padding, no border between rows; section is closed by a 1px hairline divider above and below.

**`reviews-card`** — A 2-column grid of review excerpts. Each column holds an author row (avatar, name, date) above a 3-line excerpt with "Show more" tertiary link.

**`host-card`** — A white card with `{rounded.md}` rounding and 24px padding holding a host avatar, name, "Superhost" badge, response-rate stat, and a "Contact host" `{component.button-secondary}`.

**`reservation-card`** — The sticky right-rail card on listing detail pages. White surface, `{rounded.md}` rounding, 1px hairline border, 1px shadow tier elevation, 24px padding. Contains: nightly price (`{typography.display-md}` ink), date-range selector, guest-count stepper, "Reserve" primary CTA full-width, and a fee breakdown stack beneath in `{typography.body-sm}`.

### Date Picker

**`date-picker-day`** — A 40×40px circular cell carrying the day number in `{typography.body-sm}`. Default state is transparent fill, ink text.

**`date-picker-day-selected`** — Ink fill, white text, full circle (`{rounded.full}`). Range states between two selected days carry a `{colors.surface-soft}` lozenge background that connects them.

### Forms

**`text-input`** — White surface, 1px hairline outline, `{rounded.sm}` 8px radius, 56px height, 14×12px padding. Stacked label above (in `{typography.caption}` muted), placeholder text in `{typography.body-md}` muted. On focus, the border thickens to 2px ink and the border color flips to `{colors.ink}` — no glow, no ring.

### Footer

**`footer-light`** — White surface (matches the page canvas — Airbnb has no contrast footer), 48×80px padding. Three columns of link blocks (Support / Hosting / Airbnb), separated by generous 24px gutters. Each column heads with a `{typography.title-sm}` ink label and stacks `{component.footer-link}` rows in `{typography.body-sm}` ink.

**`legal-band`** — A bottom strip beneath the footer columns carrying the copyright line, language picker (globe icon + "English (US)" link), currency picker, and social icons (Facebook, X, Instagram). All text in muted `{colors.muted}` at `{typography.caption-sm}`.

## Responsive Behavior

| Name    | Width       | Key Changes                                                                                                                                                                                                                               |
| ------- | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Mobile  | < 744px     | Top nav collapses to logo + hamburger; product tabs hide behind a sheet; search bar collapses to a single tappable pill; property cards stack 1-up; city grid 1-column; listing detail collapses reservation card to a sticky bottom bar. |
| Tablet  | 744–1128px  | Top nav keeps product tabs but search bar narrows; property cards 2-up; city grid 2–3 column; reservation card stays sticky right-rail at narrower width.                                                                                 |
| Desktop | 1128–1440px | Full top nav with three product tabs centered; search bar at full pill width with all 3 segments visible; property cards 4-up; city grid 6-column; listing detail 2-column with reservation rail.                                         |
| Wide    | > 1440px    | Content width caps at 1440px on listing/search pages and ~1280px on editorial; gutters absorb the rest.                                                                                                                                   |

### Touch Targets

- Primary CTAs at minimum 48×48px (above WCAG AAA).
- Search orb is 48×48px circular — the most-tapped element on the page.
- Heart save button is 32×32px circular — borderline for AAA but compensated by a generous 12px padding inside the photo card.
- Date-picker day cells are 40×40px circular.

### Collapsing Strategy

- Top product tabs collapse into a hamburger sheet below 744px.
- Search bar's 3 segments collapse into a single-tap entry that opens a full-screen search overlay on mobile.
- Property and city-link grids drop column counts cleanly at each breakpoint — never reflow rows; always reduce columns.
- Reservation card on listing detail switches from sticky right-rail to a sticky bottom bar on mobile, carrying just the "Reserve" CTA + nightly price summary.

## Known Gaps

- **Hover state colors:** intentionally not documented per the global no-hover policy — Airbnb's actual `:hover` styling for property cards is a subtle elevation lift, but precise extraction is unreliable.
- **Loading states / skeleton screens:** not visible on the extracted surfaces.
- **Map view styling:** the search-results map uses Mapbox-tinted tiles with custom Rausch markers; not captured here.
- **Form input error states:** error text color (`{colors.primary-error-text}`) is documented, but the full input outline + helper-text combination on validation failure was not visible in the captured surfaces.
- **Sub-brand palettes:** Luxe (`{colors.luxe}`) and Plus (`{colors.plus}`) are documented as tokens, but their full sub-system (typography overrides, surface treatment) lives on separate sub-domains and is not captured here.

## Hallmark 잠금 시스템 (2026-08-18, design-system-managed)

> 이 섹션은 위 Airbnb reference를 Pinvi 웹·모바일에 **잠근** 결과다. Hallmark(`hallmark audit`/`redesign`)와
> 모든 UI 작업은 이 섹션 + `docs/design/styleseed-rules.md`를 정본으로 읽는다. 페이지마다 다른 테마·구조를 고르지
> 않는다(다양화 규칙 역전 — 페이지 간 **일관성**이 목표). 시스템을 바꾸려면 페이지에서 override하지 말고 이 섹션을 먼저 고친다.
> 근거: 2026-08-18 Hallmark 감사(13 critical · 26 major · 19 minor, `docs/journal.md`).

### Genre

**modern-minimal** — 흰 canvas, 단일 accent, sans 일관, 절제된 카드 표면, 모션 최소. (playful/editorial 아님.)

### Macrostructure family

- **마케팅(`/`)**: Narrative Workflow(1.0 계획 → 2.0 기록 → 3.0 공유) — 비대칭 hero(H2 diptych) + F4 step sequence + 하단 단일 CTA. 3장 동일 카드·뷰포트 중앙 hero 금지.
- **앱(`/trips`, `/trips/[id]`, `/map`, 설정, 파일)**: Workbench — 콘텐츠 우선, hero 없음. 컨테인먼트 1층 규칙(카드 안 카드 금지, 리스트는 hairline row divider, 패널은 `surface-soft` 1층). 상단은 요약, 아래로 갈수록 밀도↑.
- **콘텐츠(법무, 공유 뷰, 404/오류)**: Long Document — 좌정렬 문단, `max-w-[65ch]`, hairline/ink top rule, 카드·그림자 없음.
- 공개 chrome: nav **N1**(워드마크 + 최대 2 액션, `components/app/PublicChrome.tsx`), footer **Ft2**(1줄 colophon + 법무 링크). 앱 셸은 `AppShell`(활성 탭 = ink 2px 밑줄, Rausch pill 아님).

### Theme (토큰은 `@pinvi/design-tokens`가 정본 — hex/OKLCH 병기)

| 역할              | 토큰                                           | hex                                   | OKLCH                                                                   |
| ----------------- | ---------------------------------------------- | ------------------------------------- | ----------------------------------------------------------------------- |
| paper             | `canvas`                                       | #ffffff                               | oklch(100% 0 0)                                                         |
| paper-2           | `surface-soft` / `surface-strong`              | #f7f7f7 / #f2f2f2                     | oklch(97.6% 0 0) / oklch(96.1% 0 0)                                     |
| rule              | `hairline` / `hairline-soft` / `border-strong` | #dddddd / #ebebeb / #c1c1c1           | oklch(89.8% 0 0) / oklch(94% 0 0) / oklch(81.1% 0 0)                    |
| ink               | `ink` / `body` / `muted` / `muted-soft`        | #222222 / #3f3f3f / #6a6a6a / #929292 | oklch(25.2% 0 0) / oklch(36.8% 0 0) / oklch(52.4% 0 0) / oklch(66% 0 0) |
| accent(브랜드)    | `primary` (Rausch)                             | #ff385c                               | oklch(65.8% 0.231 17)                                                   |
| **cta(채운 CTA)** | `cta` / `cta-hover`                            | #e00b41 / #c8093a                     | oklch(57.7% 0.228 18.5) / oklch(53% 0.209 18.2)                         |
| focus             | `focus`                                        | #ff385c                               | oklch(65.8% 0.231 17)                                                   |
| error / success   | `error-text` / `success-text`                  | #c13515 / #1b873f                     | oklch(53.9% 0.182 33.7) / —                                             |

**대비 결정(C5)**: white 라벨을 Rausch `#ff385c` 위에 올리면 3.5:1(AA 미달)이라 **본문 크기 채운 CTA는 `cta`(#e00b41, 4.9:1)**를 쓴다. Rausch는 아이콘·워드마크·포커스 링·≥24px 텍스트 전용. 인라인 링크는 `text-ink underline`(hairline decoration → hover ink); `muted-soft`는 disabled 텍스트 전용(본문 3.1:1 미달). accent는 뷰포트당 1~2 moment(페이지당 채운 primary CTA 1개 — 마케팅은 hero, 폼은 submit; masthead·마무리 CTA·보조 액션은 secondary/ghost).

### Typography

- Display: **Pretendard Variable** 700, `tracking-tight`(-0.025em), 로만(이탤릭 헤더 금지). hero h1 `text-4xl md:text-5xl`(36/48px, viewport 스케일 없음), 섹션 h2 `text-2xl md:text-3xl`.
- Body: Pretendard Variable 400 `text-base`(16px, 입력 포함 — iOS 확대 방지). 보조 `text-sm`(14px). 12px 이하 텍스트 금지(뱃지 예외 `text-xs` 600).
- Mono(단계 번호·ref 코드): 시스템 mono 스택(`ui-monospace, "SF Mono", Menlo, Consolas, monospace`) — 로드하지 않는 웹폰트 이름을 1순위에 두지 않는다. 한글 라벨은 mono가 아니라 body.
- 한글 줄바꿈: `word-break: keep-all` + `overflow-wrap: break-word`(globals.css body).
- 로딩: npm `pretendard` dynamic subset(`@import` in globals.css, self-hosted, `font-display: swap`) — 외부 CDN 금지.

### Spacing / Shape / Elevation

- 4pt 스케일(Tailwind 기본) + `spacing.section` 64px. 표면 `p-6`/`px-6` 기준(모바일 동일 24px).
- radius: 버튼·입력 `rounded-sm`(8px), 카드 `rounded-md`(14px), pill `rounded-full`.
- 그림자 **2 티어만**: `shadow-card`(hover 카드·드롭다운) / `shadow-overlay`(모달·시트), 둘 다 ≤8% opacity. `shadow-sm/md/lg/xl` 금지. scrim `bg-scrim/50` 단일.
- z-index 이름 5단: `z-nav < z-panel < z-overlay < z-modal < z-toast`.

### Motion

- easing `ease-pinvi`(cubic-bezier(0.2,0,0,1)) 단일, duration `fast 100 / normal 200 / moderate 300`. overshoot(spring)·scale·layout 속성 애니메이션 금지. 리빌 패턴 없음(페이지는 정적으로 완성).
- `prefers-reduced-motion: reduce` 전역(≤0.01ms).
- 포커스 링은 `.focus-ring` = `focus-visible:outline-2 outline-focus outline-offset-2`(outline은 transition에 안 묶여 즉시 표시).

### Microinteractions stance

- 성공은 조용히(인라인 텍스트/`role=status`), 축하 토스트 없음. 실패는 원인 + 회복 행동. 로딩은 형태가 정해진 목록/카드는 skeleton, 인라인 액션은 버튼 스피너(라벨 유지, `aria-busy`).
- 파괴적·비가역 액션(토큰 회수·동의 철회·연결 해제·삭제) = 공용 확인 다이얼로그(`useModalDialog`, danger tone). 가역 액션 = 즉시 실행 + Undo/상태 문구. `window.confirm` 금지.
- hover 툴팁 800ms / focus 0ms. 터치 타깃 44px(`min-h-11`, `.touch-target`), `sm` 크기는 coarse pointer에서 44px 승격.

### CTA voice (`components/ui/Button.tsx`)

- Primary: `bg-cta text-on-primary` 채움, `rounded-sm`, `min-h-11 px-5 text-base font-semibold`, hover/active `bg-cta-hover`, disabled `bg-primary-disabled text-cta-hover`. 카피는 동사구("무료로 시작하기", "다시 보내기").
- Secondary: `border border-ink text-ink bg-canvas`, hover `surface-soft`. Ghost: 텍스트만. Danger: `bg-error-text`.
- 8상태 필수: default · hover · focus-visible · active · disabled(3채널) · loading · error · success(`data-state`).
- 탐색은 `ButtonLink`(`<a>`), 상태 변경은 `Button`(`<button>`) — 역할을 섞지 않는다. 입력은 `components/forms/FormField|FormSelect|FormTextArea`(`inputClassName`, 44px·16px·hint/error 단일 슬롯).

### Per-page allowances

- 마케팅 페이지: 타이포 우선. enrichment는 Tier-A CSS art / Tier-B 손그림 SVG(토큰 색만)까지. 스톡 사진·Lottie·가짜 브라우저 chrome 금지.
- 앱 페이지: enrichment 없음 — 기능이 페이지를 만든다. eyebrow(uppercase 소형 라벨) 금지, 맥락은 h1 아래 muted 1줄.
- 콘텐츠 페이지: 타이포만.
- Narrative Workflow의 단계 번호(1.0/2.0/3.0)는 순서 콘텐츠라 허용, 태그는 항상 제목 위 세로 스택.

### 페이지가 반드시 공유하는 것 / 달라도 되는 것

- 공유: 워드마크(`components/app/Wordmark.tsx` — 핀 마크 = favicon/앱 아이콘과 동일 path), accent와 배치, Pretendard, CTA voice, 입력 프리미티브, 상태 UI 4종 정책, 법무 colophon.
- 차이 허용: family 안의 macrostructure(마케팅 서브페이지가 생기면 Long Document/Split Studio 가능), hero 아키타입, 마케팅 enrichment 티어.

### 잔여 이탈(감사 기준, 후속 PR로 수렴)

`bg-white`/`text-white`/`bg-black/NN` 토큰 우회(코드모드), `shadow-lg/xl` 21곳, 44px 미달 버튼 다수, 관리자 chrome 유출(설정) — `docs/tasks.md` T-312~ 참조.

**모달 계약**(T-315, `components/ui/Dialog` + `lib/useModalDialog`): 모든 모달은 프리미티브로 뜬다 —
스택(`modalStack`)에 등록돼 **최상단 하나만** Escape/Tab을 처리하고, 포커스는 패널 안에 격납된다
(안의 버튼이 disabled/언마운트돼 포커스가 body로 떨어지면 회수). `busy`(저장 중)에는 Escape·backdrop·
닫기(×)를 **모두** 잠근다 — 닫기만 열어 두면 진행 중 요청이 취소되지 않아 닫은 모달이 되살아나거나
비멱등 POST가 중복된다(T-315 2차 리뷰 실측). 요청이 끝내 응답하지 않는 경우의 탈출구는 UI가 아니라
데이터 계층(요청 타임아웃 + in-flight 취소)이 풀어야 할 문제이며 T-316이 맡는다 — 3차 리뷰가 보여준
대로 헤더만 덮는 타임아웃이나 4xx로 표면화하는 타임아웃은 취소 계약·Idempotency-Key 계약을 깨뜨린다.
예외: `RestoreHotswapDialog`(admin schema-swap)는 body portal + 배경 `inert`를 쓰는 더 강한 격리라
아직 프리미티브 밖이다(T-316에서 수렴).

**T-314에서 해소**: `useMobileWebLayout` UA 스니핑(뷰포트·포인터 미디어쿼리로 교체), 앱 셸 회색 ground(→ `bg-canvas` + 모바일 하단 탭바), 목록 skeleton 부재(`/trips`·`/notice-plans`), 필터 탭 시맨틱(패널을 바꾸지 않는 필터는 `role=group` + `aria-pressed` + 44px). 단 **실제 패널을 전환하는** `TripDetail`·`SharedTripView`의 일자·작업 탭은 `role=tab`을 유지하는 것이 맞다.

앱 셸 크롬 계약: 고정 하단 탭바 높이는 `--app-tabbar-h`, main 하단 여백은 `.app-shell-main`이 소유한다(`py-*` 유틸과 겹치면 md 변형이 덮는다). 전체 화면 페이지는 `100dvh - 상수` 대신 셸이 흘려보내는 높이(`flex-1 min-h-0`)를 쓴다.

### Exports

```css
/* tokens.css — Tailwind 프로젝트에서는 @pinvi/design-tokens preset이 소비 지점. 이식용 요약. */
:root {
  --color-paper: oklch(100% 0 0);
  --color-paper-2: oklch(97.6% 0 0);
  --color-ink: oklch(25.2% 0 0);
  --color-ink-2: oklch(52.4% 0 0);
  --color-rule: oklch(89.8% 0 0);
  --color-accent: oklch(65.8% 0.231 17);
  --color-cta: oklch(57.7% 0.228 18.5);
  --color-cta-hover: oklch(53% 0.209 18.2);
  --color-accent-ink: oklch(100% 0 0);
  --color-focus: oklch(65.8% 0.231 17);
  --font-display: 'Pretendard Variable', Pretendard, 'Apple SD Gothic Neo', system-ui, sans-serif;
  --font-body: 'Pretendard Variable', Pretendard, 'Apple SD Gothic Neo', system-ui, sans-serif;
  --font-outlier: ui-monospace, 'SF Mono', monospace;
  --space-3xs: 0.25rem;
  --space-2xs: 0.5rem;
  --space-xs: 0.75rem;
  --space-sm: 1rem;
  --space-md: 1.5rem;
  --space-lg: 2rem;
  --space-xl: 3rem;
  --space-2xl: 4rem;
  --space-3xl: 6rem;
  --text-xs: 0.75rem;
  --text-sm: 0.875rem;
  --text-md: 1rem;
  --text-lg: 1.125rem;
  --text-xl: 1.5rem;
  --text-2xl: 1.875rem;
  --text-display: 3rem;
  --ease-out: cubic-bezier(0.2, 0, 0, 1);
  --dur-short: 200ms;
  --radius-input: 8px;
  --radius-card: 14px;
  --radius-pill: 9999px;
  --shadow-card:
    0 0 0 1px rgb(0 0 0 / 0.02), 0 2px 6px rgb(0 0 0 / 0.04), 0 4px 8px rgb(0 0 0 / 0.08);
  --shadow-overlay: 0 0 0 1px rgb(0 0 0 / 0.02), 0 8px 24px rgb(0 0 0 / 0.08);
}
```

```css
/* Tailwind v4 @theme(현재는 v3 preset `packages/design-tokens/tailwind-preset.cjs`가 정본) */
@theme {
  --color-canvas: #ffffff;
  --color-ink: #222222;
  --color-primary: #ff385c;
  --color-cta: #e00b41;
  --font-sans: 'Pretendard Variable', Pretendard, system-ui, sans-serif;
  --ease-pinvi: cubic-bezier(0.2, 0, 0, 1);
}
```

```json
{
  "color": {
    "paper": { "$value": "oklch(100% 0 0)", "$type": "color" },
    "ink": { "$value": "oklch(25.2% 0 0)", "$type": "color" },
    "accent": { "$value": "oklch(65.8% 0.231 17)", "$type": "color" },
    "cta": { "$value": "oklch(57.7% 0.228 18.5)", "$type": "color" }
  },
  "font": {
    "display": { "$value": "Pretendard Variable", "$type": "fontFamily" },
    "body": { "$value": "Pretendard Variable", "$type": "fontFamily" }
  },
  "space": { "md": { "$value": "1.5rem", "$type": "dimension" } }
}
```

```css
/* shadcn/ui 변수 매핑 */
:root {
  --background: 100% 0 0;
  --foreground: 25.2% 0 0;
  --primary: 57.7% 0.228 18.5;
  --primary-foreground: 100% 0 0;
  --muted: 97.6% 0 0;
  --muted-foreground: 52.4% 0 0;
  --border: 89.8% 0 0;
  --input: 89.8% 0 0;
  --ring: 65.8% 0.231 17;
  --radius: 8px;
}
```
