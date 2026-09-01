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
import { Textarea } from '@/components/admin/ui/textarea';

/**
 * KTM `src/components/ui/form-textarea.tsx`에서 이식(T-356).
 *
 * 원문에서 바꾼 것: import 경로만(`@/components/ui/*` → `@/components/admin/ui/*`,
 * `@/components/help-tip` → `@/components/admin/ui/help-tip`). className과 배선은 원문 그대로다.
 */
type FormTextAreaProps = Omit<React.ComponentPropsWithRef<typeof Textarea>, 'id' | 'aria-invalid'> &
  FieldShellProps & {
    id?: string;
    /** hint/error 메시지 슬롯(1줄) 항상 예약(기본 true, M13). 인라인 툴바만 false. */
    reserveMessage?: boolean;
  };

/** 라벨 위 · Textarea · 메시지 슬롯 1개(error가 hint를 대체) — FormField와 같은 리듬. */
function FormTextArea({
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
  ...textareaProps
}: FormTextAreaProps) {
  const { fieldId, hintId, errorId } = useFieldIds(id);
  const unavailable = textareaProps.disabled || textareaProps.readOnly;
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
      <Textarea
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
        {...textareaProps}
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

export { FormTextArea };
export type { FormTextAreaProps };
