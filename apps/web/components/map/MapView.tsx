'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import type { ClusterPoint, MapLibreEvent, MapLibreMap } from '@/components/map/vworldPrimitives';
import {
  ClusterLayer,
  MakiMarker,
  MapFallback,
  MapLoadingSkeleton,
  Popup,
  VWorldMap,
} from '@/components/map/vworldPrimitives';

const DEFAULT_CENTER: [number, number] = [126.978, 37.5665];
const DEFAULT_ZOOM = 12;

const SHELL_POINTS: Array<
  ClusterPoint & {
    color: string;
    icon: string;
    title: string;
  }
> = [
  {
    id: 'seoul-city-hall',
    lngLat: [126.978, 37.5665],
    color: '#ff385c',
    icon: 'marker',
    title: '서울시청',
  },
  {
    id: 'gyeongbokgung',
    lngLat: [126.977, 37.5796],
    color: '#3949AB',
    icon: 'museum',
    title: '경복궁',
  },
  {
    id: 'namsan',
    lngLat: [126.9882, 37.5512],
    color: '#43A047',
    icon: 'park',
    title: '남산',
  },
];
const DEFAULT_SELECTED_POINT = SHELL_POINTS[0]!;

interface MapViewportSnapshot {
  center: [number, number];
  zoom: number;
  bounds: string;
  lastEvent: string;
}

export interface MapViewProps {
  apiKey?: string;
  className?: string;
  initialCenter?: [number, number];
  initialZoom?: number;
}

function formatLngLat(lngLat: [number, number]) {
  return `${lngLat[0].toFixed(4)}, ${lngLat[1].toFixed(4)}`;
}

function readViewport(map: MapLibreMap, lastEvent: string): MapViewportSnapshot {
  const center = map.getCenter();
  const bounds = map.getBounds();

  return {
    center: [center.lng, center.lat],
    zoom: map.getZoom(),
    bounds: `${bounds.getWest().toFixed(3)}, ${bounds.getSouth().toFixed(3)} / ${bounds
      .getEast()
      .toFixed(3)}, ${bounds.getNorth().toFixed(3)}`,
    lastEvent,
  };
}

export function MapView({
  apiKey = '',
  className,
  initialCenter = DEFAULT_CENTER,
  initialZoom = DEFAULT_ZOOM,
}: MapViewProps) {
  // 뷰포트 스냅샷은 화면에 노출하지 않는다(디버그 dl 삭제, T-316). state로 두면 moveend/zoomend마다
  // 반영되는 DOM 없이 리렌더만 나므로 ref로 유지한다 — 이벤트 배선(스모크 경로)은 그대로다.
  const viewportRef = useRef<MapViewportSnapshot>({
    center: initialCenter,
    zoom: initialZoom,
    bounds: '계산 대기',
    lastEvent: 'init',
  });
  const setViewport = (next: MapViewportSnapshot) => {
    viewportRef.current = next;
  };
  const [selectedPointId, setSelectedPointId] = useState<string>(
    DEFAULT_SELECTED_POINT.id.toString(),
  );
  const selectedPoint = useMemo(
    () =>
      SHELL_POINTS.find((point) => point.id.toString() === selectedPointId) ??
      DEFAULT_SELECTED_POINT,
    [selectedPointId],
  );

  const handleMapLoad = useCallback((map: MapLibreMap) => {
    setViewport(readViewport(map, 'load'));
  }, []);

  const handleMoveEnd = useCallback((event: MapLibreEvent) => {
    setViewport(readViewport(event.target as MapLibreMap, 'moveend'));
  }, []);

  const handleZoomEnd = useCallback((event: MapLibreEvent) => {
    setViewport(readViewport(event.target as MapLibreMap, 'zoomend'));
  }, []);

  return (
    <div className={`flex min-h-0 flex-col ${className ?? ''}`} data-testid="trip-map-shell">
      <div className="flex min-h-[320px] flex-1 flex-col overflow-hidden rounded-sm border border-hairline bg-canvas">
        <div className="relative min-h-0 flex-1">
          <VWorldMap
            apiKey={apiKey}
            center={initialCenter}
            zoom={initialZoom}
            layerType="Base"
            navigation
            scale
            geolocate={false}
            animateCameraChanges
            onLoad={handleMapLoad}
            onMoveEnd={handleMoveEnd}
            onZoomEnd={handleZoomEnd}
            fallback={(info) => <MapFallback info={info} />}
            loadingSkeleton={<MapLoadingSkeleton />}
            className="h-full min-h-[360px]"
            unsupportedTileFallback={{ label: 'VWorld tile' }}
          >
            <ClusterLayer
              points={SHELL_POINTS}
              radius={48}
              maxZoom={15}
              renderMarker={(point) => {
                const shellPoint = point as (typeof SHELL_POINTS)[number];
                return (
                  <MakiMarker
                    key={shellPoint.id}
                    lngLat={shellPoint.lngLat}
                    icon={shellPoint.icon}
                    color={shellPoint.color}
                    title={shellPoint.title}
                    selected={shellPoint.id.toString() === selectedPointId}
                    ariaLabel={shellPoint.title}
                    onClick={() => setSelectedPointId(shellPoint.id.toString())}
                  />
                );
              }}
            />
            {selectedPoint && (
              <Popup lngLat={selectedPoint.lngLat} maxWidth="240px" closeButton={false}>
                <div className="space-y-1">
                  <p className="text-sm font-semibold text-ink">{selectedPoint.title}</p>
                  <p className="text-xs text-muted">{formatLngLat(selectedPoint.lngLat)}</p>
                </div>
              </Popup>
            )}
          </VWorldMap>
        </div>
      </div>
    </div>
  );
}
