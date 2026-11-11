import { useCallback, useImperativeHandle, useRef } from 'react';
import { View, type ViewStyle } from 'react-native';
import { Marker, VWorldMapView, type MapLibreMap, type VWorldLayerType } from 'vworld-map-web';
import type { MarkerItem, VWorldMapType } from 'vworld-map-core';
import type { PlatformVWorldMapProps } from './VWorldMap.types';
import { Muted } from './ui';

const layers: Record<VWorldMapType, VWorldLayerType> = {
  base: 'Base',
  satellite: 'Satellite',
  hybrid: 'Hybrid',
  gray: 'gray',
  midnight: 'midnight',
};
/** native wrapper의 원형 마커 표현을 그대로 유지하고 지도 생명주기는 public Marker가 소유한다. */
function markerCircle(marker: MarkerItem): ViewStyle {
  const size = marker.selected ? 28 : marker.highlighted ? 24 : 20;
  return {
    width: size,
    height: size,
    borderRadius: size / 2,
    backgroundColor: marker.color ?? 'red',
    borderWidth: marker.selected ? 3 : marker.highlighted ? 2 : 0,
    borderColor: 'white',
  };
}

export function WebVWorldMap({
  ref,
  apiKey,
  initialCenter,
  initialZoom,
  mapType = 'base',
  markers = [],
  onCameraChanged,
  onFeaturePress,
  style,
}: PlatformVWorldMapProps) {
  const mapRef = useRef<MapLibreMap | null>(null);
  useImperativeHandle(
    ref,
    () => ({
      flyTo: ({ center, zoom, durationMs }) => {
        mapRef.current?.flyTo({ center, zoom, duration: durationMs });
      },
      fitBounds: ({ sw, ne }, options) => {
        mapRef.current?.fitBounds([sw, ne], {
          padding: options?.paddingPx,
          duration: options?.durationMs,
        });
      },
      zoomTo: (zoom, durationMs) => {
        mapRef.current?.zoomTo(zoom, { duration: durationMs });
      },
    }),
    [],
  );
  const notifyCamera = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    const center = map.getCenter(),
      bounds = map.getBounds();
    const ne = bounds.getNorthEast(),
      sw = bounds.getSouthWest();
    onCameraChanged?.({
      center: [center.lng, center.lat],
      zoom: map.getZoom(),
      bounds: { ne: [ne.lng, ne.lat], sw: [sw.lng, sw.lat] },
    });
  }, [onCameraChanged]);
  return (
    <View style={[{ flex: 1, position: 'relative' }, style]}>
      <VWorldMapView
        apiKey={apiKey}
        layerType={layers[mapType]}
        center={initialCenter}
        zoom={initialZoom}
        navigation={false}
        geolocate={false}
        scale={false}
        style={{ position: 'absolute', inset: 0 }}
        onLoad={(map) => {
          mapRef.current = map;
          notifyCamera();
        }}
        onMoveEnd={notifyCamera}
        fallback={<Muted>지도를 표시하지 못했습니다. 잠시 후 다시 시도해 주세요.</Muted>}
      >
        {markers.map((marker) => (
          <Marker
            key={marker.id}
            lngLat={marker.coordinate}
            zIndex={marker.zIndex}
            ariaLabel={marker.ariaLabel ?? marker.title}
            interactionId={marker.id}
            onClick={() => onFeaturePress?.(marker)}
          >
            <View style={markerCircle(marker)} />
          </Marker>
        ))}
      </VWorldMapView>
    </View>
  );
}
