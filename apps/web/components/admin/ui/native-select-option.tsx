/**
 * KTM `packages/kor-travel-map-admin/frontend/src/components/ui/native-select-option.tsx`에서
 * 이식(T-356).
 *
 * 원문에서 바꾼 부분:
 * - `@/lib/utils` → `@/lib/admin/cn`.
 * - 색 토큰 치환표만 적용: `bg-card`→`bg-canvas`, `text-text-primary`→`text-ink`.
 * - `'use client'`는 붙이지 않는다 — 상태도 이벤트 핸들러도 없는 순수 표현 요소라 server
 *   component에서도 그대로 렌더된다(client 부모가 import하면 자동으로 client 번들에 포함).
 */
import * as React from 'react';

import { cn } from '@/lib/admin/cn';

/** `<option>` — 팝업 리스트가 토큰 표면(canvas/ink)으로 렌더되도록 고정(시스템 색 리터럴 금지). */
function NativeSelectOption({ className, ...props }: React.ComponentProps<'option'>) {
  return (
    <option
      data-slot="native-select-option"
      className={cn('bg-canvas text-ink', className)}
      {...props}
    />
  );
}

export { NativeSelectOption };
