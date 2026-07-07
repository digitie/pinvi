'use client';

import { useCallback, useEffect, useMemo, useRef } from 'react';
import {
  ClusterLayer,
  type ClusterPoint,
  type MapLibreMap,
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
  chrome?: 'framed' | 'flush';
}

export function TripMapView({
  apiKey = '',
  points,
  selectedPoiId = null,
  onSelectPoi,
  onMarkerContextMenu,
  className,
  chrome = 'framed',
}: TripMapViewProps) {
  const mapRef = useRef<MapLibreMap | null>(null);
  const surfaceClassName =
    chrome === 'flush'
      ? 'h-full min-h-[420px] overflow-hidden bg-canvas'
      : 'h-full min-h-[420px] overflow-hidden rounded-sm border border-hairline bg-canvas';

  const fitToPoints = useCallback(
    (map: MapLibreMap) => {
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
        { padding: 64, maxZoom: 15, animate: false },
      );
    },
    [points],
  );

  const handleLoad = useCallback(
    (map: MapLibreMap) => {
      mapRef.current = map;
      fitToPoints(map);
    },
    [fitToPoints],
  );

  // POI 목록이 바뀌면 경계 재조정.
  useEffect(() => {
    if (mapRef.current) fitToPoints(mapRef.current);
  }, [fitToPoints]);

  const markerPoints = useMemo<MarkerPoint[]>(
    () => points.map((p) => ({ id: p.poiId, lngLat: [p.lon, p.lat], point: p })),
    [points],
  );

  const selected = useMemo(
    () => points.find((p) => p.poiId === selectedPoiId) ?? null,
    [points, selectedPoiId],
  );

  // 외부에서 POI 를 선택하면 해당 위치로 이동.
  useEffect(() => {
    if (selected && mapRef.current) {
      mapRef.current.flyTo({ center: [selected.lon, selected.lat] });
    }
  }, [selected]);

  return (
    <div className={className} data-testid="trip-map">
      <div className={surfaceClassName} data-testid="trip-map-surface">
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
                  title={
                    marker.point.isBroken ? `${marker.point.title} (링크 끊김)` : marker.point.title
                  }
                  selected={marker.point.poiId === selectedPoiId}
                  highlighted={marker.point.isBroken}
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
        <div className="sr-only" aria-hidden="true" data-testid="trip-map-marker-legend">
          {points.map((point) => (
            <span
              key={point.poiId}
              data-testid="trip-map-marker-style"
              data-poi-id={point.poiId}
              data-day-index={point.dayIndex}
              data-marker-color={point.markerColor}
              data-marker-hex={point.color}
              data-marker-icon={point.icon}
              data-marker-source={point.markerSource}
              data-marker-selected={point.poiId === selectedPoiId ? 'true' : 'false'}
              data-marker-broken={point.isBroken ? 'true' : 'false'}
              data-marker-category={point.category ?? ''}
              data-marker-kind={point.kind ?? ''}
            >
              {point.title}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
