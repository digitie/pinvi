import { Marker, VWorldMapView as NativeVWorldMapView } from 'vworld-map-rn';
import { MapPin } from './MapPin';
import {
  usesCustomPin,
  type PlatformMarkerItem,
  type PlatformVWorldMapProps,
} from './VWorldMap.types';

/**
 * 네이티브 VWorld 지도(`vworld-map-rn`, MapLibre Native). 기본 마커는 패키지 `markers`로 그대로 넘기고,
 * 이름 라벨·작은 원 마커는 같은 패키지의 `Marker`에 `MapPin` 내용을 넣어 자식으로 그린다.
 */
export function VWorldMapView({ markers = [], onFeaturePress, ...props }: PlatformVWorldMapProps) {
  const plain: PlatformMarkerItem[] = [];
  const custom: PlatformMarkerItem[] = [];
  for (const marker of markers) (usesCustomPin(marker) ? custom : plain).push(marker);
  return (
    <NativeVWorldMapView {...props} markers={plain} onFeaturePress={onFeaturePress}>
      {custom.map((marker) => (
        <Marker
          key={marker.id}
          id={marker.id}
          lngLat={marker.coordinate}
          zIndex={marker.zIndex}
          ariaLabel={marker.ariaLabel ?? marker.label}
          onPress={() => onFeaturePress?.(marker)}
        >
          <MapPin
            color={marker.color ?? '#717171'}
            label={marker.label}
            selected={marker.selected}
            compact={marker.compact}
          />
        </Marker>
      ))}
    </NativeVWorldMapView>
  );
}
