'use client';

/**
 * KTM `packages/kor-travel-map-admin/frontend/src/components/ui/textarea.tsx`에서 이식(T-356).
 *
 * 원문에서 바꾼 부분:
 * - `@/lib/utils` → `@/lib/admin/cn`. (원문도 네이티브 `<textarea>`라 base-ui 의존은 없었다.)
 * - `'use client'` 추가 — 값/핸들러를 받는 인터랙티브 컨트롤이다(Next.js App Router).
 * - 색 토큰 치환표만 적용(`min-h-24`/`resize-y`/간격/모션은 원문 그대로):
 *   `border-input`→`border-admin-control-line`, `bg-card`→`bg-canvas`,
 *   `text-text-primary`→`text-ink`, `text-text-tertiary`→`text-muted`,
 *   `bg-surface-subtle`→`bg-admin-subtle`, `border-text-secondary`→`border-body`,
 *   `text-text-secondary`→`text-body`, `border-destructive`→`border-admin-danger`.
 */
import * as React from 'react';

import { cn } from '@/lib/admin/cn';

/**
 * Textarea recipe = Input recipe + `resize-y` + `min-h-24` (interaction-and-states §Specific
 * control overrides). border 1px 고정, focus는 불투명 outline(즉시), disabled는 3채널.
 */
function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        'min-h-24 w-full min-w-0 resize-y rounded-control border border-admin-control-line bg-canvas px-3 py-1.5 text-sm text-ink transition-[color,background-color,border-color] duration-fast ease-out',
        'placeholder:text-muted hover:bg-admin-subtle focus-visible:border-body focus-visible:bg-canvas focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus',
        'disabled:cursor-not-allowed disabled:bg-admin-subtle disabled:opacity-55 read-only:cursor-default read-only:bg-admin-subtle read-only:text-body',
        'aria-invalid:border-admin-danger',
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
