/**
 * KTM `packages/kor-travel-map-admin/frontend/src/components/ui/badge-variants.ts`에서 이식(T-356).
 *
 * 원문에서 바꾼 부분 (색 토큰 치환표만 적용, `h-6`/`px-2`/`text-2xs`/`rounded-control`/전환 속성
 * 열거는 원문 그대로):
 * - `bg-brand`→`bg-primary`, `bg-brand-hover`→`bg-primary-active`, `text-brand`→`text-primary`,
 *   `text-brand-foreground`→`text-on-primary`, `bg-brand-tint`→`bg-error-bg`
 * - `border-brand`→`border-primary` (치환표에 없는 항목. `bg-brand`/`text-brand`가 primary로
 *   가므로 같은 역할축을 그대로 확장했다.)
 * - `bg-card`→`bg-canvas`, `border-border`→`border-admin-line`,
 *   `text-text-secondary`→`text-body`, `text-text-primary`→`text-ink`
 * - `bg-surface-subtle`→`bg-admin-subtle`, `bg-surface-muted`→`bg-admin-muted`
 * - `text-success`/`bg-success-tint`/`border-success` → `*-admin-success` 계열,
 *   warning/info/destructive도 같은 방식(`destructive`→`admin-danger`).
 * - `outline-focus`는 pinvi에도 같은 이름이 있어 그대로 둔다.
 */
import { cva, type VariantProps } from 'class-variance-authority';

/**
 * Badge recipe — 상태 칩 전용(design.md §Status colour semantics). count/version/key 같은 정적
 * metadata는 badge가 아니라 muted inline text로 표기한다(M22). tone 변형(success/warning/info/
 * destructive/neutral)은 불투명 `*-tint` 토큰 위에 tone 잉크 — alpha 팔레트 금지(M4/C2).
 * 한글 라벨이므로 uppercase/tracking 없음(m3), 숫자는 tabular-nums(M24).
 *
 * 컴포넌트 파일(`badge.tsx`)은 컴포넌트만 export한다(react-refresh only-export-components) —
 * recipe는 button-variants.ts와 같은 방식으로 여기 둔다. 링크 배지는 `<a className={badgeVariants(
 * { variant })}>`로 호출부가 직접 만든다.
 *
 * 전환 속성은 열거한다(`transition-[color,background-color,border-color]`). tailwind v4의
 * `transition-colors`는 `outline-color`를 포함해서 링크 배지(`<a>`)의 포커스 링이 100ms 동안
 * 페이드인 되는데, design.md §Focus는 "링은 전환 대상이 아니라 즉시"로 못박고 있다.
 */
export const badgeVariants = cva(
  'group/badge inline-flex h-6 w-fit shrink-0 items-center justify-center gap-1 rounded-control border border-transparent px-2 text-2xs leading-none font-medium whitespace-nowrap tabular-nums transition-[color,background-color,border-color] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 aria-invalid:border-admin-danger [&>svg]:pointer-events-none [&>svg]:size-3!',
  {
    variants: {
      variant: {
        default: 'bg-primary text-on-primary [a]:hover:bg-primary-active',
        secondary: 'bg-error-bg text-primary [a]:hover:border-primary',
        destructive: 'bg-admin-danger-tint text-admin-danger [a]:hover:border-admin-danger',
        outline:
          'border-admin-line bg-canvas text-body [a]:hover:bg-admin-subtle [a]:hover:text-ink',
        ghost: 'text-body [a]:hover:bg-admin-subtle [a]:hover:text-ink',
        link: 'text-primary underline-offset-4 hover:underline',
        success: 'bg-admin-success-tint text-admin-success [a]:hover:border-admin-success',
        warning: 'bg-admin-warning-tint text-admin-warning [a]:hover:border-admin-warning',
        info: 'bg-admin-info-tint text-admin-info [a]:hover:border-admin-info',
        neutral: 'bg-admin-subtle text-body [a]:hover:bg-admin-muted [a]:hover:text-ink',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

export type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>['variant']>;
