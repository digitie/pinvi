/**
 * trip 메타 편집 폼 ↔ `TripUpdate` — `docs/api/trips.md`.
 */

import type { TripStatus, TripUpdate, TripVisibility } from '@pinvi/schemas';

export interface TripEditForm {
  title: string;
  regionHint: string;
  startDate: string;
  endDate: string;
  visibility: TripVisibility;
  status: TripStatus;
}

export const VISIBILITY_LABEL: Record<TripVisibility, string> = {
  private: '비공개',
  unlisted: '링크 공개',
  public: '전체 공개',
};

export const STATUS_LABEL: Record<TripStatus, string> = {
  draft: '초안',
  planned: '예정',
  in_progress: '진행 중',
  completed: '완료',
  archived: '보관',
};

export function buildTripUpdate(form: TripEditForm): TripUpdate {
  return {
    title: form.title.trim(),
    region_hint: form.regionHint.trim() || null,
    start_date: form.startDate || null,
    end_date: form.endDate || null,
    visibility: form.visibility,
    status: form.status,
  };
}
