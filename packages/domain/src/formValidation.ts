import type { ZodType } from 'zod';

export type FieldErrors = Record<string, string>;

export interface ValidateResult<T> {
  success: boolean;
  data: T | null;
  /** 필드명 → 한국어 오류 메시지 (각 필드 첫 오류만) */
  fieldErrors: FieldErrors;
  /** 첫 번째로 오류가 난 필드명 — 포커스 이동용 */
  firstField: string | null;
}

const LABELS: Record<string, string> = {
  email: '이메일',
  password: '비밀번호',
  nickname: '닉네임',
};

/**
 * Zod issue 하나를 사용자 친화적 한국어 메시지로 변환한다.
 * 스키마의 기본 메시지는 영어이므로 필드·코드 기준으로 직접 매핑한다.
 */
function messageFor(field: string, issue: { code: string; message: string; minimum?: unknown }): string {
  const label = LABELS[field] ?? field;
  if (field === 'email') return '올바른 이메일 주소를 입력해 주세요.';
  if (issue.code === 'too_small') {
    const min = typeof issue.minimum === 'number' ? issue.minimum : 0;
    if (field === 'password' && min > 1) return `비밀번호는 ${min}자 이상이어야 합니다.`;
    return `${label}을(를) 입력해 주세요.`;
  }
  if (issue.code === 'too_big') return `${label}이(가) 너무 깁니다.`;
  return issue.message || `${label} 형식을 확인해 주세요.`;
}

/**
 * Zod 스키마로 폼 값을 검증하고, 실패 시 필드별 한국어 메시지와
 * 첫 오류 필드명을 돌려준다. UI는 이 결과만으로 aria-invalid /
 * aria-describedby / 포커스 이동을 구성할 수 있다.
 */
export function validateForm<T>(schema: ZodType<T>, values: unknown): ValidateResult<T> {
  const parsed = schema.safeParse(values);
  if (parsed.success) {
    return { success: true, data: parsed.data, fieldErrors: {}, firstField: null };
  }

  const fieldErrors: FieldErrors = {};
  let firstField: string | null = null;
  for (const issue of parsed.error.issues) {
    const raw = issue.path[0];
    const field = typeof raw === 'string' ? raw : raw != null ? String(raw) : '';
    if (!field || fieldErrors[field]) continue;
    fieldErrors[field] = messageFor(field, issue as { code: string; message: string; minimum?: unknown });
    if (firstField === null) firstField = field;
  }
  return { success: false, data: null, fieldErrors, firstField };
}
