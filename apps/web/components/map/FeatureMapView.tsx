'use client';

import dynamic from 'next/dynamic';
import * as ReactDOMRuntime from 'react-dom';
import * as ReactRuntime from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
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
import { ApiError, featureApi } from '@tripmate/api-client';
import type { FeatureDetail, FeaturesInBoundsResponse, FeatureWeatherCard } from '@tripmate/schemas';
import { apiClient } from '@/lib/api';
import { boundsToBbox, clampZoom } from '@/lib/featureBounds';
import { paletteHex } from '@/lib/markerPalette';

declare global {
  interface Window {
    require?: (moduleName: string) => unknown;
  }
}

// maplibre-vworld dev 빌드가 UMD `require('react')` 를 호출하는 것을 위한 shim(개발 전용).
// 멱등 — 여러 지도 컴포넌트가 호출해도 한 번만 설치된다.
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
      if (moduleName === 'react') return ReactRuntime;
      if (moduleName === 'react-dom') return ReactDOMRuntime;
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
const CLUSTER_COLOR = '#37404a';
const DEBOUNCE_MS = 250;

type MapPoint = ClusterPoint & {
  kind: 'feature' | 'cluster';
  color: string;
  icon: string;
  title: string;
  lon: number;
  lat: number;
  featureId?: string;
  count?: number;
};

function toPoints(data: FeaturesInBoundsResponse): MapPoint[] {
  const features: MapPoint[] = data.features.map((f) => ({
    id: f.feature_id,
    lngLat: [f.coord.lon, f.coord.lat],
    kind: 'feature',
    color: paletteHex(f.marker_color),
    icon: f.marker_icon,
    title: f.title,
    lon: f.coord.lon,
    lat: f.coord.lat,
    featureId: f.feature_id,
  }));
  const clusters: MapPoint[] = data.clusters.map((c) => ({
    id: c.cluster_id,
    lngLat: [c.center.lon, c.center.lat],
    kind: 'cluster',
    color: CLUSTER_COLOR,
    icon: 'circle',
    title: `${c.feature_count}곳`,
    lon: c.center.lon,
    lat: c.center.lat,
    count: c.feature_count,
  }));
  return [...features, ...clusters];
}

export interface FeatureMapViewProps {
  apiKey?: string;
  className?: string;
  initialCenter?: [number, number];
  initialZoom?: number;
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

export function FeatureMapView({
  apiKey = '',
  className,
  initialCenter = DEFAULT_CENTER,
  initialZoom = DEFAULT_ZOOM,
}: FeatureMapViewProps) {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const latestRequest = useRef(0);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [points, setPoints] = useState<MapPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<MapPoint | null>(null);
  const [detail, setDetail] = useState<FeatureDetail | null>(null);
  const [weather, setWeather] = useState<FeatureWeatherCard | null>(null);

  const fetchInBounds = useCallback(async (map: maplibregl.Map) => {
    const bbox = boundsToBbox(map.getBounds());
    const zoom = clampZoom(map.getZoom());
    const requestId = latestRequest.current + 1;
    latestRequest.current = requestId;
    setLoading(true);
    try {
      const data = await featureApi(apiClient).inBounds({ bbox, zoom });
      if (requestId !== latestRequest.current) return;
      setPoints(toPoints(data));
      setError(null);
    } catch (err) {
      if (requestId !== latestRequest.current) return;
      setError(err instanceof ApiError ? err.message : '지도 데이터를 불러오지 못했습니다.');
    } finally {
      if (requestId === latestRequest.current) setLoading(false);
    }
  }, []);

  const scheduleFetch = useCallback(
    (map: maplibregl.Map) => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
      debounceTimer.current = setTimeout(() => void fetchInBounds(map), DEBOUNCE_MS);
    },
    [fetchInBounds]
  );

  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, []);

  const handleMapLoad = useCallback(
    (map: maplibregl.Map) => {
      mapRef.current = map;
      void fetchInBounds(map);
    },
    [fetchInBounds]
  );

  const handleViewportChange = useCallback(
    (event: maplibregl.MapLibreEvent) => {
      scheduleFetch(event.target as maplibregl.Map);
    },
    [scheduleFetch]
  );

  // 선택된 feature 의 상세 + 날씨 로드.
  useEffect(() => {
    if (!selected?.featureId) {
      setDetail(null);
      setWeather(null);
      return;
    }
    const featureId = selected.featureId;
    let active = true;
    setDetail(null);
    setWeather(null);
    void (async () => {
      try {
        const [d, w] = await Promise.allSettled([
          featureApi(apiClient).get(featureId),
          featureApi(apiClient).weather(featureId),
        ]);
        if (!active) return;
        if (d.status === 'fulfilled') setDetail(d.value);
        if (w.status === 'fulfilled') setWeather(w.value);
      } catch {
        // 상세/날씨 실패는 팝업 제목만으로 degrade.
      }
    })();
    return () => {
      active = false;
    };
  }, [selected?.featureId]);

  const handlePointClick = useCallback((point: MapPoint) => {
    if (point.kind === 'cluster') {
      const map = mapRef.current;
      if (map) {
        map.flyTo({ center: [point.lon, point.lat], zoom: Math.min(map.getZoom() + 2, 17) });
      }
      return;
    }
    setSelected(point);
  }, []);

  const currentTemp = weather?.short_term.find((t) => t.temp_c != null)?.temp_c ?? null;

  return (
    <div className={className} data-testid="feature-map">
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
            onMoveEnd={handleViewportChange}
            onZoomEnd={handleViewportChange}
            fallback={(info) => <MapFallback info={info} />}
            loadingSkeleton={<MapLoadingSkeleton />}
            className="h-full min-h-[360px]"
            unsupportedTileFallback={{ label: 'VWorld tile' }}
          >
            <ClusterLayer
              points={points}
              radius={48}
              maxZoom={15}
              renderMarker={(point) => {
                const mapPoint = point as MapPoint;
                return (
                  <MakiMarker
                    key={mapPoint.id}
                    lngLat={mapPoint.lngLat}
                    icon={mapPoint.icon}
                    color={mapPoint.color}
                    title={mapPoint.title}
                    selected={mapPoint.featureId != null && mapPoint.featureId === selected?.featureId}
                    ariaLabel={mapPoint.title}
                    onClick={() => handlePointClick(mapPoint)}
                  />
                );
              }}
            />
            {selected && (
              <Popup lngLat={selected.lngLat} maxWidth="260px" closeButton={false}>
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-semibold text-ink">{detail?.title ?? selected.title}</p>
                    <button
                      type="button"
                      onClick={() => setSelected(null)}
                      className="text-xs text-muted hover:text-ink"
                      aria-label="닫기"
                    >
                      닫기
                    </button>
                  </div>
                  {detail?.category && <p className="text-xs text-muted">{detail.category}</p>}
                  {detail?.address && <p className="text-xs text-body">{detail.address}</p>}
                  {currentTemp != null && (
                    <p className="text-xs text-body">현재 기온 {currentTemp.toFixed(0)}°C</p>
                  )}
                  {!detail && <p className="text-xs text-muted">상세 불러오는 중…</p>}
                </div>
              </Popup>
            )}
          </VWorldMap>
        </div>
        <dl
          className="grid gap-0 border-t border-hairline bg-canvas text-xs text-muted sm:grid-cols-3"
          data-testid="feature-map-status"
        >
          <div className="border-b border-hairline px-4 py-3 sm:border-b-0 sm:border-r">
            <dt className="font-semibold text-ink">표시</dt>
            <dd className="mt-1">{points.length}개</dd>
          </div>
          <div className="border-b border-hairline px-4 py-3 sm:border-b-0 sm:border-r">
            <dt className="font-semibold text-ink">상태</dt>
            <dd className="mt-1">{loading ? '불러오는 중…' : '대기'}</dd>
          </div>
          <div className="px-4 py-3">
            <dt className="font-semibold text-ink">오류</dt>
            <dd className="mt-1 truncate text-error-text">{error ?? '없음'}</dd>
          </div>
        </dl>
      </div>
    </div>
  );
}
