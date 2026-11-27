/**
 * 장소 정보 패널(웹 `PlaceInfoPanel`·모바일 장소 시트) 공용 문구·판정.
 */
import { ApiError } from '@pinvi/api-client';
import type { PoiPlaceDetails } from '@pinvi/schemas';
import { kstDateKey } from './weatherNow';

const SOURCE_LABELS: Record<string, string> = {
  kor_travel_map: '공공데이터(한국 여행 지도)',
  // Map visitor_info(ADR-126)의 이용시간·휴무를 쓴 필드는 그 원천을 출처로 적는다.
  tourapi: '한국관광공사',
  krheritage: '국가유산청',
  datagokr_museum: '공공데이터포털 전국박물관미술관정보표준데이터',
  krforest_recreation_forest: '공공데이터포털 전국휴양림표준데이터',
};
const WEEKDAYS = ['일요일', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일'];

/** 오늘(KST) 영업시간 줄. 한 줄뿐이면 그 줄, 요일별이면 오늘 요일 줄. 없으면 null. */
export function todayHoursLine(hours: readonly string[], now: number): string | null {
  if (hours.length === 0) return null;
  if (hours.length === 1) return hours[0]!;
  const weekday = WEEKDAYS[new Date(Date.parse(`${kstDateKey(now)}T00:00:00Z`)).getUTCDay()]!;
  return hours.find((line) => line.startsWith(weekday)) ?? null;
}

/** 보일 영업 정보(영업시간·휴무일·전화·웹사이트)가 하나라도 있는가. */
export function hasAnyPlaceDetail(details: PoiPlaceDetails | null): details is PoiPlaceDetails {
  return (
    details != null &&
    (details.opening_hours.length > 0 ||
      details.closed_days != null ||
      details.phone != null ||
      details.website != null)
  );
}

/** "출처: 공공데이터(한국 여행 지도) · 2026-11-17 확인". */
export function placeDetailsSourceLine(details: PoiPlaceDetails | null): string {
  if (!details) return '';
  const sources = Array.from(
    new Set(Object.values(details.sources).map((key) => SOURCE_LABELS[key] ?? key)),
  );
  return [
    sources.length > 0 ? `출처: ${sources.join(', ')}` : null,
    details.fetched_at ? `${kstDateKey(Date.parse(details.fetched_at))} 확인` : null,
  ]
    .filter(Boolean)
    .join(' · ');
}

/** `tel:` 주소(숫자·+만). */
export function telHref(phone: string): string {
  return `tel:${phone.replace(/[^0-9+]/g, '')}`;
}

/** "다시 읽어오기" 실패 문구 — 429는 기다릴 시간, 403은 편집 권한 안내. */
export function placeDetailsRefreshErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 429) {
    const wait = error.retryAfterSeconds ?? null;
    return wait ? `${wait}초 뒤에 다시 읽어올 수 있습니다.` : '잠시 뒤에 다시 읽어올 수 있습니다.';
  }
  if (error instanceof ApiError && error.status === 403) {
    return '이 여행을 편집할 수 있는 사람만 다시 읽어올 수 있습니다.';
  }
  return '장소 정보를 다시 읽어오지 못했습니다. 잠시 뒤 다시 시도해 주세요.';
}
