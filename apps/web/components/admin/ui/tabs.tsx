'use client';

// kor-travel-map admin `src/components/ui/tabs.tsx`에서 이식(T-356).
//
// 원문에서 바꾼 부분과 이유:
//   1) import 경로 — `@/components/ui/tabs-variants` -> `@/components/admin/ui/tabs-variants`,
//      `@/lib/utils` -> `@/lib/admin/cn`.
//      `@base-ui/react/tabs` import는 원문 그대로다(`@base-ui/react@1.7.0`).
//   2) 색 토큰 치환: `text-text-secondary`->`text-body`, `text-text-primary`->`text-ink`,
//      `bg-card`->`bg-canvas`, `border-border`->`border-admin-line`, `bg-brand`->`bg-cta`.
//   3) KTM `@custom-variant`가 pinvi에 없어 표준 임의 variant로 치환:
//      - `data-horizontal:` / `group-data-horizontal/tabs:`
//          -> `data-[orientation=horizontal]:` / `group-data-[orientation=horizontal]/tabs:`
//      - `data-vertical:` / `group-data-vertical/tabs:`
//          -> `data-[orientation=vertical]:` / `group-data-[orientation=vertical]/tabs:`
//      - `data-active:` -> **`data-[active]:`**. 지시받은 표는 `data-[state=active]:`였지만
//        base-ui 1.7의 `getStateAttributesProps`는 boolean state key를 `data-<key>`(값 없는 속성)로
//        내보낸다 — `TabsTabState.active: boolean` -> DOM은 `data-active=""`이고 `data-state`는
//        아예 없다. `data-[state=active]:`로 두면 활성 탭 스타일이 **조용히 죽는다**(생성되는 CSS는
//        있지만 매칭되는 요소가 없다). KTM의 `@custom-variant data-active`도
//        `[data-state="active"], [data-active]:not([data-active="false"])` 두 선택자를 모두 받으므로
//        `data-[active]:`가 실제로 동작하는 쪽이다.
//   4) 그 외 높이·간격·타이포·전환 속성 열거·`data-slot` 이름은 원문 그대로다.

// Hallmark · genre: editorial-utilitarian · macrostructure: Rail-Workbench · design-system: design.md · designed-as-app

import { Tabs as TabsPrimitive } from '@base-ui/react/tabs';
import { type VariantProps } from 'class-variance-authority';

import { tabsListVariants } from '@/components/admin/ui/tabs-variants';
import { cn } from '@/lib/admin/cn';

/**
 * Tabs — 두 variant, 한 높이(`h-control` 36px):
 * - `default`(segmented): view 토글(지도/테이블)용. 트랙 `bg-admin-subtle`, 활성 = `bg-canvas` +
 *   hairline (그림자 없음).
 * - `line`(underline): 콘텐츠 탭용. hairline 베이스라인 + 활성은 ink 텍스트 + 2px brand 바(opacity만
 *   전환). 전환 속성은 색/배경/테두리로 한정 — 바는 `transition-opacity`.
 * TabsList recipe(`tabsListVariants`)는 `tabs-variants.ts`가 정본이다.
 */
function Tabs({ className, orientation = 'horizontal', ...props }: TabsPrimitive.Root.Props) {
  return (
    <TabsPrimitive.Root
      data-slot="tabs"
      data-orientation={orientation}
      className={cn('group/tabs flex gap-2 data-[orientation=horizontal]:flex-col', className)}
      {...props}
    />
  );
}

function TabsList({
  className,
  variant = 'default',
  ...props
}: TabsPrimitive.List.Props & VariantProps<typeof tabsListVariants>) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      data-variant={variant}
      className={cn(tabsListVariants({ variant }), className)}
      {...props}
    />
  );
}

/**
 * 라벨 래퍼 — `disabled`/`aria-disabled`의 흐림(`opacity-55`)을 **root가 아니라 이 자식에** 건다.
 * `opacity`는 요소 전체를 합성하므로 root에 걸면 자기 focus outline까지 55 %로 흐려진다
 * (WCAG 2.4.11의 3:1 미달). 특히 `aria-disabled`는 **포커스를 유지하는** 상태라 1.4.11의
 * "비활성 컴포넌트" 면제 대상이 아니다. `gap-[inherit]`이라 아이콘+라벨 간격은 트리거의
 * `gap-1.5`를 그대로 물려받고, `after:` brand 바와 테두리·링은 항상 100 %로 남는다.
 */
const TABS_TRIGGER_LABEL_CLASS =
  'inline-flex items-center justify-center gap-[inherit] group-disabled/tabs-trigger:opacity-55 group-aria-disabled/tabs-trigger:opacity-55';

function TabsTrigger({ className, children, ...props }: TabsPrimitive.Tab.Props) {
  return (
    <TabsPrimitive.Tab
      data-slot="tabs-trigger"
      className={cn(
        'group/tabs-trigger relative inline-flex h-full flex-1 items-center justify-center gap-1.5 rounded-control border border-transparent px-2.5 text-sm font-medium whitespace-nowrap text-body transition-[color,background-color,border-color] duration-fast ease-out select-none',
        'group-data-[orientation=vertical]/tabs:h-control group-data-[orientation=vertical]/tabs:w-full group-data-[orientation=vertical]/tabs:justify-start',
        'hover:text-ink',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus',
        // 흐림은 위 라벨 래퍼가 맡는다 — root `opacity`는 링까지 함께 흐린다.
        'disabled:cursor-not-allowed aria-disabled:cursor-not-allowed',
        'has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2',
        "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        // segmented(default): 활성 = canvas 표면 + hairline, 그림자 없음
        'group-data-[variant=default]/tabs-list:data-[active]:border-admin-line group-data-[variant=default]/tabs-list:data-[active]:bg-canvas group-data-[variant=default]/tabs-list:data-[active]:text-ink',
        // line: 배경 없음, 활성 = ink 텍스트 + brand 바
        'group-data-[variant=line]/tabs-list:rounded-none group-data-[variant=line]/tabs-list:border-0 group-data-[variant=line]/tabs-list:px-1 group-data-[variant=line]/tabs-list:data-[active]:text-ink',
        'after:pointer-events-none after:absolute after:bg-cta after:opacity-0 after:transition-opacity after:duration-fast group-data-[orientation=horizontal]/tabs:after:inset-x-0 group-data-[orientation=horizontal]/tabs:after:-bottom-px group-data-[orientation=horizontal]/tabs:after:h-0.5 group-data-[orientation=vertical]/tabs:after:inset-y-0 group-data-[orientation=vertical]/tabs:after:-right-px group-data-[orientation=vertical]/tabs:after:w-0.5 group-data-[variant=line]/tabs-list:data-[active]:after:opacity-100',
        className,
      )}
      {...props}
    >
      <span className={TABS_TRIGGER_LABEL_CLASS} data-slot="tabs-trigger-label">
        {children}
      </span>
    </TabsPrimitive.Tab>
  );
}

function TabsContent({ className, ...props }: TabsPrimitive.Panel.Props) {
  return (
    <TabsPrimitive.Panel
      data-slot="tabs-content"
      className={cn(
        'flex-1 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus',
        className,
      )}
      {...props}
    />
  );
}

export { Tabs, TabsList, TabsTrigger, TabsContent };
