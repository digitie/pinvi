'use client';

import { useCallback, useEffect, useMemo, useRef } from 'react';
import type maplibregl from 'maplibre-gl';
import type { ClusterPoint } from 'maplibre-vworld';
import {
  ClusterLayer,
  MakiMarker,
  MapFallback,
  MapLoadingSkeleton,
  Popup,
  VWorldMap,
} from '@/components/map/vworldPrimitives';
import { pointsBounds, type TripMapPoint } from '@pinvi/domain';

// 전국이 보이는 기본 시점(POI 가 없을 때).
const DEFAULT_CENTER: [number, number] = [127.5, 36.5];
const DEFAULT_ZOOM = 7;

type MarkerPoint = ClusterPoint & { point: TripMapPoint };

export interface TripMapViewProps {
  apiKey?: string;
  points: TripMapPoint[];
  selectedPoiId?: string | null;
  onSelectPoi?: (poiId: string) => void;
  onMarkerContextMenu?: (poiId: string) => void;
  className?: string;
}

export function TripMapView({
  apiKey = '',
  points,
  selectedPoiId = null,
  onSelectPoi,
  onMarkerContextMenu,
  className,
}: TripMapViewProps) {
  const mapRef = useRef<maplibregl.Map | null>(null);

  const fitToPoints = useCallback((map: maplibregl.Map) => {
    const bounds = pointsBounds(points);
    if (!bounds) return;
    const only = points[0];
    if (points.length === 1 && only) {
      map.flyTo({ center: [only.lon, only.lat], zoom: 13 });
      return;
    }
    map.fitBounds(
      [
        [bounds.west, bounds.south],
        [bounds.east, bounds.north],
      ],
      { padding: 64, maxZoom: 15, animate: false }
    );
  }, [points]);

  const handleLoad = useCallback(
    (map: maplibregl.Map) => {
      mapRef.current = map;
      fitToPoints(map);
    },
    [fitToPoints]
  );

  // POI 목록이 바뀌면 경계 재조정.
  useEffect(() => {
    if (mapRef.current) fitToPoints(mapRef.current);
  }, [fitToPoints]);

  const markerPoints = useMemo<MarkerPoint[]>(
    () => points.map((p) => ({ id: p.poiId, lngLat: [p.lon, p.lat], point: p })),
    [points]
  );

  const selected = useMemo(
    () => points.find((p) => p.poiId === selectedPoiId) ?? null,
    [points, selectedPoiId]
  );

  // 외부에서 POI 를 선택하면 해당 위치로 이동.
  useEffect(() => {
    if (selected && mapRef.current) {
      mapRef.current.flyTo({ center: [selected.lon, selected.lat] });
    }
  }, [selected]);

  return (
    <div className={className} data-testid="trip-map">
      <div className="h-full min-h-[420px] overflow-hidden rounded-sm border border-hairline bg-canvas">
        <VWorldMap
          apiKey={apiKey}
          center={DEFAULT_CENTER}
          zoom={DEFAULT_ZOOM}
          layerType="Base"
          navigation
          scale
          geolocate={false}
          animateCameraChanges
          onLoad={handleLoad}
          fallback={(info) => <MapFallback info={info} />}
          loadingSkeleton={<MapLoadingSkeleton />}
          className="h-full min-h-[360px]"
          unsupportedTileFallback={{ label: 'VWorld tile' }}
        >
          <ClusterLayer
            points={markerPoints}
            radius={28}
            maxZoom={16}
            renderMarker={(clusterPoint) => {
              const marker = clusterPoint as MarkerPoint;
              return (
                <MakiMarker
                  key={marker.point.poiId}
                  lngLat={marker.lngLat}
                  icon={marker.point.icon}
                  color={marker.point.color}
                  title={marker.point.title}
                  selected={marker.point.poiId === selectedPoiId}
                  ariaLabel={marker.point.title}
                  onClick={() => onSelectPoi?.(marker.point.poiId)}
                  onContextMenu={(event) => {
                    event.preventDefault();
                    onMarkerContextMenu?.(marker.point.poiId);
                  }}
                />
              );
            }}
          />
          {selected && (
            <Popup lngLat={[selected.lon, selected.lat]} maxWidth="240px" closeButton={false}>
              <div className="space-y-1">
                <p className="text-sm font-semibold text-ink">{selected.title}</p>
                {selected.isBroken && (
                  <p className="text-xs text-error-text">링크 끊김 — 라이브러리에서 삭제된 장소</p>
                )}
              </div>
            </Popup>
          )}
        </VWorldMap>
      </div>
    </div>
  );
}
