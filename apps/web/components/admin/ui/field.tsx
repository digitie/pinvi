'use client';

import { cn } from '@/lib/admin/cn';
import type { ComponentProps } from 'react';
export {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSeparator,
  FieldSet,
  FieldTitle,
} from '@kor-travel/ui/field';

/** 오류/안내가 교체될 때 폼 높이를 유지하는 Pinvi 메시지 슬롯. */
export function FieldMessage({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      data-slot="field-message"
      className={cn('min-h-[1lh] text-xs leading-normal', className)}
      {...props}
    />
  );
}
