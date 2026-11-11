'use client';

import type { ReactNode } from 'react';
import { HelpTip } from '@/components/admin/ui/help-tip';
import {
  FieldLabel,
  FieldMessage,
  FieldError,
  FieldDescription,
} from '@/components/admin/ui/field';
import type { FieldShellProps } from '@/components/admin/ui/form-field-shared';

/** 공통 Radix 폼 primitive의 라벨/도움말 배선. 컨트롤의 id는 호출자가 결정한다. */
export function FieldCaption({
  label,
  required,
  help,
  fieldId,
  labelClassName,
}: Pick<FieldShellProps, 'label' | 'required' | 'help' | 'labelClassName'> & { fieldId: string }) {
  return (
    <FieldLabel className={labelClassName} htmlFor={fieldId}>
      {label}
      {required ? <span aria-hidden="true"> *</span> : null}
      {help !== undefined ? (
        <HelpTip label={typeof label === 'string' ? label : '이 필드'}>{help}</HelpTip>
      ) : null}
    </FieldLabel>
  );
}

/** 오류가 도움말을 대체하며 예약 슬롯은 호출자의 기존 정책을 유지한다. */
export function FieldFeedback({
  showMessage,
  error,
  showHint,
  hint,
  errorId,
  hintId,
}: {
  showMessage: boolean;
  error?: string | null;
  showHint: boolean;
  hint?: ReactNode;
  errorId: string;
  hintId: string;
}) {
  if (!showMessage) return null;
  return (
    <FieldMessage>
      {error ? (
        <FieldError id={errorId}>{error}</FieldError>
      ) : showHint ? (
        <FieldDescription id={hintId}>{hint}</FieldDescription>
      ) : null}
    </FieldMessage>
  );
}
