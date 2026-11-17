/** `MapPin` 모양을 정하는 마커 속성. */
export interface MapPinShape {
  label?: string;
  compact?: boolean;
  selected?: boolean;
  /** 원 안에 그릴 maki 아이콘 이름. */
  icon?: string;
}

/**
 * `MapPin` 원 지름(dp). 아이콘이 든 여행 장소 원은 22(웹 여행 지도와 같다), 아이콘 없는 원은 16, 보조 마커
 * (교통 등)는 12. 고르면 커진다.
 */
export function mapPinSize({ compact, selected, icon }: MapPinShape): number {
  if (compact) return selected ? 18 : 12;
  if (icon) return selected ? 26 : 22;
  return selected ? 22 : 16;
}

/**
 * 이름 라벨이 붙은 핀을 지도에 놓는 자리. 내용(원 + 아래 라벨)의 위 끝을 좌표에 두고(`anchor: 'top'`) 원 반지름만큼
 * 올려 **원 중심이 좌표**에 오게 한다. 원만 있는 핀은 기본값(가운데)이 이미 원 중심이라 null.
 * 네이티브(`vworld-map-rn` ≥ 1.0.2 Marker)와 웹(`vworld-map-web` Marker)이 같은 값을 쓴다.
 */
export function mapPinPlacement(
  marker: MapPinShape,
): { anchor: 'top'; offset: [number, number] } | null {
  if (!marker.label) return null;
  return { anchor: 'top', offset: [0, -mapPinSize(marker) / 2] };
}
