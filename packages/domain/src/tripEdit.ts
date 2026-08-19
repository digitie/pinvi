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

/** `YYYY-MM-DD` 형식 + 실제 달력상 존재하는 날짜인지(웹 `TripDetail.validDateValue` 미러). */
export function isValidIsoDate(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
  );
}

export type TripDateField = 'startDate' | 'endDate';

export interface TripDateRangeError {
  field: TripDateField;
  message: string;
}

/**
 * trip 시작/종료일 클라이언트 검증 — 웹 `TripDashboard.validateDateRange`와 같은 규칙에
 * 자유 텍스트 입력(모바일)을 위한 형식 검사를 더한 것. 문구는 웹과 동일.
 * (1) 값이 있으면 `YYYY-MM-DD` + 실제 날짜, (2) 둘 다 있거나 둘 다 비움, (3) 종료 ≥ 시작.
 * 통과 시 null. `TripCreate`/`TripUpdate` zod는 형식만 보고 순서는 안 보므로 UI가 막아야 한다.
 */
export function validateTripDateRange(
  startDate: string,
  endDate: string,
): TripDateRangeError | null {
  const start = startDate.trim();
  const end = endDate.trim();
  if (start && !isValidIsoDate(start)) {
    return { field: 'startDate', message: '날짜는 YYYY-MM-DD 형식으로 입력해 주세요.' };
  }
  if (end && !isValidIsoDate(end)) {
    return { field: 'endDate', message: '날짜는 YYYY-MM-DD 형식으로 입력해 주세요.' };
  }
  if (!start && !end) return null;
  if (!start || !end) {
    return {
      field: start ? 'endDate' : 'startDate',
      message: '시작일과 종료일을 함께 입력하거나 둘 다 비워두세요.',
    };
  }
  if (end < start) {
    return { field: 'endDate', message: '종료일은 시작일 이후여야 합니다.' };
  }
  return null;
}

export function buildTripUpdate(form: TripEditForm): TripUpdate {
  return {
    title: form.title.trim(),
    region_hint: form.regionHint.trim() || null,
    // 자유 텍스트 입력(모바일)의 공백을 정규화 — `validateTripDateRange`와 같은 값이 전송되게.
    start_date: form.startDate.trim() || null,
    end_date: form.endDate.trim() || null,
    visibility: form.visibility,
    status: form.status,
  };
}
