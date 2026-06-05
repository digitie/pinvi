'use client';

import dynamic from 'next/dynamic';
import * as ReactDOMRuntime from 'react-dom';
import * as ReactRuntime from 'react';
import { useCallback, useMemo, useState } from 'react';
import type maplibregl from 'maplibre-gl';
import type {
  ClusterLayerProps,
  ClusterPoint,
  MakiMarkerProps,
  PopupProps,
  VWorldMapFallbackInfo,
  VWorldMapProps,
} from 'maplibre-vworld';
import 'maplibre-gl/dist/maplibre-gl.css';
import 'maplibre-vworld/style.css';

declare global {
  interface Window {
    require?: (moduleName: string) => unknown;
  }
}

function installMaplibreVworldDevRequireShim() {
  if (
    typeof window === 'undefined' ||
    process.env.NODE_ENV === 'production' ||
    Reflect.has(window, 'require')
  ) {
    return;
  }

  Object.defineProperty(window, 'require', {
    configurable: true,
    value: (moduleName: string) => {
      if (moduleName === 'react') {
        return ReactRuntime;
      }
      if (moduleName === 'react-dom') {
        return ReactDOMRuntime;
      }
      throw new Error(`Unsupported maplibre-vworld dev require: ${moduleName}`);
    },
  });
}

installMaplibreVworldDevRequireShim();

const VWorldMap = dynamic<VWorldMapProps>(
  () => import('maplibre-vworld').then((module) => module.VWorldMap),
  { ssr: false, loading: () => <MapLoadingSkeleton /> }
);

const ClusterLayer = dynamic<ClusterLayerProps>(
  () => import('maplibre-vworld').then((module) => module.ClusterLayer),
  { ssr: false }
);

const MakiMarker = dynamic<MakiMarkerProps>(
  () => import('maplibre-vworld').then((module) => module.MakiMarker),
  { ssr: false }
);

const Popup = dynamic<PopupProps>(() => import('maplibre-vworld').then((module) => module.Popup), {
  ssr: false,
});

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

function readViewport(map: maplibregl.Map, lastEvent: string): MapViewportSnapshot {
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

function MapLoadingSkeleton() {
  return (
    <div
      className="flex h-full min-h-[360px] items-center justify-center bg-surface-soft text-sm text-muted"
      data-testid="vworld-map-loading"
    >
      지도 로딩 중
    </div>
  );
}

function MapFallback({ info }: { info: VWorldMapFallbackInfo }) {
  const message =
    info.reason === 'missing-api-key'
      ? 'VWorld API 키가 설정되지 않았습니다.'
      : '지도 엔진을 초기화할 수 없습니다.';

  return (
    <div
      className="flex h-full min-h-[360px] items-center justify-center bg-surface-soft px-6 text-center"
      data-testid="vworld-map-fallback"
    >
      <div className="max-w-sm space-y-2">
        <p className="text-base font-semibold text-ink">{message}</p>
        <p className="text-sm text-muted">NEXT_PUBLIC_VWORLD_API_KEY</p>
      </div>
    </div>
  );
}

export function MapView({
  apiKey = '',
  className,
  initialCenter = DEFAULT_CENTER,
  initialZoom = DEFAULT_ZOOM,
}: MapViewProps) {
  const [viewport, setViewport] = useState<MapViewportSnapshot>(() => ({
    center: initialCenter,
    zoom: initialZoom,
    bounds: '계산 대기',
    lastEvent: 'init',
  }));
  const [selectedPointId, setSelectedPointId] = useState<string>(
    DEFAULT_SELECTED_POINT.id.toString()
  );
  const selectedPoint = useMemo(
    () =>
      SHELL_POINTS.find((point) => point.id.toString() === selectedPointId) ??
      DEFAULT_SELECTED_POINT,
    [selectedPointId]
  );

  const handleMapLoad = useCallback((map: maplibregl.Map) => {
    setViewport(readViewport(map, 'load'));
  }, []);

  const handleMoveEnd = useCallback((event: maplibregl.MapLibreEvent) => {
    setViewport(readViewport(event.target as maplibregl.Map, 'moveend'));
  }, []);

  const handleZoomEnd = useCallback((event: maplibregl.MapLibreEvent) => {
    setViewport(readViewport(event.target as maplibregl.Map, 'zoomend'));
  }, []);

  return (
    <div className={className} data-testid="trip-map-shell">
      <div className="grid h-full min-h-[560px] grid-rows-[1fr_auto] overflow-hidden rounded-sm border border-hairline bg-canvas md:min-h-[680px]">
        <div className="relative min-h-0">
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
        <dl className="grid gap-0 border-t border-hairline bg-canvas text-xs text-muted sm:grid-cols-4">
          <div className="border-b border-hairline px-4 py-3 sm:border-b-0 sm:border-r">
            <dt className="font-semibold text-ink">중심</dt>
            <dd className="mt-1">{formatLngLat(viewport.center)}</dd>
          </div>
          <div className="border-b border-hairline px-4 py-3 sm:border-b-0 sm:border-r">
            <dt className="font-semibold text-ink">줌</dt>
            <dd className="mt-1">{viewport.zoom.toFixed(1)}</dd>
          </div>
          <div className="border-b border-hairline px-4 py-3 sm:border-b-0 sm:border-r">
            <dt className="font-semibold text-ink">이벤트</dt>
            <dd className="mt-1">{viewport.lastEvent}</dd>
          </div>
          <div className="px-4 py-3">
            <dt className="font-semibold text-ink">경계</dt>
            <dd className="mt-1 truncate">{viewport.bounds}</dd>
          </div>
        </dl>
      </div>
    </div>
  );
}
