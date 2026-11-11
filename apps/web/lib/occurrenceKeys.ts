/** 식별자가 없는 표시 목록: 동일 내용의 반복도 구분하고 고유 내용의 재정렬 키를 보존한다. */
export function withOccurrenceKeys<T>(items: readonly T[], identify: (item: T) => string) {
  const occurrences = new Map<string, number>();
  return items.map((item) => {
    const identity = identify(item);
    const occurrence = occurrences.get(identity) ?? 0;
    occurrences.set(identity, occurrence + 1);
    return { item, key: JSON.stringify([identity, occurrence]) };
  });
}
