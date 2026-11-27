/**
 * 경로(route) feature 요약 한 줄 — 일정 항목·검색 결과 표시용 (Map ADR-128 `route` 요약).
 *
 * 예: `등산 코스 · 4.2 km · 약 2시간 30분(추정) · 보통`.
 * 입력은 일정 POI의 `feature.route`(서버 trip card 또는 저장 snapshot)라 타입을 믿지 않고
 * 하나씩 확인한다 — 모르는 값은 그 조각만 빼고, 보일 것이 없으면 `null`.
 */

const ROUTE_TYPE_LABELS: Readonly<Record<string, string>> = {
  hiking_course: '등산 코스',
  hiking_trail: '등산로',
  trekking: '둘레길',
  forest_trail: '숲길',
  walking_course: '산책길',
  accessible_walk: '무장애길',
  cycling: '자전거길',
  drive_course: '드라이브 코스',
  tourism_road: '관광도로',
};

const DIFFICULTY_LABELS: Readonly<Record<string, string>> = {
  easy: '쉬움',
  moderate: '보통',
  hard: '어려움',
};

/** 보일 만한 양수만 — 0·음수·NaN은 그 조각을 생략한다. */
function finitePositive(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null;
}

/** 코스 길이 — 1 km 미만은 m, 이상은 소수 첫째 자리 km. */
export function formatRouteLength(meters: number): string {
  const rounded = Math.round(meters);
  if (rounded < 1000) return `${rounded} m`;
  return `${(meters / 1000).toFixed(1)} km`;
}

/** 소요시간 — `약 2시간 30분` / `약 45분`. */
export function formatRouteDuration(minutes: number): string {
  const total = Math.max(1, Math.round(minutes));
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  if (hours === 0) return `약 ${rest}분`;
  return rest === 0 ? `약 ${hours}시간` : `약 ${hours}시간 ${rest}분`;
}

export function routeSummaryLine(route: unknown): string | null {
  if (route == null || typeof route !== 'object') return null;
  const value = route as Record<string, unknown>;
  const parts: string[] = [];
  const routeType = typeof value.route_type === 'string' ? value.route_type : null;
  if (routeType != null) parts.push(ROUTE_TYPE_LABELS[routeType] ?? '경로');
  // network(샛길·갈래가 남은 망)는 거리·소요시간 모두 모든 갈래를 한 번씩 걷는 합이다(Map ADR-128).
  const network = value.shape === 'network';
  const length = finitePositive(value.length_m);
  if (length != null) parts.push(formatRouteLength(length) + (network ? '(갈래 포함)' : ''));
  const duration = finitePositive(value.duration_minutes);
  if (duration != null) {
    const notes = [
      ...(value.duration_basis === 'estimated' ? ['추정'] : []),
      ...(network ? ['갈래 포함'] : []),
    ];
    parts.push(formatRouteDuration(duration) + (notes.length > 0 ? `(${notes.join('·')})` : ''));
  }
  const difficulty =
    typeof value.difficulty === 'string' ? DIFFICULTY_LABELS[value.difficulty] : undefined;
  if (difficulty != null) parts.push(difficulty);
  // 종류만 있고 거리·시간이 없으면 굳이 한 줄을 차지하지 않는다.
  if (length == null && duration == null) return null;
  return parts.join(' · ');
}
