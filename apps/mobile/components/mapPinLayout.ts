/** `MapPin` 원 지름(dp) — 여행 장소(이름 있음)는 16, 보조 마커(교통 등)는 12. 고르면 커진다. */
export function mapPinSize(compact: boolean | undefined, selected: boolean | undefined): number {
  if (compact) return selected ? 18 : 12;
  return selected ? 22 : 16;
}

/**
 * 이름 라벨이 붙은 핀을 지도에 놓는 자리. 내용(원 + 아래 라벨)의 위 끝을 좌표에 두고(`anchor: 'top'`) 원 반지름만큼
 * 올려 **원 중심이 좌표**에 오게 한다. 원만 있는 핀은 기본값(가운데)이 이미 원 중심이라 null.
 * 네이티브(`vworld-map-rn` ≥ 1.0.2 Marker)와 웹(`vworld-map-web` Marker)이 같은 값을 쓴다.
 */
export function mapPinPlacement(marker: {
  label?: string;
  compact?: boolean;
  selected?: boolean;
}): { anchor: 'top'; offset: [number, number] } | null {
  if (!marker.label) return null;
  return { anchor: 'top', offset: [0, -mapPinSize(marker.compact, marker.selected) / 2] };
}
