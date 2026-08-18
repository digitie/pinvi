import type { SelectHTMLAttributes } from 'react';
import { forwardRef } from 'react';
import { inputClassName } from './FormField';

export interface FormSelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  /** label·select·error를 잇는 고유 id (필수) */
  id: string;
  label: string;
  /** 검증 오류 메시지 — 있으면 aria-invalid + role=alert로 노출 */
  error?: string;
  /** label 클래스 override */
  labelClassName?: string;
}

/**
 * `FormField`의 select 버전. label↔select를 `htmlFor`/`id`로 연결한다.
 * `<option>`은 children으로 전달한다.
 */
export const FormSelect = forwardRef<HTMLSelectElement, FormSelectProps>(function FormSelect(
  { id, label, error, className, labelClassName, children, ...selectProps },
  ref,
) {
  const errorId = `${id}-error`;

  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className={labelClassName ?? 'block text-sm font-medium text-ink'}>
        {label}
      </label>
      <select
        ref={ref}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        className={inputClassName({ error: Boolean(error), className })}
        {...selectProps}
      >
        {children}
      </select>
      {error ? (
        <p id={errorId} role="alert" className="min-h-5 text-sm text-error-text">
          {error}
        </p>
      ) : (
        <p className="min-h-5 text-sm" aria-hidden="true" />
      )}
    </div>
  );
});
