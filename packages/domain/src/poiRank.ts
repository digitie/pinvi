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
  currentSortById: Map<string, string>
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
