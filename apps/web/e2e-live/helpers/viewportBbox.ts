/** native viewport와 API bbox의 정본 차이는 한국 범위 clamp와 저줌 바깥 양자화뿐이다. */
export function viewportBboxMatches(
  query: readonly number[],
  native: readonly number[],
  zoom: number,
): boolean {
  if (query.length !== 4 || native.length !== 4) return false;
  const tolerance = zoom <= 7 ? 0.01 : zoom <= 10 ? 0.001 : 0.00001;
  return query.every((value, i) => {
    const expected = Math.max(i % 2 ? 33 : 124, Math.min(i % 2 ? 43 : 132, native[i]!));
    return Math.abs(value - expected) <= tolerance + 1e-8;
  });
}
