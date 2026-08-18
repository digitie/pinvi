import type { TextareaHTMLAttributes } from 'react';
import { forwardRef } from 'react';
import { inputClassName } from './FormField';

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
export const FormTextArea = forwardRef<HTMLTextAreaElement, FormTextAreaProps>(
  function FormTextArea(
    { id, label, error, hint, className, labelClassName, ...textareaProps },
    ref,
  ) {
    const errorId = `${id}-error`;
    const hintId = `${id}-hint`;
    // 오류가 있으면 hint 대신 오류만 렌더하므로 참조도 하나만 건다(FormField와 동일 규칙).
    const describedBy = error ? errorId : hint ? hintId : undefined;

    return (
      <div className="space-y-1.5">
        <label htmlFor={id} className={labelClassName ?? 'block text-sm font-medium text-ink'}>
          {label}
        </label>
        <textarea
          ref={ref}
          id={id}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={inputClassName({
            error: Boolean(error),
            className: `min-h-24 ${className ?? ''}`,
          })}
          {...textareaProps}
        />
        {error ? (
          <p id={errorId} role="alert" className="text-sm text-error-text">
            {error}
          </p>
        ) : hint ? (
          <p id={hintId} className="text-sm text-muted">
            {hint}
          </p>
        ) : null}
      </div>
    );
  },
);
