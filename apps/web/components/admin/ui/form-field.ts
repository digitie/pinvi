/**
 * KTM `src/components/ui/form-field.ts`에서 이식(T-356).
 *
 * 폼 셸 3종의 단일 진입 배럴. 원문에서 바꾼 것: import 경로만
 * (`@/components/ui/*` → `@/components/admin/ui/*`).
 */
export { FormField } from '@/components/admin/ui/form-field-input';
export type { FormFieldProps } from '@/components/admin/ui/form-field-input';
export { FormSelect } from '@/components/admin/ui/form-select';
export type { FormSelectProps } from '@/components/admin/ui/form-select';
export { FormTextArea } from '@/components/admin/ui/form-textarea';
export type { FormTextAreaProps } from '@/components/admin/ui/form-textarea';
