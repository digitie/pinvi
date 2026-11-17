import type { Ref } from 'react';
import type { StyleProp, ViewStyle } from 'react-native';
import type { MarkerItem, VWorldMapViewProps } from 'vworld-map-core';
import type { VWorldMapHandle } from 'vworld-map-rn';
import type { MapPinWeather } from './MapPin';

export type { VWorldMapHandle } from 'vworld-map-rn';

/**
 * 공개 `MarkerItem` + Pinvi 표현. `label`(원 아래 이름)·`compact`(작은 원)·`icon`(원 안 maki 아이콘)이
 * 있으면 플랫폼 어댑터가 `MapPin`으로 그리고, 모두 없으면 지금처럼 패키지 기본 원 마커다. `weather`는 이름 옆
 * 현재 날씨(모르면 null).
 */
export type PlatformMarkerItem = MarkerItem & {
  label?: string;
  compact?: boolean;
  icon?: string;
  weather?: MapPinWeather | null;
};

/** `MapPin`으로 그릴 마커인가(라벨·작은 원·아이콘). */
export function usesCustomPin(marker: PlatformMarkerItem): boolean {
  return Boolean(marker.label) || marker.compact === true || Boolean(marker.icon);
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
