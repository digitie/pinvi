import type { PlaceSearchResult } from '@pinvi/schemas';
export function searchResultCategory(result: PlaceSearchResult): string | null {
  if (result.category_label) return result.category_label;
  return result.source === 'feature' ? null : (result.category ?? null);
}
