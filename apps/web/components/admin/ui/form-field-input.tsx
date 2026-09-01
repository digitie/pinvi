'use client';

import * as React from 'react';

import { HelpTip } from '@/components/admin/ui/help-tip';
import {
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
  FieldMessage,
} from '@/components/admin/ui/field';
import {
  describedBy,
  type FieldShellProps,
  requiredFieldAriaLabel,
  useFieldIds,
} from '@/components/admin/ui/form-field-shared';
import { Input } from '@/components/admin/ui/input';

/**
 * KTM `src/components/ui/form-field-input.tsx`에서 이식(T-356).
 *
 * 원문에서 바꾼 것: import 경로만(`@/components/ui/*` → `@/components/admin/ui/*`,
 * `@/components/help-tip` → `@/components/admin/ui/help-tip`). className과 배선은 원문 그대로다
 * (이 파일에는 색 토큰 문자열이 없다).
 */
type FormFieldProps = Omit<React.ComponentPropsWithRef<typeof Input>, 'id' | 'aria-invalid'> &
  FieldShellProps & {
    id?: string;
    /**
     * hint/error 메시지 슬롯(1줄)을 항상 예약한다(기본 true — 오류가 나타나도 폼이 밀리지 않음,
     * M13). 인라인 툴바처럼 슬롯이 불필요한 곳만 false.
     */
    reserveMessage?: boolean;
  };

/**
 * 라벨 위 · 컨트롤 · 메시지 슬롯 1개(error가 hint를 대체) — 폼 컨트롤 표준(M43).
 * `aria-describedby`는 지금 표시 중인 메시지만 가리킨다.
 */
function FormField({
  label,
  hint,
  help,
  error,
  required,
  className,
  labelClassName,
  reserveMessage = true,
  id,
  ref,
  'aria-describedby': ariaDescribedBy,
  ...inputProps
}: FormFieldProps) {
  const { fieldId, hintId, errorId } = useFieldIds(id);
  const unavailable = inputProps.disabled || inputProps.readOnly;
  const showHint = !error && Boolean(hint);
  const showMessage = reserveMessage || Boolean(error) || showHint;
  return (
    <Field
      className={className}
      data-disabled={unavailable ? true : undefined}
      data-invalid={error ? true : undefined}
    >
      <FieldLabel className={labelClassName} htmlFor={fieldId}>
        {label}
        {required ? <span aria-hidden="true"> *</span> : null}
        {help !== undefined ? (
          <HelpTip label={typeof label === 'string' ? label : '이 필드'}>{help}</HelpTip>
        ) : null}
      </FieldLabel>
      <Input
        aria-describedby={describedBy(
          ariaDescribedBy,
          showHint ? hintId : undefined,
          error ? errorId : undefined,
        )}
        aria-invalid={error ? true : undefined}
        aria-label={requiredFieldAriaLabel(label, required, help)}
        aria-required={required || undefined}
        id={fieldId}
        ref={ref}
        {...inputProps}
      />
      {showMessage ? (
        <FieldMessage>
          {error ? (
            <FieldError id={errorId}>{error}</FieldError>
          ) : showHint ? (
            <FieldDescription id={hintId}>{hint}</FieldDescription>
          ) : null}
        </FieldMessage>
      ) : null}
    </Field>
  );
}

export { FormField };
export type { FormFieldProps };
