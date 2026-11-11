import type { Ref } from 'react';
import type { StyleProp, ViewStyle } from 'react-native';
import type { VWorldMapViewProps } from 'vworld-map-core';
import type { VWorldMapHandle } from 'vworld-map-rn';

export type { VWorldMapHandle } from 'vworld-map-rn';
/** Pinvi에서 실제 사용하는 플랫폼 공통 계약. native-only 기능은 웹에 암묵 전달하지 않는다. */
export type PlatformVWorldMapProps = Pick<
  VWorldMapViewProps,
  | 'apiKey'
  | 'initialCenter'
  | 'initialZoom'
  | 'mapType'
  | 'markers'
  | 'onCameraChanged'
  | 'onFeaturePress'
> & {
  style?: StyleProp<ViewStyle>;
  ref?: Ref<VWorldMapHandle>;
};
