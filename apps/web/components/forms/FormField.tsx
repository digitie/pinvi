import type { InputHTMLAttributes } from 'react';
import { forwardRef } from 'react';

export interface FormFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  /** label·input·error를 잇는 고유 id (필수) */
  id: string;
  label: string;
  /** 검증 오류 메시지 — 있으면 aria-invalid + role=alert로 노출 */
  error?: string;
  /** 보조 설명(예: "8자 이상") */
  hint?: string;
}

/**
 * 접근성 기본을 갖춘 텍스트 입력 필드.
 * - `htmlFor`/`id`로 label↔input 연결
 * - 오류 시 `aria-invalid` + `aria-describedby`로 메시지 연결, `role=alert`로 announce
 * - 포커스 이동을 위해 `forwardRef`
 */
export const FormField = forwardRef<HTMLInputElement, FormFieldProps>(function FormField(
  { id, label, error, hint, className, ...inputProps },
  ref,
) {
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const describedBy =
    [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(' ') || undefined;

  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm text-ink">
        {label}
      </label>
      <input
        ref={ref}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={`w-full rounded-sm border px-3 py-2 text-sm ${
          error ? 'border-error-text' : 'border-hairline'
        }${className ? ` ${className}` : ''}`}
        {...inputProps}
      />
      {hint ? (
        <p id={hintId} className="text-xs text-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} role="alert" className="text-sm text-error-text">
          {error}
        </p>
      ) : null}
    </div>
  );
});
