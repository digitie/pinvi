/**
 * KTM `packages/kor-travel-map-admin/frontend/src/components/ui/button-variants.ts`에서 이식(T-356).
 *
 * 원문에서 바꾼 부분 (색 토큰 치환표만 적용, 레이아웃/간격/radius/높이/타이포/모션은 원문 그대로):
 * - `bg-brand`→`bg-primary`, `bg-brand-hover`→`bg-primary-active`, `text-brand`→`text-primary`,
 *   `text-brand-foreground`→`text-on-primary`, `bg-brand-tint`→`bg-error-bg`(연한 브랜드 tint 대용)
 * - `border-brand`/`border-brand-hover`→`border-primary`/`border-primary-active`
 *   (치환표에 없는 항목. `bg-brand`/`text-brand`가 primary로 가므로 같은 역할축을 그대로 확장했다.)
 * - `bg-card`→`bg-canvas`, `text-text-primary`→`text-ink`, `text-text-secondary`→`text-body`
 * - `bg-surface-page`→`bg-admin-page`(여기서는 `text-surface-page`→`text-admin-page`),
 *   `bg-surface-subtle`→`bg-admin-subtle`, `bg-surface-muted`→`bg-admin-muted`
 * - `border-input`→`border-admin-control-line`
 * - `text-destructive`/`bg-destructive`/`bg-destructive-tint`/`border-destructive` →
 *   `text-admin-danger`/`bg-admin-danger`/`bg-admin-danger-tint`/`border-admin-danger`
 * - `outline-focus`는 pinvi에도 같은 이름이 있어 그대로 둔다.
 *
 * 구조 토큰(`rounded-control`, `h-control`, `h-control-sm`, `size-control`, `size-control-sm`)과
 * `duration-fast`(100ms)는 pinvi `app/globals.css`/preset에 같은 이름·같은 값으로 이미 있다.
 */
import { cva } from 'class-variance-authority';

/**
 * Button recipe (design.md §CTA voice / §Spacing·shape·size / §Motion).
 *
 * - 높이 2종만: `default`/`lg`/`icon`/`icon-lg` → `h-control`(36px), `sm`/`xs`/`icon-sm`/`icon-xs` →
 *   `h-control-sm`(30px). xs/lg 계열은 하위 호환 alias — 신규 코드는 default/sm/icon/icon-sm만.
 * - 8-state: rest · hover(colour) · focus-visible(불투명 outline, transition 밖 — `outline-none`을
 *   붙이지 않는다: tailwind v4에서 `--tw-outline-style: none`이 focus-visible까지 덮어 링이 사라진다) ·
 *   active(1px press) · disabled(`cursor-not-allowed`, pointer-events 유지 → `title` 사유 도달 가능) ·
 *   loading(`aria-busy` + `aria-disabled` — native disabled를 걸지 않아 포커스를 유지한다.
 *   Button `loading` prop이 spinner 오버레이) · aria-invalid · aria-expanded.
 *   그래서 disabled 계열 색은 `disabled:`/`aria-disabled:` 두 벌을 항상 같이 둔다.
 * - **흐림(opacity-55)은 이 레시피가 root에 걸지 않는다.** `opacity`는 요소 전체를 합성하므로
 *   outline(포커스 링)까지 55 %로 흐려진다 — `aria-disabled`는 포커스를 유지하는 상태라(loading·
 *   pager busy) 링이 focus vs page 대비 기준(WCAG 2.4.11 3:1) 아래로 무너진다.
 *   그래서 `Button`이 **라벨 자식**에만
 *   `group-disabled/button:opacity-55 group-aria-disabled/button:opacity-55`를 건다. 링과 경계는
 *   항상 100 %다. (bare `buttonVariants()` 소비자는 전부 `<Link>`/`<a>`라 두 상태를 갖지 않는다.)
 * - variant: `default`(brand fill, band당 1개) · `outline`(secondary CTA) · `ghost`(toolbar/table 안) ·
 *   `secondary`(선택/활성 tint chip) · `destructive`(in-page = outline + destructive text) ·
 *   `destructive-solid`(confirm dialog 안에서만 fill) · `link`.
 * - **경계는 컨트롤 hairline(`border-admin-control-line`)이다.** 장식용 `border-admin-line`은
 *   흰 배경 대비 1.6:1이라 1.4.11(3:1) 미달이라서 secondary CTA·pager가 배경에 녹는다.
 *   `secondary`는 tint 채움이 경계 구실을 못 해 `border-primary`로 테를 세운다.
 *   모든 variant가 `border border-transparent`를 깔고 있어 테를 켜도 폭이 안 변한다.
 * - alpha 팔레트 금지 → hover는 불투명 토큰(`primary-active`, `admin-subtle`, `*-tint`).
 * - `<Link className={buttonVariants()}>`도 같은 레시피(no-underline).
 */
const buttonVariants = cva(
  [
    'group/button inline-flex shrink-0 items-center justify-center rounded-control border border-transparent bg-clip-padding font-medium whitespace-nowrap no-underline select-none',
    'transition-[color,background-color,border-color,box-shadow,transform] duration-fast ease-out',
    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus',
    'active:not-aria-[haspopup]:translate-y-px',
    // opacity는 root가 아니라 라벨 자식에만(위 주석) — root에 걸면 focus outline까지 흐려진다.
    'disabled:cursor-not-allowed aria-disabled:cursor-not-allowed aria-busy:cursor-progress',
    'aria-invalid:border-admin-danger',
    "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  ].join(' '),
  {
    variants: {
      variant: {
        default:
          'bg-primary text-on-primary hover:bg-primary-active active:bg-primary-active disabled:bg-admin-muted disabled:text-ink aria-disabled:bg-admin-muted aria-disabled:text-ink',
        outline:
          'border-admin-control-line bg-canvas text-ink hover:bg-admin-subtle active:bg-admin-muted aria-expanded:bg-admin-subtle aria-expanded:text-ink disabled:border-admin-control-line disabled:bg-canvas aria-disabled:border-admin-control-line aria-disabled:bg-canvas',
        secondary:
          'border-primary bg-error-bg text-primary hover:border-primary-active hover:text-primary-active active:border-primary-active active:text-primary-active aria-expanded:border-primary aria-expanded:bg-error-bg aria-expanded:text-primary disabled:border-primary disabled:text-primary aria-disabled:border-primary aria-disabled:text-primary',
        ghost:
          'text-body hover:bg-admin-subtle hover:text-ink active:bg-admin-muted aria-expanded:bg-admin-subtle aria-expanded:text-ink disabled:bg-transparent disabled:text-body aria-disabled:bg-transparent aria-disabled:text-body',
        destructive:
          'border-admin-control-line bg-canvas text-admin-danger hover:border-admin-danger hover:bg-admin-danger-tint active:bg-admin-danger-tint aria-expanded:bg-admin-danger-tint disabled:border-admin-control-line disabled:bg-canvas aria-disabled:border-admin-control-line aria-disabled:bg-canvas',
        'destructive-solid':
          'bg-admin-danger text-on-primary hover:bg-ink hover:text-admin-page active:bg-ink active:text-admin-page disabled:bg-admin-muted disabled:text-ink aria-disabled:bg-admin-muted aria-disabled:text-ink',
        link: 'text-primary underline-offset-4 hover:text-primary-active hover:underline',
      },
      size: {
        default:
          'h-control gap-2 px-3.5 text-sm has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3',
        sm: "h-control-sm gap-1.5 px-2.5 text-xs has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2 [&_svg:not([class*='size-'])]:size-3.5",
        /** @deprecated alias of `sm` (two control heights only). */
        xs: "h-control-sm gap-1.5 px-2 text-xs has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        /** @deprecated alias of `default` (two control heights only). */
        lg: 'h-control gap-2 px-3.5 text-sm has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3',
        icon: 'size-control text-sm',
        'icon-sm': "size-control-sm text-xs [&_svg:not([class*='size-'])]:size-3.5",
        /** @deprecated alias of `icon-sm`. */
        'icon-xs': "size-control-sm text-xs [&_svg:not([class*='size-'])]:size-3.5",
        /** @deprecated alias of `icon`. */
        'icon-lg': 'size-control text-sm',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
);

export { buttonVariants };
