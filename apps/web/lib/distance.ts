/**
 * 거리 표시 — 동선 최적화/거리 행렬(`docs/api/trips.md`).
 */

export function formatDistanceMeters(meters: number | null): string {
  if (meters == null) return '거리 정보 없음';
  if (meters < 1000) return `${meters}m`;
  return `${(meters / 1000).toFixed(1)}km`;
}
