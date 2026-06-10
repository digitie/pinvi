import type { SelectHTMLAttributes } from 'react';
import { forwardRef } from 'react';

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
    <div className="space-y-1">
      <label htmlFor={id} className={labelClassName ?? 'block text-sm text-ink'}>
        {label}
      </label>
      <select
        ref={ref}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        className={`w-full rounded-sm border px-3 py-2 text-sm ${
          error ? 'border-error-text' : 'border-hairline'
        }${className ? ` ${className}` : ''}`}
        {...selectProps}
      >
        {children}
      </select>
      {error ? (
        <p id={errorId} role="alert" className="text-sm text-error-text">
          {error}
        </p>
      ) : null}
    </div>
  );
});
