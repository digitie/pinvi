'use client';

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type TouchEvent,
} from 'react';
import {
  ClusterLayer,
  type ClusterPoint,
  type MapLibreMap,
  MapFallback,
  MapLoadingSkeleton,
  PinMarker,
  Popup,
  VWorldMap,
} from '@/components/map/vworldPrimitives';
import { ApiError, featureApi } from '@pinvi/api-client';
import type { FeatureSummary } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { isAbortError } from '@/lib/abort';
import { boundsToBbox, clampZoom } from '@/lib/featureBounds';
import { pointsBounds, resolveMarkerStyle, type TripMapPoint } from '@pinvi/domain';

// 전국이 보이는 기본 시점(POI 가 없을 때).
const DEFAULT_CENTER: [number, number] = [127.5, 36.5];
const DEFAULT_ZOOM = 7;
const TRIP_MAP_MARKER_SIZE = 27;
const FEATURE_MARKER_SIZE = 22;
const FEATURE_DEBOUNCE_MS = 250;
const MAKI_ICON_BASE_URL = 'https://unpkg.com/@mapbox/maki@8.0.0/icons';
const MAKI_ICON_ALIASES: Record<string, string> = {
  alert: 'danger',
  camera: 'viewpoint',
  walking: 'mountain',
};

function makiIconName(icon: string): string {
  return MAKI_ICON_ALIASES[icon] ?? icon;
}

function makiIconUrl(icon: string): string {
  return `${MAKI_ICON_BASE_URL}/${encodeURIComponent(icon)}.svg`;
}

function isKoreaCoord(coord: { lon: number; lat: number }): boolean {
  return coord.lon >= 124 && coord.lon <= 132 && coord.lat >= 33 && coord.lat <= 43;
}

function ignoreLongPressTarget(target: EventTarget | null): boolean {
  return (
    target instanceof Element &&
    target.closest(
      '.maplibregl-marker, button, a, input, textarea, select, [role="button"], [role="menu"]',
    ) != null
  );
}

function TripMakiIcon({ icon, title }: { icon: string; title: string }) {
  const renderedIcon = makiIconName(icon);
  const [src, setSrc] = useState(() => makiIconUrl(renderedIcon));

  useEffect(() => {
    setSrc(makiIconUrl(renderedIcon));
  }, [renderedIcon]);

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt=""
      aria-hidden="true"
      data-testid="trip-map-maki-icon"
      data-maki-icon={icon}
      data-maki-rendered-icon={src.endsWith('/marker.svg') ? 'marker' : renderedIcon}
      className="block h-[18px] w-[18px] object-contain"
      style={{ filter: 'brightness(0) invert(1)' }}
      title={title}
      onError={() => {
        const fallbackSrc = makiIconUrl('marker');
        if (src !== fallbackSrc) setSrc(fallbackSrc);
      }}
    />
  );
}

type MarkerPoint = ClusterPoint & { point: TripMapPoint };
type FeaturePoint = ClusterPoint & {
  feature: FeatureSummary;
  color: string;
  icon: string;
  category: string | null;
};

export interface TripMapViewProps {
  apiKey?: string;
  points: TripMapPoint[];
  selectedPoiId?: string | null;
  showFeatures?: boolean;
  hiddenFeatureIds?: ReadonlySet<string>;
  canAddFeature?: boolean;
  onSelectPoi?: (poiId: string) => void;
  onMarkerContextMenu?: (poiId: string) => void;
  onAddFeature?: (feature: FeatureSummary) => void;
  onCreatePoiAtCoordinate?: (coord: { lon: number; lat: number }) => void;
  className?: string;
  chrome?: 'framed' | 'flush';
  showNavigationControls?: boolean;
}

export function TripMapView({
  apiKey = '',
  points,
  selectedPoiId = null,
  showFeatures = false,
  hiddenFeatureIds,
  canAddFeature = true,
  onSelectPoi,
  onMarkerContextMenu,
  onAddFeature,
  onCreatePoiAtCoordinate,
  className,
  chrome = 'framed',
  showNavigationControls = true,
}: TripMapViewProps) {
  const mapRef = useRef<MapLibreMap | null>(null);
  const featureAbortRef = useRef<AbortController | null>(null);
  const featureDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latestFeatureRequestRef = useRef(0);
  const longPressTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressStartRef = useRef<{ clientX: number; clientY: number } | null>(null);
  const longPressCreatedAtRef = useRef(0);
  const [features, setFeatures] = useState<FeatureSummary[]>([]);
  const [selectedFeature, setSelectedFeature] = useState<FeatureSummary | null>(null);
  const surfaceClassName =
    chrome === 'flush'
      ? 'h-full min-h-[420px] overflow-hidden bg-canvas'
      : 'h-full min-h-[420px] overflow-hidden rounded-sm border border-hairline bg-canvas';

  const fetchFeaturesInBounds = useCallback(async (map: MapLibreMap) => {
    const requestId = latestFeatureRequestRef.current + 1;
    latestFeatureRequestRef.current = requestId;
    featureAbortRef.current?.abort();

    const controller = new AbortController();
    featureAbortRef.current = controller;
    try {
      const zoom = clampZoom(map.getZoom());
      const data = await featureApi(apiClient).inBounds(
        { bbox: boundsToBbox(map.getBounds(), zoom), zoom, limit: 300 },
        { signal: controller.signal },
      );
      if (requestId !== latestFeatureRequestRef.current) return;
      setFeatures(data.items);
    } catch (err) {
      if (isAbortError(err) || requestId !== latestFeatureRequestRef.current) return;
      if (err instanceof ApiError) {
        // 지도 feature layer는 보조 정보라 실패 시 POI 지도 자체를 막지 않는다.
        setFeatures([]);
        return;
      }
      setFeatures([]);
    }
  }, []);

  const scheduleFeatureFetch = useCallback(
    (map: MapLibreMap) => {
      if (!showFeatures) return;
      if (featureDebounceRef.current) clearTimeout(featureDebounceRef.current);
      featureDebounceRef.current = setTimeout(
        () => void fetchFeaturesInBounds(map),
        FEATURE_DEBOUNCE_MS,
      );
    },
    [fetchFeaturesInBounds, showFeatures],
  );

  useEffect(() => {
    if (showFeatures) return;
    featureAbortRef.current?.abort();
    setFeatures([]);
    setSelectedFeature(null);
  }, [showFeatures]);

  useEffect(() => {
    return () => {
      featureAbortRef.current?.abort();
      if (featureDebounceRef.current) clearTimeout(featureDebounceRef.current);
      if (longPressTimerRef.current) clearTimeout(longPressTimerRef.current);
    };
  }, []);

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
      scheduleFeatureFetch(map);
    },
    [fitToPoints, scheduleFeatureFetch],
  );

  // POI 목록이 바뀌면 경계 재조정.
  useEffect(() => {
    if (mapRef.current) fitToPoints(mapRef.current);
  }, [fitToPoints]);

  const markerPoints = useMemo<MarkerPoint[]>(
    () => points.map((p) => ({ id: p.poiId, lngLat: [p.lon, p.lat], point: p })),
    [points],
  );

  const featurePoints = useMemo<FeaturePoint[]>(
    () =>
      features.flatMap((feature) => {
        if (!feature.coord || hiddenFeatureIds?.has(feature.feature_id)) return [];
        const style = resolveMarkerStyle({
          upstreamColor: feature.marker_color,
          upstreamIcon: feature.marker_icon,
          upstreamCategory: feature.category,
          upstreamKind: feature.kind,
        });
        return [
          {
            id: feature.feature_id,
            lngLat: [feature.coord.lon, feature.coord.lat] as [number, number],
            feature,
            color: style.hex,
            icon: style.icon,
            category: style.category,
          },
        ];
      }),
    [features, hiddenFeatureIds],
  );

  const selected = useMemo(
    () => points.find((p) => p.poiId === selectedPoiId) ?? null,
    [points, selectedPoiId],
  );

  useEffect(() => {
    if (selectedFeature && hiddenFeatureIds?.has(selectedFeature.feature_id)) {
      setSelectedFeature(null);
    }
  }, [hiddenFeatureIds, selectedFeature]);

  // 외부에서 POI 를 선택하면 해당 위치로 이동.
  useEffect(() => {
    if (selected && mapRef.current) {
      mapRef.current.flyTo({ center: [selected.lon, selected.lat] });
    }
  }, [selected]);

  const coordFromClientPoint = useCallback((clientX: number, clientY: number) => {
    const map = mapRef.current;
    if (!map) return null;
    const rect = map.getCanvas().getBoundingClientRect();
    const lngLat = map.unproject([clientX - rect.left, clientY - rect.top]);
    const coord = { lon: lngLat.lng, lat: lngLat.lat };
    return isKoreaCoord(coord) ? coord : null;
  }, []);

  const clearLongPress = useCallback(() => {
    if (longPressTimerRef.current) {
      clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
    longPressStartRef.current = null;
  }, []);

  const handleTouchStart = useCallback(
    (event: TouchEvent<HTMLDivElement>) => {
      if (!onCreatePoiAtCoordinate || event.touches.length !== 1) return;
      if (ignoreLongPressTarget(event.target)) return;
      const touch = event.touches[0];
      if (!touch) return;

      clearLongPress();
      longPressStartRef.current = { clientX: touch.clientX, clientY: touch.clientY };
      longPressTimerRef.current = setTimeout(() => {
        const start = longPressStartRef.current;
        if (!start) return;
        const coord = coordFromClientPoint(start.clientX, start.clientY);
        if (coord) {
          longPressCreatedAtRef.current = Date.now();
          onCreatePoiAtCoordinate(coord);
        }
        clearLongPress();
      }, 650);
    },
    [clearLongPress, coordFromClientPoint, onCreatePoiAtCoordinate],
  );

  const handleTouchMove = useCallback(
    (event: TouchEvent<HTMLDivElement>) => {
      const start = longPressStartRef.current;
      const touch = event.touches[0];
      if (!start || !touch) return;
      const moved = Math.hypot(touch.clientX - start.clientX, touch.clientY - start.clientY);
      if (moved > 10) clearLongPress();
    },
    [clearLongPress],
  );

  const openCoordinatePoiDialog = useCallback(
    (coord: { lon: number; lat: number }) => {
      if (isKoreaCoord(coord)) onCreatePoiAtCoordinate?.(coord);
    },
    [onCreatePoiAtCoordinate],
  );

  const handleMouseDown = useCallback(
    (event: ReactMouseEvent<HTMLDivElement>) => {
      if (!onCreatePoiAtCoordinate || event.button !== 2) return;
      if (ignoreLongPressTarget(event.target)) return;
      const coord = coordFromClientPoint(event.clientX, event.clientY);
      if (!coord) return;
      event.preventDefault();
      longPressCreatedAtRef.current = Date.now();
      openCoordinatePoiDialog(coord);
    },
    [coordFromClientPoint, onCreatePoiAtCoordinate, openCoordinatePoiDialog],
  );

  return (
    <div className={className} data-testid="trip-map">
      <div
        className={surfaceClassName}
        data-testid="trip-map-surface"
        onMouseDownCapture={handleMouseDown}
        onContextMenuCapture={(event) => {
          if (onCreatePoiAtCoordinate && !ignoreLongPressTarget(event.target)) {
            event.preventDefault();
          }
        }}
        onTouchStartCapture={handleTouchStart}
        onTouchMoveCapture={handleTouchMove}
        onTouchEndCapture={clearLongPress}
        onTouchCancelCapture={clearLongPress}
      >
        <VWorldMap
          apiKey={apiKey}
          center={DEFAULT_CENTER}
          zoom={DEFAULT_ZOOM}
          layerType="Base"
          navigation={showNavigationControls}
          scale
          geolocate={false}
          animateCameraChanges
          onLoad={handleLoad}
          onMoveEnd={(event) => scheduleFeatureFetch(event.target as MapLibreMap)}
          onZoomEnd={(event) => scheduleFeatureFetch(event.target as MapLibreMap)}
          onContextMenu={
            onCreatePoiAtCoordinate
              ? (event, context) => {
                  event.preventDefault();
                  if (context.source !== 'map' || context.defaultPrevented) return;
                  if (Date.now() - longPressCreatedAtRef.current < 1000) return;
                  openCoordinatePoiDialog({ lon: event.lngLat.lng, lat: event.lngLat.lat });
                }
              : undefined
          }
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
                <PinMarker
                  key={marker.point.poiId}
                  lngLat={marker.lngLat}
                  icon={<TripMakiIcon icon={marker.point.icon} title={marker.point.title} />}
                  color={marker.point.color}
                  size={TRIP_MAP_MARKER_SIZE}
                  showInnerCircle={false}
                  className="trip-map-marker"
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
          {showFeatures && (
            <ClusterLayer
              points={featurePoints}
              radius={36}
              maxZoom={15}
              renderMarker={(clusterPoint) => {
                const marker = clusterPoint as FeaturePoint;
                return (
                  <PinMarker
                    key={marker.feature.feature_id}
                    lngLat={marker.lngLat}
                    icon={<TripMakiIcon icon={marker.icon} title={marker.feature.name} />}
                    color={marker.color}
                    size={FEATURE_MARKER_SIZE}
                    showInnerCircle={false}
                    className="trip-map-feature-marker"
                    title={marker.feature.name}
                    ariaLabel={marker.feature.name}
                    onClick={() => setSelectedFeature(marker.feature)}
                    onContextMenu={(event) => event.preventDefault()}
                  />
                );
              }}
            />
          )}
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
          {selectedFeature?.coord && (
            <Popup
              lngLat={[selectedFeature.coord.lon, selectedFeature.coord.lat]}
              maxWidth="240px"
              closeButton={false}
            >
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-ink">
                      {selectedFeature.name}
                    </p>
                    {selectedFeature.category && (
                      <p className="text-xs text-muted">{selectedFeature.category}</p>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedFeature(null)}
                    className="text-xs text-muted hover:text-ink"
                    aria-label="닫기"
                  >
                    닫기
                  </button>
                </div>
                <button
                  type="button"
                  disabled={!canAddFeature}
                  onClick={() => {
                    onAddFeature?.(selectedFeature);
                    setSelectedFeature(null);
                  }}
                  className="h-8 w-full rounded-sm bg-ink px-3 text-xs font-semibold text-white hover:bg-ink/90 disabled:opacity-50"
                >
                  일정에 추가
                </button>
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
              data-marker-rendered-icon={makiIconName(point.icon)}
              data-marker-size={TRIP_MAP_MARKER_SIZE}
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
        <div className="sr-only" aria-hidden="true" data-testid="trip-map-feature-legend">
          {featurePoints.map((point) => (
            <span
              key={point.feature.feature_id}
              data-testid="trip-map-feature-style"
              data-feature-id={point.feature.feature_id}
              data-marker-color={point.feature.marker_color}
              data-marker-icon={point.icon}
              data-marker-size={FEATURE_MARKER_SIZE}
              data-marker-category={point.category ?? ''}
              data-feature-kind={point.feature.kind}
            >
              {point.feature.name}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
