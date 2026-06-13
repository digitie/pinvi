/**
 * feature 제안(새 장소/이벤트) 요청 빌더 — `docs/api/features.md`.
 *
 * 사용자는 `new_place` 제안만(장소/이벤트). 좌표는 지도에서 가져온다.
 */

import type { FeatureRequestCreate, FeatureSuggestionKind } from '@pinvi/schemas';

export interface NewPlaceForm {
  kind: FeatureSuggestionKind;
  title: string;
  /** 쉼표 구분 카테고리 입력. */
  categories: string;
  note: string;
}

/** 쉼표 구분 문자열 → 정리된 카테고리 배열(trim·중복 제거·최대 10). */
export function parseCategories(raw: string): string[] {
  const seen = new Set<string>();
  for (const part of raw.split(',')) {
    const trimmed = part.trim();
    if (trimmed) seen.add(trimmed);
  }
  return Array.from(seen).slice(0, 10);
}

export function buildNewPlaceRequest(
  form: NewPlaceForm,
  coord: { lon: number; lat: number }
): FeatureRequestCreate {
  return {
    type: 'new_place',
    kind: form.kind,
    title: form.title.trim(),
    coord: { lon: coord.lon, lat: coord.lat },
    categories: parseCategories(form.categories),
    note: form.note.trim() || null,
  };
}
