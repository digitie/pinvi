/**
 * POI `sort_order` 키 생성 — PR-C(4).
 *
 * 백엔드 `sort_order` 는 COLLATE "C"(바이트 순) 텍스트. 재정렬 시 클라이언트가
 * `new_sort_order` 를 만들어 보낸다(`poiApi.reorder`). base36 고정폭 + '0' 패딩은
 * ASCII 순서를 보존하므로 사전식 == 수치 순서.
 */

const SPACING = 100;
const WIDTH = 4;

/** n개의 균등 간격 정렬 키(오름차순, COLLATE "C" 안전). */
export function evenRanks(n: number): string[] {
  const ranks: string[] = [];
  for (let i = 0; i < n; i++) {
    ranks.push(((i + 1) * SPACING).toString(36).padStart(WIDTH, '0'));
  }
  return ranks;
}

/** 마지막 키 뒤에 오는 키(append). suffix 한 글자는 prefix 보다 항상 뒤로 정렬된다. */
export function appendRank(last: string | null): string {
  if (last == null || last.length === 0) {
    return evenRanks(1)[0]!;
  }
  return `${last}m`;
}

/** from → to 로 1칸 이동한 새 배열(원본 불변). 범위를 벗어나면 원본 복사 반환. */
export function arrayMove<T>(items: T[], from: number, to: number): T[] {
  const next = items.slice();
  if (from < 0 || from >= next.length || to < 0 || to >= next.length || from === to) {
    return next;
  }
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved as T);
  return next;
}

export interface PoiMove {
  poi_id: string;
  new_sort_order: string;
}

/**
 * 새 순서(poiId 배열) → 변경된 항목만 move 로. 현재 키와 같으면 제외(불필요한 write 방지).
 */
export function reorderMoves(
  orderedPoiIds: string[],
  currentSortById: Map<string, string>,
): PoiMove[] {
  const ranks = evenRanks(orderedPoiIds.length);
  const moves: PoiMove[] = [];
  orderedPoiIds.forEach((poiId, index) => {
    const rank = ranks[index]!;
    if (currentSortById.get(poiId) !== rank) {
      moves.push({ poi_id: poiId, new_sort_order: rank });
    }
  });
  return moves;
}

/** 장소 한 곳을 옮길 자리 — `day_index` 일자의 `beforePoiId` 바로 앞, null이면 맨 끝(`poiApi.move`). */
export interface PoiMoveTarget {
  dayIndex: number;
  beforePoiId: string | null;
}

/** 일자 하나의 장소 순서(표시 순서 그대로). */
export interface PoiDayOrder {
  dayIndex: number;
  poiIds: string[];
}

/**
 * 같은 일자 안에서 지금 자리로 되돌아오는 이동인가 — 자기 앞이나 바로 다음 장소 앞에 놓으면 순서가 그대로다.
 * 다른 일자로 가는 이동은 언제나 변경이다.
 */
export function isNoopPoiMove(poiId: string, fromDay: PoiDayOrder, target: PoiMoveTarget): boolean {
  if (target.dayIndex !== fromDay.dayIndex) return false;
  const index = fromDay.poiIds.indexOf(poiId);
  if (index < 0) return false;
  if (target.beforePoiId === poiId) return true;
  const next = fromDay.poiIds[index + 1] ?? null;
  return target.beforePoiId === next;
}

/**
 * 행 하나 위에 놓을 때의 자리 — 행 위쪽 절반이면 그 행 앞, 아래쪽 절반이면 다음 행 앞(마지막이면 맨 끝).
 */
export function poiRowDropTarget(
  day: PoiDayOrder,
  rowIndex: number,
  placement: 'before' | 'after',
): PoiMoveTarget {
  const beforePoiId =
    placement === 'before' ? (day.poiIds[rowIndex] ?? null) : (day.poiIds[rowIndex + 1] ?? null);
  return { dayIndex: day.dayIndex, beforePoiId };
}

/**
 * 키보드·버튼 한 칸 이동 — 일자 안에서는 한 칸씩, 첫 장소에서 위로 가면 이전 일자 맨 끝,
 * 마지막 장소에서 아래로 가면 다음 일자 맨 앞이다. 더 갈 곳이 없으면 null.
 * `days`는 화면에 보이는 일자 순서(day_index 오름차순)다.
 */
export function poiStepMoveTarget(
  days: PoiDayOrder[],
  poiId: string,
  direction: 'up' | 'down',
): PoiMoveTarget | null {
  const dayPosition = days.findIndex((day) => day.poiIds.includes(poiId));
  if (dayPosition < 0) return null;
  const day = days[dayPosition]!;
  const index = day.poiIds.indexOf(poiId);
  if (direction === 'up') {
    if (index > 0) return { dayIndex: day.dayIndex, beforePoiId: day.poiIds[index - 1]! };
    const previous = days[dayPosition - 1];
    return previous ? { dayIndex: previous.dayIndex, beforePoiId: null } : null;
  }
  if (index < day.poiIds.length - 1) {
    return { dayIndex: day.dayIndex, beforePoiId: day.poiIds[index + 2] ?? null };
  }
  const next = days[dayPosition + 1];
  return next ? { dayIndex: next.dayIndex, beforePoiId: next.poiIds[0] ?? null } : null;
}

/**
 * 이동을 표시 순서에 낙관적으로 반영한 새 일자 목록(원본 불변) — 모바일 낙관 순서용.
 */
export function applyPoiMove(
  days: PoiDayOrder[],
  poiId: string,
  target: PoiMoveTarget,
): PoiDayOrder[] {
  const without = days.map((day) => ({
    dayIndex: day.dayIndex,
    poiIds: day.poiIds.filter((id) => id !== poiId),
  }));
  return without.map((day) => {
    if (day.dayIndex !== target.dayIndex) return day;
    const at = target.beforePoiId == null ? -1 : day.poiIds.indexOf(target.beforePoiId);
    const poiIds = day.poiIds.slice();
    poiIds.splice(at < 0 ? poiIds.length : at, 0, poiId);
    return { dayIndex: day.dayIndex, poiIds };
  });
}
