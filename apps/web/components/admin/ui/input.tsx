'use client';

/**
 * KTM `packages/kor-travel-map-admin/frontend/src/components/ui/input.tsx`에서 이식(T-356).
 *
 * 원문에서 바꾼 부분:
 * - **`@base-ui/react/input` 제거.** pinvi는 base-ui를 오버레이 프리미티브
 *   (dialog/alert-dialog/popover/tooltip/tabs)에만 쓴다. `InputPrimitive` → 네이티브
 *   `<input>`. base-ui `Input`은 이 자리에서 스타일 hook만 얹는 얇은 래퍼라 동작 차이가 없다.
 * - `@/lib/utils` → `@/lib/admin/cn`.
 * - `'use client'` 추가 — 값/핸들러를 받는 인터랙티브 컨트롤이다(Next.js App Router).
 * - 색 토큰 치환표만 적용(레이아웃/간격/높이/모션 클래스는 원문 그대로):
 *   `border-input`→`border-admin-control-line`, `bg-card`→`bg-canvas`,
 *   `text-text-primary`→`text-ink`, `text-text-tertiary`→`text-muted`,
 *   `bg-surface-subtle`→`bg-admin-subtle`, `border-text-secondary`→`border-body`,
 *   `text-text-secondary`→`text-body`, `border-destructive`→`border-admin-danger`.
 */
import * as React from 'react';

import { cn } from '@/lib/admin/cn';

type InputProps = Omit<React.ComponentProps<'input'>, 'size'> & {
  /** 컨트롤 높이 2종만: `default` = `h-control`(36px, 15px) · `sm` = `h-control-sm`(30px, 13.5px). */
  size?: 'sm' | 'default';
};

/**
 * 텍스트 입력 recipe (interaction-and-states §Input field states):
 * border 1px 고정(모든 상태) · hover는 배경만 · focus는 불투명 outline(즉시) · disabled/read-only는
 * opacity + cursor + 배경 3채널 · aria-invalid는 border 색 + 메시지 슬롯(FormField) 병행.
 */
function Input({ className, type, size = 'default', ...props }: InputProps) {
  return (
    <input
      type={type}
      data-slot="input"
      data-size={size}
      className={cn(
        'w-full min-w-0 rounded-control border border-admin-control-line bg-canvas px-3 text-ink transition-[color,background-color,border-color] duration-fast ease-out',
        'h-control text-sm data-[size=sm]:h-control-sm data-[size=sm]:px-2.5 data-[size=sm]:text-xs',
        'file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-xs file:font-medium file:text-ink placeholder:text-muted',
        'hover:bg-admin-subtle focus-visible:border-body focus-visible:bg-canvas focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus',
        'disabled:cursor-not-allowed disabled:bg-admin-subtle disabled:opacity-55 read-only:cursor-default read-only:bg-admin-subtle read-only:text-body',
        'aria-invalid:border-admin-danger',
        className,
      )}
      {...props}
    />
  );
}

export { Input };
export type { InputProps };
