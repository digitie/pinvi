/**
 * KTM `packages/kor-travel-map-admin/frontend/src/components/ui/badge.tsx`에서 이식(T-356).
 *
 * 원문에서 바꾼 부분:
 * - **`@base-ui/react/use-render` + `merge-props` 제거.** pinvi에는 base-ui가 없다.
 *   `useRender({ defaultTagName: 'span', render, ... })` → 그냥 `<span>`을 렌더한다.
 *   `render` prop / `asLink` 같은 대체 prop은 만들지 않는다 — 링크 배지가 필요하면 호출부가
 *   `<a className={badgeVariants({ variant })}>`를 쓴다(`[a]:hover:*` 규칙이 그대로 걸린다).
 * - `useRender.ComponentProps<'span'>` → `React.ComponentPropsWithoutRef<'span'>`.
 * - base-ui `state`가 만들던 data 속성 중 `data-slot="badge"`만 리터럴로 남긴다. `data-variant`는
 *   레시피 어디서도 셀렉터로 쓰이지 않아 재현하지 않는다.
 * - `@/lib/utils` → `@/lib/admin/cn`, `@/components/ui/badge-variants` →
 *   `@/components/admin/ui/badge-variants`.
 * - `'use client'`는 붙이지 않는다 — 상태도 이벤트 핸들러도 없는 순수 표현 요소다.
 * - className 문자열은 `badge-variants.ts`에만 있고 이 파일은 색 토큰을 직접 쓰지 않는다.
 */
import * as React from 'react';

import { type VariantProps } from 'class-variance-authority';

import { badgeVariants, type BadgeVariant } from '@/components/admin/ui/badge-variants';
import { cn } from '@/lib/admin/cn';

type BadgeProps = React.ComponentPropsWithoutRef<'span'> & VariantProps<typeof badgeVariants>;

/**
 * Badge — 상태 칩 전용(design.md §Status colour semantics). count/version/key 같은 정적 metadata는
 * badge가 아니라 muted inline text로 표기한다(M22). tone 변형(success/warning/info/destructive/neutral)은
 * 불투명 `*-tint` 토큰 위에 tone 잉크 — alpha 팔레트 금지(M4/C2).
 * 한글 라벨이므로 uppercase/tracking 없음(m3), 숫자는 tabular-nums(M24).
 * recipe(`badgeVariants`)와 `BadgeVariant` 타입은 `badge-variants.ts`가 정본이다.
 */
function Badge({ className, variant = 'default', ...props }: BadgeProps) {
  return (
    <span data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge };
export type { BadgeProps, BadgeVariant };
