'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { LocateFixed } from 'lucide-react';
import { ApiError, featureApi, userApi } from '@pinvi/api-client';
import type {
  FeatureDetail,
  FeaturesInBoundsResponse,
  FeatureSummary,
  FeatureWeatherCard,
} from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { isAbortError } from '@/lib/abort';
import { boundsToBbox, clampZoom } from '@/lib/featureBounds';
import { hasLocationConsent, locationConsentItems, resolveMarkerStyle } from '@pinvi/domain';
import {
  ClusterLayer,
  type ClusterPoint,
  type WeatherCondition,
  type MapLibreEvent,
  type MapLibreMap,
  type MapMouseEvent,
  MakiMarker,
  MapContextMenu,
  MapFallback,
  MapLoadingSkeleton,
  Popup,
  UserLocationMarker,
  VWorldMap,
  WeatherMarker,
} from '@/components/map/vworldPrimitives';
import { FeatureRequestDialog } from '@/components/map/FeatureRequestDialog';
import { LocationConsentDialog } from '@/components/map/LocationConsentDialog';
import { MapSearchBox } from '@/components/map/MapSearchBox';
import { FeatureDetailModalController } from '@/components/map/FeatureDetailModalController';
import { useMobileWebLayout } from '@/lib/useMobileWebLayout';

const DEFAULT_CENTER: [number, number] = [126.978, 37.5665];
const DEFAULT_ZOOM = 12;
const CLUSTER_COLOR = '#37404a';
const CLUSTER_MARKER_COLOR = 'cluster';
const DEBOUNCE_MS = 250;
const VIEWPORT_CACHE_MAX = 32;
const VIEWPORT_CACHE_TTL_MS = 60_000;

type MapPoint = ClusterPoint & {
  kind: 'feature' | 'cluster';
  color: string;
  markerColor: string;
  markerSource: string;
  icon: string;
  title: string;
  lon: number;
  lat: number;
  category?: string | null;
  status?: string | null;
  featureId?: string;
  featureKind?: FeatureSummary['kind'];
  count?: number;
};

interface ContextMenuState {
  x: number;
  y: number;
  lon: number;
  lat: number;
}

type ViewportCacheEntry = {
  data: FeaturesInBoundsResponse;
  cachedAt: number;
};

function toPoints(data: FeaturesInBoundsResponse): MapPoint[] {
  // kor_travel_map 평면 lon/lat 은 nullable — point geometry 없는 feature 는 마커에서 제외.
  const features: MapPoint[] = data.items.flatMap((f) => {
    if (!f.coord) return [];
    const style = resolveMarkerStyle({
      upstreamColor: f.marker_color,
      upstreamIcon: f.marker_icon,
      upstreamCategory: f.category,
      upstreamKind: f.kind,
    });
    return [
      {
        id: f.feature_id,
        lngLat: [f.coord.lon, f.coord.lat] as [number, number],
        kind: 'feature' as const,
        color: style.hex,
        markerColor: style.color,
        markerSource: style.source,
        icon: style.icon,
        title: f.name,
        lon: f.coord.lon,
        lat: f.coord.lat,
        category: style.category,
        status: f.status ?? null,
        featureId: f.feature_id,
        featureKind: f.kind,
      },
    ];
  });
  const clusters: MapPoint[] = data.clusters.map((c) => ({
    id: c.cluster_key,
    lngLat: [c.coord.lon, c.coord.lat],
    kind: 'cluster',
    color: CLUSTER_COLOR,
    markerColor: CLUSTER_MARKER_COLOR,
    markerSource: 'cluster',
    icon: 'circle',
    title: `${c.feature_count}곳`,
    lon: c.coord.lon,
    lat: c.coord.lat,
    count: c.feature_count,
  }));
  return [...features, ...clusters];
}

function featureToPoint(f: FeatureSummary): MapPoint | null {
  if (!f.coord) return null;
  const style = resolveMarkerStyle({
    upstreamColor: f.marker_color,
    upstreamIcon: f.marker_icon,
    upstreamCategory: f.category,
    upstreamKind: f.kind,
  });
  return {
    id: f.feature_id,
    lngLat: [f.coord.lon, f.coord.lat],
    kind: 'feature',
    color: style.hex,
    markerColor: style.color,
    markerSource: style.source,
    icon: style.icon,
    title: f.name,
    lon: f.coord.lon,
    lat: f.coord.lat,
    category: style.category,
    status: f.status ?? null,
    featureId: f.feature_id,
    featureKind: f.kind,
  };
}

function weatherConditionFromIcon(icon: string | null | undefined): WeatherCondition {
  const value = (icon ?? '').toLowerCase();
  if (/snow|sleet|ice|hail|blizzard|눈|한파/.test(value)) return 'snowy';
  if (/rain|shower|storm|thunder|drizzle|precip|비|호우/.test(value)) return 'rainy';
  if (/sun|clear|day|맑/.test(value)) return 'sunny';
  return 'cloudy';
}

function rememberViewport(
  cache: Map<string, ViewportCacheEntry>,
  key: string,
  data: FeaturesInBoundsResponse
) {
  if (cache.has(key)) cache.delete(key);
  cache.set(key, { data, cachedAt: Date.now() });
  while (cache.size > VIEWPORT_CACHE_MAX) {
    const first = cache.keys().next().value;
    if (first == null) break;
    cache.delete(first);
  }
}

function cachedViewport(
  cache: Map<string, ViewportCacheEntry>,
  key: string
): FeaturesInBoundsResponse | null {
  const entry = cache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.cachedAt > VIEWPORT_CACHE_TTL_MS) {
    cache.delete(key);
    return null;
  }
  return entry.data;
}

/** kor_travel_map 구조화 `address` 객체에서 표시용 한 줄을 뽑는다(키 미확정 → 방어적). */
function addressLine(detail: FeatureDetail | null): string | null {
  const addr = detail?.address;
  if (!addr) return null;
  const pick = (key: string): string | null =>
    typeof addr[key] === 'string' && (addr[key] as string).length > 0
      ? (addr[key] as string)
      : null;
  return (
    pick('road') ??
    pick('full') ??
    pick('jibun') ??
    pick('name') ??
    Object.values(addr).find((v): v is string => typeof v === 'string' && v.length > 0) ??
    null
  );
}

/** 평탄 weather metric 중 기온(℃) metric 의 현재값을 찾는다(metric_key 미확정 → 방어적). */
function currentTempC(card: FeatureWeatherCard | null): number | null {
  const metric = card?.metrics.find(
    (m) =>
      m.value_number != null &&
      (/℃|°C/.test(m.unit ?? '') || /temp|기온|T1H|TMP|TMN|TMX/i.test(m.metric_key)),
  );
  return metric?.value_number ?? null;
}

export interface FeatureMapViewProps {
  apiKey?: string;
  className?: string;
  initialCenter?: [number, number];
  initialZoom?: number;
  /** 딥링크(`?suggest=lon,lat`)로 장소 제안 다이얼로그를 특정 좌표에 미리 연다. */
  initialSuggestCoord?: { lon: number; lat: number } | null;
}

export function FeatureMapView({
  apiKey = '',
  className,
  initialCenter = DEFAULT_CENTER,
  initialZoom = DEFAULT_ZOOM,
  initialSuggestCoord = null,
}: FeatureMapViewProps) {
  const mapRef = useRef<MapLibreMap | null>(null);
  const latestRequest = useRef(0);
  const inBoundsAbort = useRef<AbortController | null>(null);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const viewportCache = useRef<Map<string, ViewportCacheEntry>>(new Map());

  const [points, setPoints] = useState<MapPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<MapPoint | null>(null);
  // F5: feature 상세 풀스크린 모달(weather 제외). null이면 닫힘.
  const [detailFeatureId, setDetailFeatureId] = useState<string | null>(null);
  const mobileLayout = useMobileWebLayout();
  const [detail, setDetail] = useState<FeatureDetail | null>(null);
  const [weather, setWeather] = useState<FeatureWeatherCard | null>(null);
  const [userLocation, setUserLocation] = useState<[number, number] | null>(null);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [locationConsent, setLocationConsent] = useState<boolean | null>(null);
  const [consentOpen, setConsentOpen] = useState(false);
  const [consentSaving, setConsentSaving] = useState(false);
  const [consentError, setConsentError] = useState<string | null>(null);
  const [requestCoord, setRequestCoord] = useState<{ lon: number; lat: number } | null>(
    initialSuggestCoord,
  );
  const [notice, setNotice] = useState<string | null>(null);

  const fetchInBounds = useCallback(async (map: MapLibreMap) => {
    const zoom = clampZoom(map.getZoom());
    const bbox = boundsToBbox(map.getBounds(), zoom);
    const cacheKey = `${zoom}:${bbox}`;
    const requestId = latestRequest.current + 1;
    latestRequest.current = requestId;
    // 직전 in-flight 요청을 취소해 빠른 pan에서 superseded viewport 검색이 백엔드에
    // 쌓이지 않게 한다 (kor-travel-concierge #111 — abort 미전파 패턴 예방).
    inBoundsAbort.current?.abort();

    const cached = cachedViewport(viewportCache.current, cacheKey);
    if (cached) {
      setPoints(toPoints(cached));
      setError(null);
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    inBoundsAbort.current = controller;
    setLoading(true);
    try {
      const data = await featureApi(apiClient).inBounds(
        { bbox, zoom },
        { signal: controller.signal },
      );
      if (requestId !== latestRequest.current) return;
      rememberViewport(viewportCache.current, cacheKey, data);
      setPoints(toPoints(data));
      setError(null);
    } catch (err) {
      if (isAbortError(err) || requestId !== latestRequest.current) return;
      setError(err instanceof ApiError ? err.message : '지도 데이터를 불러오지 못했습니다.');
    } finally {
      if (requestId === latestRequest.current) setLoading(false);
    }
  }, []);

  const scheduleFetch = useCallback(
    (map: MapLibreMap) => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
      debounceTimer.current = setTimeout(() => void fetchInBounds(map), DEBOUNCE_MS);
    },
    [fetchInBounds],
  );

  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
      inBoundsAbort.current?.abort();
    };
  }, []);

  const handleMapLoad = useCallback(
    (map: MapLibreMap) => {
      mapRef.current = map;
      void fetchInBounds(map);
    },
    [fetchInBounds],
  );

  const handleViewportChange = useCallback(
    (event: MapLibreEvent) => {
      scheduleFetch(event.target as MapLibreMap);
    },
    [scheduleFetch],
  );

  const handleContextMenu = useCallback((event: MapMouseEvent) => {
    setContextMenu({
      x: event.originalEvent.clientX,
      y: event.originalEvent.clientY,
      lon: event.lngLat.lng,
      lat: event.lngLat.lat,
    });
  }, []);

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

  const flyTo = useCallback((lon: number, lat: number, zoom?: number) => {
    mapRef.current?.flyTo(zoom != null ? { center: [lon, lat], zoom } : { center: [lon, lat] });
  }, []);

  const handlePointClick = useCallback(
    (point: MapPoint) => {
      if (point.kind === 'cluster') {
        const map = mapRef.current;
        if (map) flyTo(point.lon, point.lat, Math.min(map.getZoom() + 2, 17));
        return;
      }
      setSelected(point);
      // 모바일: weather가 아닌 feature 마커 탭은 중간 팝업 없이 상세 시트를 바로 연다(ADR-056).
      if (mobileLayout && point.featureId && point.featureKind !== 'weather') {
        setDetailFeatureId(point.featureId);
      }
    },
    [flyTo, mobileLayout],
  );

  const handleSearchSelect = useCallback(
    (feature: FeatureSummary) => {
      const point = featureToPoint(feature);
      if (!point) return;
      setSelected(point);
      flyTo(point.lon, point.lat, 15);
    },
    [flyTo],
  );

  const runGeolocate = useCallback(() => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setNotice('이 브라우저는 위치를 지원하지 않습니다.');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const lon = position.coords.longitude;
        const lat = position.coords.latitude;
        setUserLocation([lon, lat]);
        setNotice(null);
        flyTo(lon, lat, 14);
      },
      () => setNotice('위치 권한이 거부되었거나 가져올 수 없습니다.'),
    );
  }, [flyTo]);

  // 위치 기능은 LBS 동의(lbs_tos + location_collection) 확인 후에만(위치정보법 제15·16조).
  const handleMyLocation = useCallback(async () => {
    if (locationConsent === true) {
      runGeolocate();
      return;
    }
    try {
      const consents = await userApi(apiClient).getConsents();
      if (hasLocationConsent(consents)) {
        setLocationConsent(true);
        runGeolocate();
        return;
      }
    } catch {
      // 동의 조회 실패 시 동의 다이얼로그로 안내.
    }
    setConsentError(null);
    setConsentOpen(true);
  }, [locationConsent, runGeolocate]);

  const handleConsentAgree = useCallback(async () => {
    setConsentSaving(true);
    setConsentError(null);
    try {
      await userApi(apiClient).putConsents(locationConsentItems());
      setLocationConsent(true);
      setConsentOpen(false);
      runGeolocate();
    } catch (err) {
      setConsentError(err instanceof ApiError ? err.message : '동의 저장에 실패했습니다.');
    } finally {
      setConsentSaving(false);
    }
  }, [runGeolocate]);

  const copyCoord = useCallback(async (lat: number, lon: number) => {
    const text = `${lat.toFixed(6)}, ${lon.toFixed(6)}`;
    try {
      await navigator.clipboard?.writeText(text);
      setNotice(`좌표 복사됨: ${text}`);
    } catch {
      setNotice(`좌표: ${text}`);
    }
  }, []);

  const currentTemp = currentTempC(weather);
  const detailAddress = addressLine(detail);

  return (
    <div className={className} data-testid="feature-map">
      <div className="grid h-full min-h-[560px] grid-rows-[1fr_auto] overflow-hidden rounded-sm border border-hairline bg-canvas md:min-h-[680px]">
        <div className="relative min-h-0">
          <div className="pointer-events-none absolute inset-0 z-10">
            <div className="pointer-events-auto absolute left-3 top-3 w-72 max-w-[80vw]">
              <MapSearchBox onSelect={handleSearchSelect} />
              {notice && (
                <p className="mt-1 rounded-sm bg-surface-soft px-2 py-1 text-xs text-body shadow-sm">
                  {notice}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => void handleMyLocation()}
              aria-label="내 위치로 이동"
              data-testid="map-my-location"
              className="pointer-events-auto absolute bottom-4 right-3 flex h-10 w-10 items-center justify-center rounded-full border border-hairline bg-white text-ink shadow-sm hover:bg-surface-soft"
            >
              <LocateFixed className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>

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
            onContextMenu={handleContextMenu}
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
                const isSelected =
                  mapPoint.featureId != null && mapPoint.featureId === selected?.featureId;
                if (mapPoint.featureKind === 'weather') {
                  return (
                    <WeatherMarker
                      key={mapPoint.id}
                      lngLat={mapPoint.lngLat}
                      temperature={isSelected && currentTemp != null ? Math.round(currentTemp) : 0}
                      condition={weatherConditionFromIcon(mapPoint.icon)}
                      title={mapPoint.title}
                      selected={isSelected}
                      ariaLabel={mapPoint.title}
                      simplifyAtZoom={isSelected ? 5 : 20}
                      onClick={() => handlePointClick(mapPoint)}
                    />
                  );
                }
                return (
                  <MakiMarker
                    key={mapPoint.id}
                    lngLat={mapPoint.lngLat}
                    icon={mapPoint.icon}
                    color={mapPoint.color}
                    title={mapPoint.title}
                    selected={isSelected}
                    ariaLabel={mapPoint.title}
                    onClick={() => handlePointClick(mapPoint)}
                  />
                );
              }}
            />
            {userLocation && <UserLocationMarker lngLat={userLocation} />}
            {selected && (
              <Popup lngLat={selected.lngLat} maxWidth="260px" closeButton={false}>
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-semibold text-ink">
                      {detail?.name ?? selected.title}
                    </p>
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
                  {detailAddress && <p className="text-xs text-body">{detailAddress}</p>}
                  {currentTemp != null && (
                    <p className="text-xs text-body">현재 기온 {currentTemp.toFixed(0)}°C</p>
                  )}
                  {!detail && <p className="text-xs text-muted">상세 불러오는 중…</p>}
                  {/* weather는 인라인 기온만(풀스크린 상세 제외, ADR-056). */}
                  {selected.featureId && selected.featureKind !== 'weather' && (
                    <button
                      type="button"
                      onClick={() => setDetailFeatureId(selected.featureId ?? null)}
                      data-testid="feature-map-detail-open"
                      className="h-8 w-full rounded-sm bg-ink px-3 text-xs font-semibold text-white hover:bg-ink/90"
                    >
                      상세보기
                    </button>
                  )}
                </div>
              </Popup>
            )}
          </VWorldMap>
          <div className="sr-only" aria-hidden="true" data-testid="feature-map-marker-legend">
            {points.map((point) => (
              <span
                key={point.id}
                data-testid="feature-map-marker-style"
                data-feature-id={point.featureId ?? ''}
                data-kind={point.kind}
                data-marker-color={point.markerColor}
                data-marker-hex={point.color}
                data-marker-icon={point.icon}
                data-marker-source={point.markerSource}
                data-marker-selected={
                  point.kind === 'feature' && point.featureId === selected?.featureId
                    ? 'true'
                    : 'false'
                }
                data-marker-count={point.count ?? ''}
                data-feature-status={point.status ?? ''}
              >
                {point.title}
              </span>
            ))}
          </div>

          {contextMenu && (
            <MapContextMenu
              x={contextMenu.x}
              y={contextMenu.y}
              onClose={() => setContextMenu(null)}
            >
              <div className="min-w-44 overflow-hidden rounded-sm border border-hairline bg-white py-1 text-sm shadow-md">
                <button
                  type="button"
                  className="block w-full px-3 py-2 text-left text-ink hover:bg-surface-soft"
                  onClick={() => {
                    flyTo(contextMenu.lon, contextMenu.lat, 15);
                    setContextMenu(null);
                  }}
                >
                  여기서 주변 보기
                </button>
                <button
                  type="button"
                  className="block w-full px-3 py-2 text-left text-ink hover:bg-surface-soft"
                  onClick={() => {
                    setRequestCoord({ lon: contextMenu.lon, lat: contextMenu.lat });
                    setContextMenu(null);
                  }}
                >
                  이 위치 장소 제안
                </button>
                <button
                  type="button"
                  className="block w-full px-3 py-2 text-left text-ink hover:bg-surface-soft"
                  onClick={() => {
                    void copyCoord(contextMenu.lat, contextMenu.lon);
                    setContextMenu(null);
                  }}
                >
                  좌표 복사
                </button>
              </div>
            </MapContextMenu>
          )}
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
      <LocationConsentDialog
        open={consentOpen}
        saving={consentSaving}
        error={consentError}
        onAgree={() => void handleConsentAgree()}
        onCancel={() => setConsentOpen(false)}
      />
      {requestCoord && (
        <FeatureRequestDialog
          coord={requestCoord}
          onClose={() => setRequestCoord(null)}
          onSubmitted={() => setNotice('장소 제안이 접수됐습니다.')}
        />
      )}
      <FeatureDetailModalController
        featureId={detailFeatureId}
        fallbackTitle={selected?.title}
        onClose={() => setDetailFeatureId(null)}
      />
    </div>
  );
}
