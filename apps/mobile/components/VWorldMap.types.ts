import type { Ref } from 'react';
import type { StyleProp, ViewStyle } from 'react-native';
import type { MarkerItem, VWorldMapViewProps } from 'vworld-map-core';
import type { VWorldMapHandle } from 'vworld-map-rn';

export type { VWorldMapHandle } from 'vworld-map-rn';

/**
 * 공개 `MarkerItem` + Pinvi 표현. `label`(원 아래 이름)이나 `compact`(작은 원)가 있으면 플랫폼 어댑터가
 * `MapPin`으로 그리고, 둘 다 없으면 지금처럼 패키지 기본 원 마커다.
 */
export type PlatformMarkerItem = MarkerItem & { label?: string; compact?: boolean };

/** `MapPin`으로 그릴 마커인가(라벨 또는 작은 원). */
export function usesCustomPin(marker: PlatformMarkerItem): boolean {
  return Boolean(marker.label) || marker.compact === true;
}

/** Pinvi에서 실제 사용하는 플랫폼 공통 계약. native-only 기능은 웹에 암묵 전달하지 않는다. */
export type PlatformVWorldMapProps = Pick<
  VWorldMapViewProps,
  'apiKey' | 'initialCenter' | 'initialZoom' | 'mapType' | 'onCameraChanged' | 'onFeaturePress'
> & {
  markers?: PlatformMarkerItem[];
  style?: StyleProp<ViewStyle>;
  ref?: Ref<VWorldMapHandle>;
};
