import { inputClassName } from '@/components/forms/input-styles';
import type { InputHTMLAttributes } from 'react';
import { forwardRef } from 'react';

export interface FormFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  /** label·input·error를 잇는 고유 id (필수) */
  id: string;
  label: string;
  /** 검증 오류 메시지 — 있으면 aria-invalid + role=alert로 노출 */
  error?: string;
  /** 보조 설명(예: "8자 이상") — 필드 아래, 오류와 같은 슬롯 */
  hint?: string;
  /** label 클래스 override (다이얼로그의 굵은 라벨 등) */
  labelClassName?: string;
}

/**
 * 접근성 기본을 갖춘 텍스트 입력 필드.
 * - `htmlFor`/`id`로 label↔input 연결
 * - 오류 시 `aria-invalid` + `aria-describedby`로 메시지 연결, `role=alert`로 announce
 * - 포커스 이동을 위해 `forwardRef`
 * - hint/error는 필드 아래 같은 슬롯(오류가 나면 hint 대신 오류) — 레이아웃 시프트 최소화
 */
export const FormField = forwardRef<HTMLInputElement, FormFieldProps>(function FormField(
  { id, label, error, hint, className, labelClassName, ...inputProps },
  ref,
) {
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  // 오류가 있으면 hint 대신 오류만 렌더하므로 참조도 하나만 건다.
  const describedBy = error ? errorId : hint ? hintId : undefined;

  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className={labelClassName ?? 'block text-sm font-medium text-ink'}>
        {label}
      </label>
      <input
        ref={ref}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={inputClassName({ error: Boolean(error), className })}
        {...inputProps}
      />
      {/* helper 슬롯은 항상 예약(min-h-5) — 오류가 뜨는 순간 아래 요소가 밀리지 않는다(gate 39). */}
      {error ? (
        <p id={errorId} role="alert" className="min-h-5 text-sm text-error-text">
          {error}
        </p>
      ) : hint ? (
        <p id={hintId} className="min-h-5 text-sm text-muted">
          {hint}
        </p>
      ) : (
        <p className="min-h-5 text-sm" aria-hidden="true" />
      )}
    </div>
  );
});
