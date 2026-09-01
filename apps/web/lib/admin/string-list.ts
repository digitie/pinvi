/**
 * KTM `packages/kor-travel-map-admin/frontend/src/lib/string-list.ts`에서 이식(T-356).
 *
 * 원문에서 바꾼 부분과 이유:
 *  - 로직·시그니처는 원문 그대로. prettier 설정(`printWidth: 100`)에 맞춰 줄바꿈만 정리했다.
 *  - `MultiFilterCombobox`가 요구하는 유일한 의존이라 admin 전용 위치(`lib/admin/`)에 둔다.
 *
 * 공백만 있는 값은 버리고, trim 후 중복을 제거해 `localeCompare` 오름차순으로 정렬한다.
 * 콤보박스의 chip 순서와 후보 목록 순서를 한 규칙으로 묶기 위한 정규화 함수다.
 */
export function uniqueSorted(values: readonly string[]): string[] {
  const normalized = values.flatMap((value) => {
    const trimmed = value.trim();
    return trimmed ? [trimmed] : [];
  });
  return Array.from(new Set(normalized)).sort((left, right) => left.localeCompare(right));
}
