/**
 * 추천 여행(notice-plan) → trip 복사 요청 빌더 — `docs/api/notice-plans.md`.
 *
 * 새 여행 생성(`trip_title`/날짜) 또는 기존 여행에 추가(`target_trip_id`) 중 하나로 정규화.
 * `poi_ids: []` 는 plan 의 전체 POI 복사를 의미한다.
 */

import type { NoticePlanCopyRequest } from '@pinvi/schemas';

export type CopyMode = 'new' | 'existing';

export interface CopyForm {
  mode: CopyMode;
  title: string;
  startDate: string;
  endDate: string;
  targetTripId: string | null;
}

export function buildCopyRequest(form: CopyForm): NoticePlanCopyRequest {
  if (form.mode === 'existing') {
    return { target_trip_id: form.targetTripId, poi_ids: [] };
  }
  return {
    trip_title: form.title.trim() || null,
    trip_start_date: form.startDate || null,
    trip_end_date: form.endDate || null,
    poi_ids: [],
  };
}

/** 복사 가능 여부(새 여행=제목 필요, 기존 여행=trip 선택 필요). */
export function canCopy(form: CopyForm): boolean {
  if (form.mode === 'existing') return form.targetTripId != null;
  return form.title.trim().length > 0;
}
