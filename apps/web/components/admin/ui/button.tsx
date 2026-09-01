'use client';

/**
 * KTM `packages/kor-travel-map-admin/frontend/src/components/ui/button.tsx`에서 이식(T-356).
 *
 * 원문에서 바꾼 부분:
 * - **`@base-ui/react/button` 제거.** pinvi에는 base-ui가 없다. `ButtonPrimitive` → 네이티브
 *   `<button>` + `React.forwardRef<HTMLButtonElement, ButtonProps>`. `render` prop / `asChild`는
 *   만들지 않는다 — 링크 버튼이 필요하면 호출부가 `<a className={buttonVariants(...)}>`를 쓴다.
 * - `ButtonPrimitive.Props` → `React.ComponentPropsWithoutRef<'button'>`,
 *   `ButtonPrimitive.Props['onClick']` → `React.MouseEventHandler<HTMLButtonElement>`.
 * - **`type` 기본값 `'button'` 추가.** base-ui `Button`은 `<button>`에 `type="button"`을 넣어주지만
 *   네이티브 `<button>`의 기본값은 `submit`이다. 그대로 두면 폼 안의 모든 버튼이 실수로 제출을
 *   일으키므로 base-ui와 같은 동작을 유지한다(호출부가 `type="submit"`으로 덮을 수 있다).
 * - `@/lib/utils` → `@/lib/admin/cn`, `@/components/ui/button-variants` →
 *   `@/components/admin/ui/button-variants`.
 * - `'use client'` 추가 — 이벤트 핸들러를 받는 인터랙티브 컨트롤이다(Next.js App Router).
 * - className 문자열은 `button-variants.ts`에만 있고 이 파일은 색 토큰을 직접 쓰지 않는다.
 */
import * as React from 'react';
import type { VariantProps } from 'class-variance-authority';
import { Loader2Icon } from 'lucide-react';

import { buttonVariants } from '@/components/admin/ui/button-variants';
import { cn } from '@/lib/admin/cn';

/**
 * 라벨 래퍼 — 항상 렌더한다(loading 토글 시 DOM 모양이 바뀌지 않아 폭이 흔들리지 않는다).
 * `disabled`/`aria-disabled`의 흐림은 **여기(자식)** 에만 건다: root에 `opacity`를 걸면 요소
 * 전체가 합성돼 focus outline까지 55 %로 흐려지고, aria-disabled(진행 중)는 포커스를 유지하는
 * 상태라 링이 3:1 아래로 떨어진다.
 * 스피너는 이 래퍼 밖(형제)이라 항상 100 %로 돈다 — 진행을 알리는 유일한 신호다.
 */
const BUTTON_LABEL_CLASS = 'inline-flex items-center justify-center gap-[inherit]';
const BUTTON_LABEL_DIMMED_CLASS =
  'group-disabled/button:opacity-55 group-aria-disabled/button:opacity-55';

/** aria-disabled(진행 중) 버튼의 클릭 차단 — onClick 조기 반환. */
type ButtonClickHandler = React.MouseEventHandler<HTMLButtonElement>;

/**
 * 진행 중(loading) 버튼은 native `disabled`가 아니라 `aria-disabled`라 클릭/Enter/Space가 그대로
 * 발화한다. 여기서 끊고 기본 동작까지 막아 `type="submit"`이 폼을 제출하지 못하게 한다.
 */
const blockBusyActivation: ButtonClickHandler = (event) => {
  event.preventDefault();
  event.stopPropagation();
};

type ButtonProps = React.ComponentPropsWithoutRef<'button'> &
  VariantProps<typeof buttonVariants> & {
    /**
     * 비동기 진행 중(design.md §Microinteractions — row action은 page spinner 대신 trigger의
     * loading). `aria-disabled` + `aria-busy` + inline spinner이며 native `disabled`는 걸지
     * 않는다 — disabled는 포커스를 body로 날려 방금 누른 위치를 잃게 만들기 때문이다.
     * 활성화(클릭/Enter/Space)는 onClick 조기 반환이 막는다. 라벨은 자리를 지키고(폭 불변)
     * 시각적으로만 숨겨지므로 접근성 이름은 그대로다.
     */
    loading?: boolean;
    /**
     * disabled 사유(사용자 노출 문장). disabled일 때 `title`로 붙는다 — hover로 도달 가능하고
     * (pointer-events 유지) 접근성 설명(accessible description)으로도 노출된다.
     * 인라인 노트(helper/hint)는 호출부가 함께 렌더한다.
     */
    disabledReason?: string;
  };

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    className,
    variant = 'default',
    size = 'default',
    loading = false,
    disabledReason,
    disabled,
    title,
    type = 'button',
    onClick,
    children,
    ...props
  },
  ref,
) {
  // native `disabled`는 "진짜 비활성"(호출부가 disabled를 준 경우)에만. 진행 중에는
  // `aria-disabled`만 걸어 포커스를 유지한다(둘 다 참이면 진행 중 표면이 이긴다 —
  // 방금 누른 버튼이 곧 진행 중인 버튼이라 포커스 보존이 가장 중요한 자리다).
  const nativeDisabled = Boolean(disabled) && !loading;
  const reason = disabled && !loading ? disabledReason : undefined;
  return (
    <button
      ref={ref}
      type={type}
      data-slot="button"
      data-loading={loading ? 'true' : undefined}
      aria-busy={loading || undefined}
      aria-disabled={loading || undefined}
      title={reason ?? title}
      disabled={nativeDisabled}
      onClick={loading ? blockBusyActivation : onClick}
      className={cn(buttonVariants({ variant, size }), loading && 'relative', className)}
      {...props}
    >
      {loading ? (
        <span
          aria-hidden="true"
          data-slot="button-spinner"
          className="absolute inset-0 flex items-center justify-center"
        >
          <Loader2Icon className="animate-spin" />
        </span>
      ) : null}
      <span
        data-slot="button-label"
        className={cn(
          BUTTON_LABEL_CLASS,
          // 진행 중에는 라벨이 자리를 지킨 채 시각적으로만 사라진다(접근성 이름 유지).
          // `opacity-0`이 흐림 클래스보다 낮은 specificity라 둘을 겹치지 않고 갈라 쓴다.
          loading ? 'opacity-0' : BUTTON_LABEL_DIMMED_CLASS,
        )}
      >
        {children}
      </span>
    </button>
  );
});

export { Button };
export type { ButtonProps };
