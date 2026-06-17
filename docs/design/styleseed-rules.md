# StyleSeed 적용 규칙 — Pinvi UI 운영 가이드

이 문서는 `https://styleseed-demo.vercel.app/llms.txt`와 연결된 full context를 읽고,
Pinvi의 기존 `DESIGN.md` / `docs/architecture/frontend.md` 기준에 맞게 적용할 핵심
규칙을 정리한다. StyleSeed는 새 브랜드 스킨이 아니라 **AI가 Pinvi UI를 만들 때
반복해서 확인해야 하는 디자인 판단 규칙**으로 쓴다.

## 1. 적용 범위

- 적용 대상: `apps/web`, `apps/mobile`, `packages/design-tokens`, UI/UX 문서.
- 비적용 대상: 백엔드 로직, DB schema, 배포 스크립트, `kor-travel-map` 책임 feature
  정규화.
- Pinvi 브랜드 기준은 계속 Airbnb 톤의 `Rausch` 단일 accent + Pretendard + 흰 canvas다.
- 지도 마커 16색(`P-01`~`P-16`)은 데이터 카테고리 표현이다. CTA, nav, 강조 UI에
  마커 색을 재사용하지 않는다.

## 2. 색상 / 토큰

- 컴포넌트에서 색상 hex를 직접 쓰지 않는다. `text-ink`, `bg-primary`,
  `border-hairline`, `text-muted` 같은 semantic token을 우선한다.
- 순검정은 쓰지 않는다. 본문과 제목은 `ink`(`#222222`) 계열을 쓴다.
- 기본 accent는 `primary` 하나다. 상태 색(success/error 등)은 회복 안내나 상태 표시
  용도에만 쓰고, 브랜드 강조처럼 남발하지 않는다.
- 그림자는 한 단계만 둔다. 카드 그림자는 최대 8% opacity로 제한한다.
- legal copy의 파란 링크(`legal-link`)와 지도 마커 팔레트는 제한된 예외다.

## 3. 레이아웃 / 리듬

- 제품 데이터와 상태 메시지는 가능한 한 명확한 surface 안에 둔다. 단, 저장소의 상위
  프론트엔드 규칙에 따라 페이지 전체를 떠 있는 card section으로 남발하거나 card 안에
  card를 중첩하지 않는다.
- 단일 표면은 `p-6` / `mx-6`, grid와 carousel은 `px-6`을 기본으로 한다. 모바일도 같은
  24px 기준을 유지한다.
- 대시보드형 화면은 같은 section type을 연속으로 반복하지 않는다. metric, chart,
  list, briefing/empty state를 섞어 높이와 밀도에 리듬을 만든다.
- 정보 밀도는 위에서 아래로 높아진다. 상단은 요약, 하단은 세부 목록과 로그다.
- 4개 KPI grid를 만들 때는 모두 같은 보조 요소를 붙이지 않는다. trend, progress,
  비교 텍스트, status dot 등을 섞는다.

## 4. 타이포그래피

- 폰트는 Pretendard + system fallback을 유지한다.
- display 숫자와 단위가 함께 있으면 2:1 크기 비율을 지킨다. 예: 48px 숫자 + 24px 단위,
  36px 숫자 + 18px 단위.
- 작은 panel, sidebar, card 내부에 hero 크기 글자를 쓰지 않는다. 화면 맥락에 맞는
  크기만 사용한다.
- viewport 너비에 따라 font size를 직접 스케일하지 않는다.
- letter spacing은 기본 0을 유지하고, 아주 작은 uppercase label만 예외적으로 넓힌다.

## 5. 상태 UI

- empty/loading/error/success 네 상태를 모두 설계한다.
- empty는 안내와 다음 행동을 포함한다. 빈 영역이나 "데이터 없음" 한 줄로 끝내지 않는다.
- loading은 모양이 정해진 목록/카드에서는 skeleton을 우선한다. 전체 화면 전환처럼
  목적지가 불명확한 대기만 spinner를 허용한다.
- error는 실패 원인과 회복 행동을 같이 보여준다. stack trace나 dead end 화면은 금지다.
- success는 짧고 조용해야 한다. routine save에 과한 축하 motion을 쓰지 않는다.

## 6. 접근성

- interactive target은 최소 44px × 44px다. 아이콘만 있는 컨트롤도 padding으로 보정한다.
- 모든 interactive element는 `focus-visible` 상태가 보여야 한다.
- 의미를 색상만으로 전달하지 않는다. 상태는 색 + 텍스트 또는 아이콘/도트를 함께 쓴다.
- heading order, 실제 `<button>`/`<a>`, 이미지 `alt`, icon-only `aria-label`을 지킨다.
- `prefers-reduced-motion`을 존중한다. custom motion은 전역 reduced-motion 규칙을 깨지 않는다.

## 7. Motion

- Pinvi는 StyleSeed의 motion vocab 중 절제된 `fast`/`normal`/`moderate` duration과
  `pinvi`/`spring` easing만 token으로 쓴다.
- hover/tap/route feedback은 100~300ms 범위로 제한한다.
- 한 element에 CSS transition과 Framer Motion을 동시에 얹지 않는다.
- full-page animation, scroll-linked motion, 500ms를 넘는 느린 motion은 기본 금지다.

## 8. Form

- label은 field 위에 둔다. placeholder는 예시일 뿐 label 대체가 아니다.
- 긴 form은 주제별 surface로 나누고, 한 화면에 primary action은 하나만 둔다.
- 검증은 blur 또는 submit 기준을 우선한다. 입력 중 매 keystroke마다 오류를 띄우지 않는다.
- 오류 문구는 복구 방법을 알려야 한다.
- submit을 비활성화할 때는 이유를 보여준다. 가능하면 submit 후 검증을 선호한다.

## 9. 적용 우선순위

1. 접근성: contrast, focus, touch target, semantic structure.
2. 저장소의 accepted ADR과 Pinvi / `kor-travel-map` 책임 경계.
3. Pinvi 기존 브랜드 기준: Airbnb 톤, Rausch 단일 accent, 16색 지도 마커 예외.
4. StyleSeed 리듬/밀도/상태/motion 규칙.
5. 화면별 미세 취향.

충돌하면 위 순서대로 판단한다. 특히 StyleSeed의 "모든 content는 card 안" 규칙은
Pinvi에서는 "제품 데이터와 상태 메시지를 명확한 surface에 둔다"로 적용하되, 상위
프론트엔드 규칙의 card 남발 금지와 card 중첩 금지를 우선한다.
