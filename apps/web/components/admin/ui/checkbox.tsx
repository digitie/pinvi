'use client';
// kor-travel-map admin `src/components/ui/checkbox.tsx`에서 이식(T-356).
//
// 원문은 `@base-ui/react/checkbox`의 `Checkbox.Root`/`Indicator`를 쓴다. pinvi는 base-ui를
// 도입하지 않으므로(모달 프리미티브가 `lib/useModalDialog` 하나로 잠겨 있어 focus-trap/inert
// 스택이 두 벌이 되는 것을 막는다) 네이티브 `<input type="checkbox">` 기반으로 다시 만들었다.
// 시각 사양(16px + ::after 32px hit target, 상태 8종, 글리프 분리)과 className은 원문 그대로다.
//
// base-ui와의 API 차이:
//   - `indeterminate`는 DOM 속성이 아니라 프로퍼티라 ref로 직접 설정한다.
//   - 원문의 `data-[unchecked]` / `data-checked` / `data-[indeterminate]`는 base-ui가 붙이는
//     속성이다. 네이티브에서는 `:not(:checked)` / `:checked` / `data-indeterminate`로 대응한다.
//   - 글리프는 Indicator 대신 체크 상태에 따라 조건부 렌더한다(원문과 동일하게 checked=Check,
//     indeterminate=Minus로 형태를 갈라 색만으로 구분되지 않게 한다).

import * as React from 'react';
import { CheckIcon, MinusIcon } from 'lucide-react';

import { cn } from '@/lib/admin/cn';

export interface CheckboxProps extends Omit<
  React.ComponentPropsWithoutRef<'input'>,
  'type' | 'onChange'
> {
  indeterminate?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  onChange?: React.ChangeEventHandler<HTMLInputElement>;
}

const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { className, indeterminate = false, onCheckedChange, onChange, checked, ...props },
  forwardedRef,
) {
  const innerRef = React.useRef<HTMLInputElement | null>(null);

  // `indeterminate`는 속성이 아니라 프로퍼티다 — 렌더 후 직접 써야 한다.
  React.useEffect(() => {
    if (innerRef.current) innerRef.current.indeterminate = indeterminate;
  }, [indeterminate, checked]);

  const setRefs = React.useCallback(
    (node: HTMLInputElement | null) => {
      innerRef.current = node;
      if (typeof forwardedRef === 'function') forwardedRef(node);
      else if (forwardedRef) forwardedRef.current = node;
    },
    [forwardedRef],
  );

  const isChecked = Boolean(checked);

  return (
    <span className="relative inline-grid size-4 shrink-0 place-content-center">
      <input
        ref={setRefs}
        type="checkbox"
        data-slot="checkbox"
        checked={checked}
        data-indeterminate={indeterminate || undefined}
        onChange={(event) => {
          onChange?.(event);
          onCheckedChange?.(event.currentTarget.checked);
        }}
        className={cn(
          'peer relative col-start-1 row-start-1 size-4 shrink-0 appearance-none rounded-control border border-admin-control-line bg-canvas transition-[color,background-color,border-color] duration-fast ease-out',
          "after:absolute after:-inset-2 after:content-['']",
          'hover:not-checked:border-body hover:not-checked:bg-admin-subtle',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus',
          'disabled:cursor-not-allowed disabled:opacity-55',
          'aria-invalid:border-admin-danger',
          'checked:border-primary checked:bg-primary hover:checked:border-primary-active hover:checked:bg-primary-active',
          'data-[indeterminate]:border-primary data-[indeterminate]:bg-primary',
          className,
        )}
        {...props}
      />
      {/* 글리프는 input 위에 겹쳐 그린다 — 네이티브 input은 자식을 가질 수 없다.
          pointer-events-none이라 클릭/hit target은 전적으로 input이 받는다. */}
      {(isChecked || indeterminate) && (
        <span
          data-slot="checkbox-indicator"
          aria-hidden="true"
          className="pointer-events-none col-start-1 row-start-1 grid place-content-center text-on-primary [&>svg]:size-3.5"
        >
          {indeterminate ? <MinusIcon /> : <CheckIcon />}
        </span>
      )}
    </span>
  );
});

export { Checkbox };
