import type { TextareaHTMLAttributes } from 'react';
import { forwardRef } from 'react';

export interface FormTextAreaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  /** label·textarea·error를 잇는 고유 id (필수) */
  id: string;
  label: string;
  /** 검증 오류 메시지 — 있으면 aria-invalid + role=alert로 노출 */
  error?: string;
  /** 보조 설명(예: "최소 1자") */
  hint?: string;
  /** label 클래스 override */
  labelClassName?: string;
}

/**
 * `FormField`의 textarea 버전. label↔textarea를 `htmlFor`/`id`로 연결하고,
 * 오류 시 `aria-invalid` + `aria-describedby` + `role=alert`로 노출한다.
 */
export const FormTextArea = forwardRef<HTMLTextAreaElement, FormTextAreaProps>(function FormTextArea(
  { id, label, error, hint, className, labelClassName, ...textareaProps },
  ref,
) {
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const describedBy =
    [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(' ') || undefined;

  return (
    <div className="space-y-1">
      <label htmlFor={id} className={labelClassName ?? 'block text-sm text-ink'}>
        {label}
      </label>
      {hint ? (
        <p id={hintId} className="text-xs text-muted">
          {hint}
        </p>
      ) : null}
      <textarea
        ref={ref}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={`w-full rounded-sm border px-3 py-2 text-sm ${
          error ? 'border-error-text' : 'border-hairline'
        }${className ? ` ${className}` : ''}`}
        {...textareaProps}
      />
      {error ? (
        <p id={errorId} role="alert" className="text-sm text-error-text">
          {error}
        </p>
      ) : null}
    </div>
  );
});
