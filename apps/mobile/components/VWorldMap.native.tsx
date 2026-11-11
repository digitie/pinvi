import { VWorldMapView as NativeVWorldMapView } from 'vworld-map-rn';
import type { PlatformVWorldMapProps } from './VWorldMap.types';

export function VWorldMapView(props: PlatformVWorldMapProps) {
  return <NativeVWorldMapView {...props} />;
}
export type { VWorldMapHandle } from './VWorldMap.types';
