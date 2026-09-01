'use client';

/**
 * KTM `packages/kor-travel-map-admin/frontend/src/components/ui/native-select.tsx`에서 이식(T-356).
 *
 * 원문에서 바꾼 부분:
 * - `@/lib/utils` → `@/lib/admin/cn`. (원문도 네이티브 `<select>`라 base-ui 의존은 없었다.)
 * - `'use client'` 추가 — 값/핸들러를 받는 인터랙티브 컨트롤이다(Next.js App Router).
 * - 색 토큰 치환표만 적용(레이아웃/`pr-9`/chevron 위치/모션은 원문 그대로):
 *   `border-input`→`border-admin-control-line`, `bg-card`→`bg-canvas`,
 *   `text-text-primary`→`text-ink`, `text-text-tertiary`→`text-muted`,
 *   `text-icon-default`→`text-muted`, `bg-surface-subtle`→`bg-admin-subtle`,
 *   `border-text-secondary`→`border-body`, `bg-brand`→`bg-primary`,
 *   `text-brand-foreground`→`text-on-primary`, `border-destructive`→`border-admin-danger`.
 */
import * as React from 'react';

import { ChevronDownIcon } from 'lucide-react';

import { cn } from '@/lib/admin/cn';

type NativeSelectProps = Omit<React.ComponentPropsWithRef<'select'>, 'size'> & {
  /** 컨트롤 높이 2종만: `default` = `h-control`(36px) · `sm` = `h-control-sm`(30px). */
  size?: 'sm' | 'default';
};

/**
 * Native `<select>` + styled wrapper (a11y는 브라우저 것 그대로). Input과 같은 recipe:
 * border 1px 고정 · hover 배경만 · 불투명 focus outline · disabled 3채널(opacity/cursor/배경).
 * 우측 chevron 슬롯(`pr-9`)은 항상 예약.
 */
function NativeSelect({ className, size = 'default', ref, ...props }: NativeSelectProps) {
  return (
    <div
      className={cn(
        'group/native-select relative w-fit has-[select:disabled]:opacity-55',
        className,
      )}
      data-slot="native-select-wrapper"
      data-size={size}
    >
      <select
        data-slot="native-select"
        data-size={size}
        ref={ref}
        className={cn(
          'w-full min-w-0 appearance-none rounded-control border border-admin-control-line bg-canvas pr-9 pl-3 text-ink transition-[color,background-color,border-color] duration-fast ease-out select-none',
          'h-control text-sm data-[size=sm]:h-control-sm data-[size=sm]:pl-2.5 data-[size=sm]:text-xs',
          'selection:bg-primary selection:text-on-primary placeholder:text-muted',
          'hover:bg-admin-subtle focus-visible:border-body focus-visible:bg-canvas focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus',
          'disabled:cursor-not-allowed disabled:bg-admin-subtle',
          'aria-invalid:border-admin-danger',
        )}
        {...props}
      />
      <ChevronDownIcon
        className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-muted select-none group-data-[size=sm]/native-select:right-2.5 group-data-[size=sm]/native-select:size-3.5"
        aria-hidden="true"
        data-slot="native-select-icon"
      />
    </div>
  );
}

export { NativeSelect };
export type { NativeSelectProps };
