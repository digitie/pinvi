/**
 * KTM `packages/kor-travel-map-admin/frontend/src/components/ui/tabs-variants.ts`에서 이식(T-356).
 *
 * 원문에서 바꾼 부분과 이유 (구조 토큰 `h-control`/`rounded-control`은 pinvi에도 같은 이름·값):
 * 1) 색 토큰 치환: `text-text-secondary`->`text-body`, `bg-surface-subtle`->`bg-admin-subtle`,
 *    `border-border`->`border-admin-line`.
 * 2) `group-data-vertical/tabs:` -> `group-data-[orientation=vertical]/tabs:`. 원문은 KTM
 *    globals.css의 `@custom-variant data-vertical`(`&:where([data-orientation="vertical"])`)에
 *    의존하는데 pinvi에는 그 variant가 없다. 선택자·의미가 같은 표준 임의 variant로 바꿨다.
 */
/* Hallmark · genre: editorial-utilitarian · macrostructure: Rail-Workbench · design-system: design.md · designed-as-app */
import { cva } from 'class-variance-authority';

/**
 * TabsList recipe — 두 variant, 한 높이(`h-control` 36px):
 * - `default`(segmented): view 토글(지도/테이블)용. 트랙 `bg-admin-subtle`, 활성 = `bg-canvas` +
 *   hairline (그림자 없음).
 * - `line`(underline): 콘텐츠 탭용. hairline 베이스라인 + 활성은 ink 텍스트 + 2px brand 바.
 *
 * 컴포넌트 파일(`tabs.tsx`)은 컴포넌트만 export한다(react-refresh only-export-components).
 */
export const tabsListVariants = cva(
  'group/tabs-list inline-flex w-fit items-center justify-center text-body group-data-[orientation=vertical]/tabs:h-fit group-data-[orientation=vertical]/tabs:flex-col group-data-[orientation=vertical]/tabs:items-stretch',
  {
    variants: {
      variant: {
        default:
          'h-control gap-0.5 rounded-control bg-admin-subtle p-0.5 group-data-[orientation=vertical]/tabs:h-fit',
        line: 'h-control gap-4 rounded-none border-b border-admin-line bg-transparent p-0 group-data-[orientation=vertical]/tabs:border-r group-data-[orientation=vertical]/tabs:border-b-0',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);
