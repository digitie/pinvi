/** live fixture 선택용 이름 비교. 업종 분류나 제품 검색 순위를 바꾸지 않는다. */
export function normalizeFixtureName(name: string): string {
  return name
    .normalize('NFKC')
    .replace(/\s/g, '')
    .replace(/\([^)]*\)$/, '');
}
export function coordinateFixtureIndex(
  rows: ReadonlyArray<{ name: string; coord?: { lon: number; lat: number } | null }>,
  query: string,
): number {
  const expected = normalizeFixtureName(query);
  return rows.findIndex((row) => row.coord != null && normalizeFixtureName(row.name) === expected);
}
