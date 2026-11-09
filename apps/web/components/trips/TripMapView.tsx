'use client';

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
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
import { useFeatureGeometry } from '@/lib/useFeatureGeometry';
import type { GeometryFeature } from '@/lib/featureGeometry';
import {
  FeatureGeometryControls,
  FeatureGeometryLayers,
  FeatureGeometryPopup,
} from '@/components/map/FeatureGeometryLayer';

import { isAbortError } from '@/lib/abort';
import { boundsToBbox, clampZoom } from '@/lib/featureBounds';
import {
  fitBottomRect,
  fitOverlayRect,
  fitPaddingForOverlay,
  fitPanelRect,
  pinBoxIntersects,
} from '@/lib/mapFitPadding';
import { viewportSearchBias } from '@/lib/searchBias';
import {
  featureResolutionNotice,
  pointsBounds,
  resolveMarkerStyle,
  type TripMapPoint,
} from '@pinvi/domain';
import { FeatureDetailModalController } from '@/components/map/FeatureDetailModalController';
import { useMobileWebLayout } from '@/lib/useMobileWebLayout';
import { useTransportLayers } from '@/lib/useTransportLayers';
import { TransportLayerControls } from '@/components/map/TransportLayerControls';
import { TransportMarkerLegend, TransportMarkers } from '@/components/map/TransportMarkers';
import { TransportDetailDialog } from '@/components/map/TransportDetailDialog';
import { markerZIndex } from '@/lib/markerStacking';

// 전국이 보이는 기본 시점(POI 가 없을 때).
const DEFAULT_CENTER: [number, number] = [127.5, 36.5];

/**
 * 맞춤 여백은 지금 DOM 상자로 계산하는데 maplibre transform은 컨테이너 크기를 ResizeObserver→rAF `resize()`로
 * 늦게 따라간다. 데스크톱 여행 지도는 왼쪽 일정 패널 내용이 늘면서 컨테이너가 자라므로(운영 데스크톱 약 1590px),
 * 옛 transform에 새 여백을 주면 fitBounds가 "cannot fit"으로 아무 일도 하지 않아 기본 시점(127.5,36.5 z7)에
 * 남는다(#686 NEAR-024 — 교통 요청 bbox=124.80,33.00,130.20,40.05 z7). 맞추기 전에 크기를 맞춘다.
 */
function syncMapSize(map: MapLibreMap): void {
  const container = map.getContainer();
  const canvas = map.getCanvas();
  if (
    container.clientWidth !== canvas.clientWidth ||
    container.clientHeight !== canvas.clientHeight
  ) {
    map.resize();
  }
}
const DEFAULT_ZOOM = 7;
const TRIP_MAP_MARKER_SIZE = 27;
// PinMarker는 너비 size, 높이 size×1.5(40.5px) 물방울을 아래 꼭짓점(anchor bottom)에 건다. 선택된 핀은
// 1.18배(≈48px)로 커지고, 실지도 확인에서 마커 상자 위쪽이 앵커보다 ≈49px 위에 잡힌 적이 있어 넉넉히 잡는다.
const TRIP_MAP_PIN_HEIGHT = Math.ceil(TRIP_MAP_MARKER_SIZE * 1.5 * 1.18);
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
      '.maplibregl-marker, button, a, input, textarea, select, [role="button"], [role="menu"], [data-map-overlay]',
    ) != null
  );
}

function TripMakiIcon({ icon, title }: { icon: string; title: string }) {
  const renderedIcon = makiIconName(icon);
  const [src, setSrc] = useState(() => makiIconUrl(renderedIcon));
  // icon(따라서 renderedIcon)이 바뀌면 이전 onError fallback 상태를 지우고 새 아이콘으로
  // 되돌린다 — src는 onError로도 독립적으로 바뀔 수 있어 순수 파생값이 아니다.
  const [prevRenderedIcon, setPrevRenderedIcon] = useState(renderedIcon);
  if (renderedIcon !== prevRenderedIcon) {
    setPrevRenderedIcon(renderedIcon);
    setSrc(makiIconUrl(renderedIcon));
  }

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
  onSelectPoi?: (poiId: string | null) => void;
  onMarkerContextMenu?: (poiId: string) => void;
  onAddFeature?: (feature: FeatureSummary) => void;
  onCreatePoiAtCoordinate?: (coord: { lon: number; lat: number }) => void;
  className?: string;
  chrome?: 'framed' | 'flush';
  showNavigationControls?: boolean;
  /**
   * 교통 정보 레이어(ADR-076). `/transport/*`는 로그인 필요라 **비로그인 공유 화면에서는 켜지 않는다**
   * (401이 로그인 화면 이동을 부른다). 기본 꺼짐.
   */
  transportLayers?: boolean;
  /**
   * 지도 왼쪽 위에 얹는 호출부 오버레이(예: `TripDetail`의 장소 검색). 주면 교통 정보 컨트롤을
   * **같은 세로 스택의 아래**에 둔다 — 둘을 따로 `absolute left/top`에 두면 서로 덮는다
   * (2026-11-02 prod e2e: 교통 정보 패널이 검색창을 가려 데스크톱·모바일 모두 입력란 왼쪽을
   * 누를 수 없었다). 검색 결과 목록이 펼쳐지면 교통 컨트롤이 그만큼 아래로 밀린다.
   */
  overlayTopLeft?: ReactNode;
  /**
   * `overlayTopLeft` 스택의 위치·폭 class(호출부 레이아웃이 정한다). 검색 결과·교통 패널이 지도보다
   * 길어질 수 있으므로 max-height와 세로 스크롤을 함께 준다.
   */
  overlayTopLeftClassName?: string;
  /** 지도 화면이 바뀔 때마다(로드·이동·줌) 그 bbox를 알린다 — 장소 검색 지역 편향의 화면 fallback. */
  onViewportBboxChange?: (bbox: string) => void;
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
  transportLayers = false,
  overlayTopLeft,
  overlayTopLeftClassName = 'pointer-events-none absolute left-2 right-2 top-2 z-10',
  onViewportBboxChange,
}: TripMapViewProps) {
  const mapRef = useRef<MapLibreMap | null>(null);
  const overlayStackRef = useRef<HTMLDivElement | null>(null);
  const fitCleanupRef = useRef<(() => void) | null>(null);
  const featureAbortRef = useRef<AbortController | null>(null);
  const featureDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latestFeatureRequestRef = useRef(0);
  const longPressTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressStartRef = useRef<{ clientX: number; clientY: number } | null>(null);
  const longPressCreatedAtRef = useRef(0);
  const [features, setFeatures] = useState<FeatureSummary[]>([]);
  const [selectedFeature, setSelectedFeature] = useState<FeatureSummary | null>(null);
  // F5: feature 상세 풀스크린 모달(weather 제외).
  const [detailFeatureId, setDetailFeatureId] = useState<string | null>(null);
  const mobileLayout = useMobileWebLayout();
  const transport = useTransportLayers({ active: transportLayers });
  const transportVisible = transport.visible;
  // fitToPoints가 읽는 값들 — 맞춤 함수가 바뀌어(=다시 맞춤) 사용자의 시점을 빼앗지 않게 ref로 둔다.
  const transportVisibleRef = useRef(transportVisible);
  const userMovedRef = useRef(false);
  const lastFitPointsRef = useRef<TripMapPoint[] | null>(null);
  const lastFitWithPanelRef = useRef(false);
  const { onViewportChange: transportViewportChange } = transport;
  const handleGeometrySelect = useCallback(
    (feature: GeometryFeature) => {
      userMovedRef.current = true;
      onSelectPoi?.(null);
      setSelectedFeature(null);
      if (mobileLayout) setDetailFeatureId(feature.feature_id);
    },
    [mobileLayout, onSelectPoi],
  );
  const geometry = useFeatureGeometry({
    active: showFeatures,
    hiddenFeatureIds,
    onSelect: handleGeometrySelect,
  });
  const { onViewportChange: geometryViewportChange, clearSelection: clearGeometrySelection } =
    geometry;
  const [previousGeometryPoiId, setPreviousGeometryPoiId] = useState(selectedPoiId);
  if (previousGeometryPoiId !== selectedPoiId) {
    setPreviousGeometryPoiId(selectedPoiId);
    if (selectedPoiId != null) {
      clearGeometrySelection();
      if (selectedFeature) setSelectedFeature(null);
    }
  }

  // flush = 여행 상세 지도 열. 데스크톱(lg)은 창 높이에 고정된 열을 그대로 채운다 — 고정 최소 높이가 남으면
  // 짧은 창에서 지도가 열 밖으로 넘쳐 아래쪽 핀이 fold 아래에 그려진다(#704).
  // 지도·fallback·로딩 상자 공통 최소 높이 — flush는 lg에서 열 높이를 그대로 따른다.
  const mapMinHeightClassName = chrome === 'flush' ? 'min-h-[360px] lg:min-h-0' : 'min-h-[360px]';
  const surfaceClassName =
    chrome === 'flush'
      ? 'relative h-full min-h-[420px] overflow-hidden bg-canvas lg:min-h-0'
      : 'relative h-full min-h-[420px] overflow-hidden rounded-sm border border-hairline bg-canvas';

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

  // showFeatures가 꺼지면 feature 상태를 리셋한다.
  const [prevShowFeatures, setPrevShowFeatures] = useState(showFeatures);
  if (showFeatures !== prevShowFeatures) {
    setPrevShowFeatures(showFeatures);
    if (!showFeatures) {
      setFeatures([]);
      setSelectedFeature(null);
    }
  }

  // ref(진행 중인 요청 취소)는 render 중에 접근할 수 없으므로 effect로 유지한다.
  useEffect(() => {
    if (!showFeatures) featureAbortRef.current?.abort();
  }, [showFeatures]);

  useEffect(() => {
    return () => {
      fitCleanupRef.current?.();
      featureAbortRef.current?.abort();
      if (featureDebounceRef.current) clearTimeout(featureDebounceRef.current);
      if (longPressTimerRef.current) clearTimeout(longPressTimerRef.current);
    };
  }, []);

  const fitToPoints = useCallback(
    (map: MapLibreMap) => {
      lastFitPointsRef.current = points;
      // 맞춤이 시점을 새로 정했다 — 그 전의 사용자 이동은 더는 지킬 시점이 아니다.
      userMovedRef.current = false;
      const bounds = pointsBounds(points);
      if (!bounds) return;
      syncMapSize(map);
      // 위쪽 여백은 지도 위 장소 검색 줄 아래로 — 북쪽 핀이 그 밑에 숨지 않게. 여백은 핀
      // 앵커(아래 꼭짓점) 자리라 핀 머리 높이도 더한다. 기준 높이는 maplibre가 맞춤을 검사하는
      // 지도 컨테이너다.
      const container = map.getContainer().getBoundingClientRect();
      const stack = overlayStackRef.current;
      const padding = fitPaddingForOverlay(container, fitOverlayRect(stack), TRIP_MAP_PIN_HEIGHT);
      const panel = fitPanelRect(stack);
      lastFitWithPanelRef.current = panel != null;
      const bottom = fitBottomRect(map.getContainer());
      const only = points[0];
      if (points.length === 1 && only) {
        // 핀 하나는 가운데에 두되, 위·아래 여백 차이의 절반만큼 내려 검색 줄과 겹치지 않게. 교통
        // 패널이 가운데 열까지 덮으면(모바일) 패널 아래를 기준으로 한다.
        const centerX = container.left + container.width / 2;
        const half = TRIP_MAP_MARKER_SIZE / 2;
        const panelCoversCenter =
          panel != null && panel.left < centerX + half && panel.right > centerX - half;
        const singlePadding = fitPaddingForOverlay(
          container, panel && panelCoversCenter ? panel : fitOverlayRect(stack),
          TRIP_MAP_PIN_HEIGHT,
          bottom && bottom.left < centerX + half && bottom.right > centerX - half ? bottom : null,
        );
        map.flyTo({
          center: [only.lon, only.lat],
          zoom: 13,
          offset: [0, (singlePadding.top - singlePadding.bottom) / 2],
        });
        return;
      }
      const lngLatBounds: [[number, number], [number, number]] = [
        [bounds.west, bounds.south],
        [bounds.east, bounds.north],
      ];
      map.fitBounds(lngLatBounds, { padding, maxZoom: 15, animate: false });
      // 교통 정보 패널(왼쪽 열) 밑에 핀이 들어가면 패널 아래까지 한 번 더 맞춘다. animate:false라
      // fitBounds가 바로 적용돼 project가 맞춘 뒤 위치를 준다.
      let topOverlay = fitOverlayRect(stack);
      let bottomOverlay = null;
      // 한쪽을 피한 재맞춤이 반대쪽 핀을 옮길 수 있어 상하 제한을 누적한다.
      for (let pass = 0; pass < 2; pass += 1) {
        const overlaps = (rect: NonNullable<typeof panel>) =>
          points.some((point) => {
            const at = map.project([point.lon, point.lat]);
            return pinBoxIntersects(
              container.left + at.x, container.top + at.y,
              TRIP_MAP_MARKER_SIZE, TRIP_MAP_PIN_HEIGHT, rect,
            );
          });
        let changed = false;
        if (panel && topOverlay !== panel && overlaps(panel)) {
          topOverlay = panel;
          changed = true;
        }
        if (bottom && !bottomOverlay && overlaps(bottom)) {
          bottomOverlay = bottom;
          changed = true;
        }
        if (!changed) break;
        map.fitBounds(lngLatBounds, {
          padding: fitPaddingForOverlay(container, topOverlay, TRIP_MAP_PIN_HEIGHT, bottomOverlay),
          maxZoom: 15, animate: false,
        });
      }
    },
    [points],
  );

  const fitToPointsRef = useRef(fitToPoints);
  useEffect(() => {
    fitToPointsRef.current = fitToPoints;
  }, [fitToPoints]);

  const onViewportBboxChangeRef = useRef(onViewportBboxChange);
  useEffect(() => {
    onViewportBboxChangeRef.current = onViewportBboxChange;
  }, [onViewportBboxChange]);
  const reportViewport = useCallback((map: MapLibreMap) => {
    onViewportBboxChangeRef.current?.(viewportSearchBias(map.getBounds()));
  }, []);

  const handleLoad = useCallback(
    (map: MapLibreMap) => {
      mapRef.current = map;
      geometryViewportChange(map);
      fitCleanupRef.current?.();
      // moveend보다 먼저 기록해 드래그 도중 늦은 UI 응답이 시점을 되돌리지 않게 한다.
      const markUserMove = (event: { originalEvent?: unknown }) => {
        if (event.originalEvent) userMovedRef.current = true;
      };
      map.on('movestart', markUserMove);
      fitToPoints(map);
      const stack = overlayStackRef.current;
      let observer: ResizeObserver | null = null;
      let mutations: MutationObserver | null = null;
      if (stack && typeof ResizeObserver !== 'undefined') {
        let previousLayout = '';
        observer = new ResizeObserver(() => {
          if (userMovedRef.current || stack.querySelector('input')?.value.trim()) return;
          const anchor = fitOverlayRect(stack);
          const panel = fitPanelRect(stack);
          const bottom = fitBottomRect(map.getContainer());
          const container = map.getContainer().getBoundingClientRect();
          const layout = JSON.stringify([
            anchor?.bottom, panel?.left, panel?.right, panel?.top, panel?.bottom,
            bottom?.top, container.width, container.height,
          ]);
          if (layout === previousLayout) return;
          previousLayout = layout;
          fitToPointsRef.current(map);
        });
        const observed = new Set<Element>();
        const observePanels = () => {
          const targets = new Set<Element>([
            stack, map.getContainer(), ...stack.querySelectorAll('[data-map-fit-panel]'),
          ]);
          for (const element of observed) {
            if (!targets.has(element)) {
              observer?.unobserve(element);
              observed.delete(element);
            }
          }
          for (const element of targets) {
            if (!observed.has(element)) {
              observer?.observe(element);
              observed.add(element);
            }
          }
        };
        observePanels();
        // 스택 외곽이 max-height로 고정돼도 나중에 나타난 실제 패널을 관찰한다.
        mutations = new MutationObserver(observePanels);
        mutations.observe(stack, { childList: true, subtree: true });
      }
      fitCleanupRef.current = () => {
        observer?.disconnect();
        mutations?.disconnect();
        map.off('movestart', markUserMove);
      };
      scheduleFeatureFetch(map);
      transportViewportChange(map);
      reportViewport(map);
    },
    [
      fitToPoints,
      scheduleFeatureFetch,
      transportViewportChange,
      reportViewport,
      geometryViewportChange,
    ],
  );

  const handleViewportChange = useCallback(
    (map: MapLibreMap) => {
      geometryViewportChange(map);
      scheduleFeatureFetch(map);
      transportViewportChange(map);
      reportViewport(map);
    },
    [scheduleFeatureFetch, transportViewportChange, reportViewport, geometryViewportChange],
  );

  // POI 목록이 바뀌면 경계 재조정. 교통 패널은 상태 조회 뒤에 나타나므로 보이게 되면 한 번 더
  // 맞추되, 그 사이 사용자가 지도를 움직였으면 시점을 빼앗지 않는다.
  useEffect(() => {
    transportVisibleRef.current = transportVisible;
    const map = mapRef.current;
    if (!map) return;
    if (lastFitPointsRef.current !== points) {
      userMovedRef.current = false;
      fitToPoints(map);
    } else if (transportVisible && !lastFitWithPanelRef.current && !userMovedRef.current) {
      fitToPoints(map);
    }
  }, [fitToPoints, points, transportVisible]);

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
  const selectedResolutionNotice = selected
    ? featureResolutionNotice(selected.featureResolutionState)
    : null;

  // hiddenFeatureIds가 바뀌어 현재 선택된 feature가 숨겨지면 선택을 해제한다.
  const [prevHiddenFeatureIds, setPrevHiddenFeatureIds] = useState(hiddenFeatureIds);
  if (hiddenFeatureIds !== prevHiddenFeatureIds) {
    setPrevHiddenFeatureIds(hiddenFeatureIds);
    if (selectedFeature && hiddenFeatureIds?.has(selectedFeature.feature_id)) {
      setSelectedFeature(null);
    }
  }

  // 외부에서 POI 를 선택하면 해당 위치로 이동.
  useEffect(() => {
    if (selected && mapRef.current) {
      // 사용자가 고른 장소로 가는 이동 — 늦게 나타난 교통 패널의 재맞춤이 되돌리지 않게.
      userMovedRef.current = true;
      const map = mapRef.current;
      const container = map.getContainer().getBoundingClientRect();
      const stack = overlayStackRef.current;
      const centerX = container.left + container.width / 2;
      const half = TRIP_MAP_MARKER_SIZE / 2;
      const panel = fitPanelRect(stack);
      const bottom = fitBottomRect(map.getContainer());
      const coversCenter = (rect: NonNullable<typeof panel>) =>
        rect.left < centerX + half && rect.right > centerX - half;
      const padding = fitPaddingForOverlay(
        container, panel && coversCenter(panel) ? panel : fitOverlayRect(stack),
        TRIP_MAP_PIN_HEIGHT, bottom && coversCenter(bottom) ? bottom : null,
      );
      map.flyTo({
        center: [selected.lon, selected.lat],
        offset: [0, (padding.top - padding.bottom) / 2],
      });
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

  const transportControls = (
    <TransportLayerControls
      state={transport}
      onOpenDetail={(target) => {
        setSelectedFeature(null);
        transport.openDetail(target);
      }}
    />
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
        {/* 지도 위 오버레이는 DOM에서 지도보다 **먼저** 둔다 — 키보드 Tab이 캔버스와 마커들을 다 지나야
            검색창에 닿지 않게(위치는 absolute·z-10이라 보이는 모습은 같다). `data-map-overlay`는 길게
            누르기/우클릭 "여기에 장소 추가" 제스처가 오버레이 위에서 시작되지 않게 한다. */}
        {overlayTopLeft != null ? (
          <div
            ref={overlayStackRef}
            className={overlayTopLeftClassName}
            data-testid="trip-map-overlay-stack"
            data-map-overlay=""
          >
            <div className="pointer-events-auto">{overlayTopLeft}</div>
            {showFeatures && (
              <div className="pointer-events-auto mt-2 w-64 max-w-[80%]" data-map-fit-panel="">
                <FeatureGeometryControls state={geometry} />
              </div>
            )}
            {transport.visible && (
              <div className="pointer-events-auto mt-2 w-64 max-w-[70%]">{transportControls}</div>
            )}
          </div>
        ) : (
          (showFeatures || transport.visible) && (
            <div
              className="pointer-events-none absolute left-2 top-2 z-10 w-64 max-w-[70%]"
              data-map-overlay=""
            >
              {showFeatures && (
                <div className="pointer-events-auto">
                  <FeatureGeometryControls state={geometry} />
                </div>
              )}
              {transport.visible && (
                <div className="pointer-events-auto mt-2">{transportControls}</div>
              )}
            </div>
          )
        )}
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
          onMoveEnd={(event) => {
            // 사용자가 끌거나 휠로 움직인 것(originalEvent 있음) — 패널이 늦게 나타나도 다시 맞추지 않는다.
            if (event.originalEvent) userMovedRef.current = true;
            handleViewportChange(event.target as MapLibreMap);
          }}
          onZoomEnd={(event) => {
            if (event.originalEvent) userMovedRef.current = true;
            handleViewportChange(event.target as MapLibreMap);
          }}
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
          fallback={(info) => <MapFallback info={info} minHeightClassName={mapMinHeightClassName} />}
          loadingSkeleton={<MapLoadingSkeleton minHeightClassName={mapMinHeightClassName} />}
          className={`h-full ${mapMinHeightClassName}`}
          unsupportedTileFallback={{ label: 'VWorld tile' }}
        >
          <FeatureGeometryLayers state={geometry} />
          <FeatureGeometryPopup state={geometry} onOpenDetail={setDetailFeatureId} />
          <ClusterLayer
            points={markerPoints}
            radius={28}
            maxZoom={16}
            renderMarker={(clusterPoint) => {
              const marker = clusterPoint as MarkerPoint;
              const resolutionNotice = featureResolutionNotice(marker.point.featureResolutionState);
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
                    resolutionNotice
                      ? `${marker.point.title} (${resolutionNotice})`
                      : marker.point.title
                  }
                  selected={marker.point.poiId === selectedPoiId}
                  zIndex={markerZIndex(marker.point.poiId === selectedPoiId)}
                  highlighted={marker.point.featureResolutionState === 'missing'}
                  ariaLabel={marker.point.title}
                  interactionId={'poi:' + marker.point.poiId}
                  onClick={() => {
                    clearGeometrySelection();
                    setSelectedFeature(null);
                    onSelectPoi?.(marker.point.poiId);
                  }}
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
                    zIndex={markerZIndex(
                      selectedFeature?.feature_id === marker.feature.feature_id,
                    )}
                    title={marker.feature.name}
                    ariaLabel={marker.feature.name}
                    onClick={() => {
                      clearGeometrySelection();
                      onSelectPoi?.(null);
                      setSelectedFeature(marker.feature);
                      // 모바일: weather 외 feature는 상세 시트를 바로 연다(ADR-056).
                      if (mobileLayout && marker.feature.kind !== 'weather') {
                        setDetailFeatureId(marker.feature.feature_id);
                      }
                    }}
                    onContextMenu={(event) => event.preventDefault()}
                  />
                );
              }}
            />
          )}
          {transport.visible && (
            <TransportMarkers
              points={transport.points}
              selectedId={transport.selectedId}
              onSelect={(target) => {
                setSelectedFeature(null);
                transport.openDetail(target);
              }}
            />
          )}
          {selected && !geometry.selection && (
            <Popup
              key={selected.poiId}
              lngLat={[selected.lon, selected.lat]}
              maxWidth="240px"
              closeButton={false}
              onClose={() => onSelectPoi?.(null)}
            >
              <div className="space-y-1">
                <p className="text-sm font-semibold text-ink">{selected.title}</p>
                {selectedResolutionNotice && (
                  <p className="text-xs text-error-text">{selectedResolutionNotice}</p>
                )}
              </div>
            </Popup>
          )}
          {selectedFeature?.coord && (
            <Popup
              lngLat={[selectedFeature.coord.lon, selectedFeature.coord.lat]}
              onClose={() => setSelectedFeature(null)}
              maxWidth="240px"
              closeButton={false}
            >
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-ink">
                      {selectedFeature.name}
                    </p>
                    {selectedFeature.category_label && (
                      <p className="text-xs text-muted">{selectedFeature.category_label}</p>
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
                {selectedFeature.kind !== 'weather' && (
                  <button
                    type="button"
                    onClick={() => setDetailFeatureId(selectedFeature.feature_id)}
                    data-testid="trip-map-detail-open"
                    className="min-h-11 w-full rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
                  >
                    상세보기
                  </button>
                )}
                <button
                  type="button"
                  disabled={!canAddFeature}
                  onClick={() => {
                    onAddFeature?.(selectedFeature);
                    setSelectedFeature(null);
                  }}
                  className="min-h-11 w-full rounded-sm bg-ink px-3 text-sm font-semibold text-canvas hover:bg-ink/90 disabled:opacity-50"
                >
                  일정에 추가
                </button>
              </div>
            </Popup>
          )}
        </VWorldMap>
        <TransportMarkerLegend points={transport.points} />
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
              data-feature-resolution-state={point.featureResolutionState}
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
      <FeatureDetailModalController
        featureId={detailFeatureId}
        fallbackTitle={geometry.selection?.feature.name ?? selectedFeature?.name}
        onClose={() => setDetailFeatureId(null)}
      />
      <TransportDetailDialog target={transport.detail} onClose={transport.closeDetail} />
    </div>
  );
}
