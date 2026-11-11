import type { PoiResponse, TripView, TripViewPoi } from '@pinvi/schemas';

/**
 * 방금 만든 POI를 `POST /trips/{id}/pois` 응답만으로 TripView에 끼운다(#733).
 *
 * 목록은 원래 `GET /trips/{id}` 재조회가 끝나야 새 행을 그렸다. 그 재조회는 weather 보강을 기다려
 * 운영에서 2~7 s 걸리고, 진행 중 조회가 있으면 그 뒤에 한 번 더 읽으므로(createLatestReload) 15 s를
 * 넘기도 한다. 여기서 만드는 행은 임시다 — 서버가 계산하는 값(표시 색의 일자 기본색, feature 해석
 * 상태, weather)은 뒤따르는 재조회 결과가 덮어쓴다. 재조회 결과에 이미 있는 POI는 건드리지 않는다.
 */
export function withCreatedPois(view: TripView, created: Iterable<PoiResponse>): TripView {
  let days = view.days;
  for (const poi of created) {
    const index = days.findIndex((day) => day.day_index === poi.day_index);
    if (index < 0) continue;
    const day = days[index]!;
    if (day.pois.some((existing) => existing.poi_id === poi.attachment_id)) continue;
    const pois = [...day.pois, provisionalViewPoi(poi)].sort((a, b) =>
      // sort_order는 COLLATE "C"(바이트 순서) — ASCII rank라 code unit 비교와 같다.
      a.sort_order < b.sort_order ? -1 : a.sort_order > b.sort_order ? 1 : 0,
    );
    days = days.map((candidate, i) => (i === index ? { ...day, pois } : candidate));
  }
  return days === view.days ? view : { ...view, days };
}

function provisionalViewPoi(poi: PoiResponse): TripViewPoi {
  const snapshot = poi.feature_snapshot;
  const text = (key: string): string | null => {
    const value = snapshot[key];
    return typeof value === 'string' && value.trim() !== '' ? value : null;
  };
  return {
    poi_id: poi.attachment_id,
    feature_id: poi.feature_id,
    sort_order: poi.sort_order,
    title: text('name') ?? text('title'),
    feature: snapshot,
    marker_color: poi.custom_marker_color ?? text('marker_color'),
    marker_icon: poi.custom_marker_icon ?? text('marker_icon'),
    // 일자 기본색은 서버가 계산한다 — 사용자 지정 색이 없으면 재조회 전까지 비워 둔다.
    display_marker_color: poi.custom_marker_color,
    // 검색 결과에서 고른 Map feature다. 실제 해석 상태는 재조회가 채운다.
    feature_resolution_state: poi.feature_id ? 'found' : 'not_linked',
    user_note: poi.user_note,
    planned_arrival_at: poi.planned_arrival_at,
    planned_departure_at: poi.planned_departure_at,
    budget_amount: poi.budget_amount,
    actual_amount: poi.actual_amount,
    currency: poi.currency,
    user_url: poi.user_url,
    rise_set: poi.rise_set,
    feature_link_broken_at: poi.feature_link_broken_at,
    version: poi.version,
    created_at: poi.created_at,
    updated_at: poi.updated_at,
  };
}
