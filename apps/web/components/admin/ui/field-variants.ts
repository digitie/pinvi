/**
 * KTM `src/components/ui/field-variants.ts`에서 이식(T-356).
 *
 * 라벨 recipe 1종(M43): 13.5px 500 ink-2 — Field가 invalid면 danger, disabled면 opacity 55.
 * FieldLabel/FieldTitle뿐 아니라 필터 필드처럼 직접 `<label>`/`<span>`을 조합하는 곳도 이 문자열만
 * 쓴다. 컴포넌트 파일(`field.tsx`)은 컴포넌트만 export한다(react-refresh only-export-components) —
 * recipe는 `button-variants.ts`와 같은 방식으로 여기 둔다.
 *
 * 원문에서 바꾼 것 = 색 토큰 2개뿐이다(구조/타이포/variant 문자열은 원문 그대로).
 * - `text-text-secondary` → `text-body`
 * - `text-destructive` → `text-admin-danger`
 */
export const fieldLabelClassName =
  'text-xs leading-snug font-medium text-body group-data-[invalid=true]/field:text-admin-danger group-data-[disabled=true]/field:opacity-55';
