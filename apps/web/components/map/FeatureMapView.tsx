'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { LocateFixed } from 'lucide-react';
import { ApiError, featureApi, userApi } from '@pinvi/api-client';
import type {
  FeatureDetail,
  FeaturesInBoundsResponse,
  FeatureSummary,
  FeatureWeatherCard,
  PlaceSearchResult,
} from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { isAbortError } from '@/lib/abort';
import { boundsToBbox, clampZoom } from '@/lib/featureBounds';
import {
  DEFAULT_MAP_CENTER,
  DEFAULT_MAP_ZOOM,
  MY_LOCATION_ZOOM,
  coarseCoordText,
  locationConsentItems,
  resolveMapCenter,
  resolveMarkerStyle,
  shouldAutoLocate,
  type AutoCenterSkipReason,
  type LocationConsentState,
  type LocationPermissionState,
} from '@pinvi/domain';
import { useUserLocation } from '@pinvi/hooks';
import { webLocationAdapter } from '@/lib/locationAdapter';
import { getLocationConsentState, setLocationConsentGranted } from '@/lib/locationConsent';
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

const DEFAULT_CENTER: [number, number] = [...DEFAULT_MAP_CENTER] as [number, number];
const DEFAULT_ZOOM = DEFAULT_MAP_ZOOM;
/** 자동 센터링 결정이 늦어도 지도가 빈 채로 남지 않도록 in-bounds 조회를 여는 상한. */
const AUTO_CENTER_TIMEOUT_MS = 2_000;

/**
 * 세션당 1회(`docs/architecture/user-location.md` §1) — 모듈 스코프 in-memory 캐시.
 * 좌표를 localStorage/sessionStorage/쿠키/서버 어디에도 남기지 않는다(§7). 탭을 새로 열면 초기화된다.
 */
let autoCenterSession: { done: true; coord: { lon: number; lat: number } | null } | null = null;
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
  data: FeaturesInBoundsResponse,
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
  key: string,
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

  // 카메라는 선언형이다. `VWorldMap`이 center/zoom prop 변화에 반응해 카메라를 옮기고, 사용자가
  // 조작 중이면 moveend까지 적용을 미룬다 — 자동 센터링이 사용자의 손을 가로채지 않는다.
  const [camera, setCamera] = useState<{ center: [number, number]; zoom: number }>({
    center: initialCenter,
    zoom: initialZoom,
  });
  // 자동 센터링 판단 결과(관측용). CI e2e에는 VWorld 키가 없어 실제 카메라를 볼 수 없으므로
  // 결정 자체를 sr-only로 노출해야 검증된다.
  const [autoCenter, setAutoCenter] = useState<{
    resolved: boolean;
    source: 'device' | 'default';
    reason: AutoCenterSkipReason | 'located' | 'out-of-area' | 'locate-failed' | 'pending';
    consent: LocationConsentState;
    permission: LocationPermissionState | 'unknown';
  }>({
    resolved: false,
    source: 'default',
    reason: 'pending',
    consent: 'loading',
    permission: 'unknown',
  });
  // 결정 전에 사용자가 지도를 만졌는지 — 만졌으면 자동 센터링을 영구 취소한다.
  const userInteractedRef = useRef(false);
  // 자동 센터링이 끝나기 전에는 in-bounds 조회를 미룬다(진입 시 두 번 조회 방지).
  const autoCenterSettledRef = useRef(false);
  const pendingFetchRef = useRef<MapLibreMap | null>(null);

  // 최소 1회 조회가 끝났는지 — 조회 전에는 "표시할 장소가 없습니다"라고 단언하지 않는다
  // (지도 키 미설정·초기화 실패 시 지도 fallback과 모순되는 문구가 겹쳐 떴다, T-316 리뷰 P2).
  const [loaded, setLoaded] = useState(false);

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
      setLoaded(true);
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
      setLoaded(true);
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

  // MapLibre는 프로그램 카메라 이동(`easeTo`/`flyTo`/`jumpTo`)에서도 zoomstart/rotatestart/pitchstart를
  // 발화한다. 사용자 제스처만 걸러내려면 원본 DOM 이벤트가 실린 경우만 세야 한다.
  const markUserInteracted = useCallback((event?: { originalEvent?: unknown }) => {
    if (event && event.originalEvent == null) return;
    userInteractedRef.current = true;
  }, []);

  const handleMapLoad = useCallback(
    (map: MapLibreMap) => {
      mapRef.current = map;
      // `VWorldMap`은 moveend/zoomend만 노출한다. 자동 센터링을 취소해야 하는 것은 "사용자가
      // 직접 만졌는가"이므로 시작 이벤트를 직접 바인딩하고, 핸들러가 `originalEvent` 유무로
      // 사용자 제스처와 프로그램 이동을 가른다(`dragstart`만 사용자 전용이다).
      for (const eventName of ['dragstart', 'zoomstart', 'rotatestart', 'pitchstart'] as const) {
        map.on(eventName, markUserInteracted);
      }
      // 자동 센터링이 확정되기 전에 조회하면 곧바로 다른 viewport로 다시 조회하게 된다.
      if (autoCenterSettledRef.current) {
        void fetchInBounds(map);
      } else {
        pendingFetchRef.current = map;
      }
    },
    [fetchInBounds, markUserInteracted],
  );

  /** 자동 센터링 결정이 끝났음을 알리고 보류된 in-bounds 조회를 연다. */
  const settleAutoCenter = useCallback(() => {
    if (autoCenterSettledRef.current) return;
    autoCenterSettledRef.current = true;
    const map = pendingFetchRef.current;
    pendingFetchRef.current = null;
    if (map) void fetchInBounds(map);
  }, [fetchInBounds]);

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

  // 검색 결과(feature/my_poi/address/kakao/naver)로 지도를 이동. feature source면 마커도 선택.
  const handleSearchSelect = useCallback(
    (result: PlaceSearchResult) => {
      const coord = result.coord;
      if (!coord) return;
      if (result.feature_id != null) {
        const style = resolveMarkerStyle({
          upstreamColor: result.marker_color,
          upstreamIcon: result.marker_icon,
          upstreamCategory: result.category,
        });
        setSelected({
          id: result.feature_id,
          lngLat: [coord.lon, coord.lat],
          kind: 'feature',
          color: style.hex,
          markerColor: style.color,
          markerSource: style.source,
          icon: style.icon,
          title: result.name,
          lon: coord.lon,
          lat: coord.lat,
          category: style.category,
          featureId: result.feature_id,
          featureKind: undefined,
        });
      } else {
        // 외부/주소 결과는 feature 상세가 없으므로 선택 해제하고 이동만 한다.
        setSelected(null);
      }
      flyTo(coord.lon, coord.lat, 15);
    },
    [flyTo],
  );

  // 사용자가 버튼으로 명시 요청한 경로 — 높은 정확도, 가까운 줌(user-location.md §1 표).
  const { loading: locating, refresh: locateNow } = useUserLocation(webLocationAdapter, {
    high_accuracy: true,
    max_age_ms: 30_000,
    on_success: (loc) => {
      setUserLocation([loc.coord.lon, loc.coord.lat]);
      setNotice(null);
      flyTo(loc.coord.lon, loc.coord.lat, MY_LOCATION_ZOOM);
    },
    on_error: (err) =>
      setNotice(
        err.code === 'PERMISSION_DENIED'
          ? '위치 권한이 거부되어 있습니다. 브라우저 설정에서 이 사이트의 위치 권한을 허용해 주세요.'
          : err.code === 'UNSUPPORTED'
            ? '이 브라우저는 위치를 지원하지 않습니다.'
            : '위치를 가져오지 못했습니다. 잠시 후 다시 시도해 주세요.',
      ),
  });

  // 위치 기능은 LBS 동의(lbs_tos + location_collection) 확인 후에만(위치정보법 제15·16조).
  const handleMyLocation = useCallback(async () => {
    // 로컬 boolean으로 단축하지 않는다. `locationConsent`는 `true`로만 바뀌는 단방향 래치라,
    // 한 번 동의한 세션은 사용자가 설정에서 철회해도 계속 위치를 잡았다 — 위치정보법 제16조
    // "철회 즉시 위치 기능 비활성"과 어긋난다. 버튼은 사용자의 명시 액션이므로 매번 서버에
    // 확인하는 비용(요청 1회)이 정당하고, 그래야 다른 탭에서의 철회도 즉시 반영된다.
    const state = await getLocationConsentState({ force: true });
    if (state === 'granted') {
      setLocationConsent(true);
      void locateNow();
      return;
    }
    setLocationConsent(false);
    // 버튼은 사용자의 명시 액션이므로 여기서는 동의 다이얼로그를 띄운다(자동 경로와 다른 점).
    setConsentError(null);
    setConsentOpen(true);
  }, [locateNow]);

  const handleConsentAgree = useCallback(async () => {
    setConsentSaving(true);
    setConsentError(null);
    try {
      await userApi(apiClient).putConsents(locationConsentItems());
      setLocationConsent(true);
      // 방금 기록한 동의를 공유 캐시에도 반영해 다른 표면이 서버를 다시 묻지 않게 한다.
      setLocationConsentGranted();
      setConsentOpen(false);
      void locateNow();
    } catch (err) {
      setConsentError(err instanceof ApiError ? err.message : '동의 저장에 실패했습니다.');
    } finally {
      setConsentSaving(false);
    }
  }, [locateNow]);

  /**
   * 진입 시 자동 센터링(T-325, `docs/architecture/user-location.md` §1 "지도 초기 중심점").
   *
   * 게이트 순서가 계약이다 — 권한이 `granted`가 **아니면 네트워크도 좌표 취득도 하지 않는다**.
   * 권한 조회는 프롬프트를 띄우지 않는 로컬 조회이므로, 이 순서 덕분에 권한 없는 사용자에게
   * 동의 조회 왕복조차 발생하지 않는다. 실제 좌표 취득은 동의까지 확인한 뒤에만 일어난다.
   *
   * 자동 경로는 **어떤 모달도 띄우지 않는다**. 동의가 없거나 확인되지 않으면 조용히 기본 중심점을
   * 유지하고, 사용자가 "내 위치" 버튼을 눌렀을 때만 동의 다이얼로그를 연다(다크 패턴 회피).
   */
  useEffect(() => {
    let alive = true;
    // 결정이 지연돼도 지도가 빈 채로 남지 않도록 조회를 여는 상한.
    const timeout = setTimeout(settleAutoCenter, AUTO_CENTER_TIMEOUT_MS);

    const finish = (
      next: Partial<Omit<typeof autoCenter, 'resolved'>> & {
        reason: (typeof autoCenter)['reason'];
      },
    ) => {
      if (!alive) return;
      setAutoCenter((prev) => ({ ...prev, ...next, resolved: true }));
      settleAutoCenter();
    };

    void (async () => {
      const permission = (await webLocationAdapter.getPermissionState?.()) ?? 'prompt';
      if (!alive) return;

      const gateWithoutConsent = shouldAutoLocate({
        permission,
        consent: 'granted',
        gate: { alreadyResolved: false, userInteracted: userInteractedRef.current },
      });
      if (!gateWithoutConsent.proceed) {
        // 세션에 굳히지 않는다 — 권한은 동의보다 오히려 세션 중에 더 자주 바뀐다(브라우저 설정).
        finish({ reason: gateWithoutConsent.skipReason, permission });
        return;
      }

      // 동의는 **매번 서버에서 다시 확인한다**. 캐시된 'granted'를 믿으면 방금 철회한 사용자가
      // 지도로 돌아왔을 때 좌표를 취득하게 된다(위치정보법 제16조 — 철회 즉시 비활성).
      // 자동 경로는 세션당 1회이고 이미 권한 게이트 뒤이므로 왕복 비용도 문제가 되지 않는다.
      const consent = await getLocationConsentState({ force: true });
      if (!alive) return;

      const gate = shouldAutoLocate({
        permission,
        consent,
        gate: { alreadyResolved: false, userInteracted: userInteractedRef.current },
      });
      if (!gate.proceed) {
        // 동의 실패는 세션에 굳히지 않는다 — 사용자가 버튼으로 동의하면 다음 진입에서 바로 걸린다.
        finish({ reason: gate.skipReason, permission, consent });
        return;
      }

      // 같은 세션에서 이미 측위했다면 재측위하지 않는다(§1 "세션당 1회").
      // 이 분기는 **권한·동의를 모두 통과한 뒤**에만 닿는다 — 캐시가 게이트를 우회하면 안 된다.
      if (autoCenterSession?.done) {
        const cachedCoord = autoCenterSession.coord;
        if (cachedCoord && !userInteractedRef.current) {
          const outcome = resolveMapCenter({ deviceCoord: cachedCoord });
          if (outcome.source === 'device') {
            setCamera({ center: outcome.center, zoom: outcome.zoom });
            setUserLocation(outcome.center);
          }
        }
        finish({
          reason: 'already-resolved',
          source: cachedCoord ? 'device' : 'default',
          permission,
          consent,
        });
        return;
      }

      try {
        // 자동 경로는 낮은 정확도 + 캐시 허용(시군구 수준이면 충분, 배터리·프라이버시 최소수집).
        const loc = await webLocationAdapter.getCurrentPosition({
          high_accuracy: false,
          max_age_ms: 300_000,
        });
        if (!alive) return;
        const outcome = resolveMapCenter({ deviceCoord: loc.coord });
        // 국내 좌표만 캐시한다 — 국외 좌표를 캐시하면 재진입 때 안내 없이 조용히 넘어간다.
        autoCenterSession = { done: true, coord: outcome.source === 'device' ? loc.coord : null };
        if (outcome.source === 'device') {
          if (!userInteractedRef.current) {
            setCamera({ center: outcome.center, zoom: outcome.zoom });
          }
          setUserLocation([loc.coord.lon, loc.coord.lat]);
          finish({ reason: 'located', source: 'device', permission, consent });
          return;
        }
        // 국내 범위 밖이면 센터링도 마커도 하지 않고 이유만 알린다(ADR-018).
        setNotice('현재 위치가 국내 서비스 범위 밖이라 기본 위치(서울)를 표시합니다.');
        finish({ reason: 'out-of-area', permission, consent });
      } catch {
        if (!alive) return;
        // 자동 경로는 재시도하지 않는다 — 5초 뒤 카메라를 빼앗는 편이 더 나쁘다. 버튼은 언제든 쓸 수 있다.
        autoCenterSession = { done: true, coord: null };
        setNotice(
          '현재 위치를 확인하지 못해 기본 위치를 표시합니다. 내 위치 버튼으로 다시 시도할 수 있어요.',
        );
        finish({ reason: 'locate-failed', permission, consent });
      }
    })();

    return () => {
      alive = false;
      clearTimeout(timeout);
    };
    // 마운트 1회만 — 의존성을 늘리면 재측위가 반복된다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
    // 높이는 셸이 흘려보낸다 — 바깥 래퍼까지 flex 사슬을 이어야 `h-full`이 실제로 해소된다
    // (사슬이 끊기면 content 높이로 붕괴한다, T-316 리뷰 P1).
    <div className={`flex min-h-0 flex-col ${className ?? ''}`} data-testid="feature-map">
      <div className="flex min-h-[320px] flex-1 flex-col overflow-hidden rounded-sm border border-hairline bg-canvas">
        <div className="relative min-h-0 flex-1">
          <div className="pointer-events-none absolute inset-0 z-10">
            <div className="pointer-events-auto absolute left-3 top-3 w-72 max-w-[80vw]">
              <MapSearchBox onSelect={handleSearchSelect} />
              {/* 상태는 상시 표가 아니라 **일이 생겼을 때만** 뜬다(DESIGN.md 상태 UI). */}
              {error ? (
                <p
                  role="alert"
                  className="mt-1 flex flex-wrap items-center gap-2 rounded-sm bg-error-bg px-2 py-1.5 text-xs text-error-text shadow-card"
                  data-testid="feature-map-error"
                >
                  <span className="min-w-0">{error}</span>
                  <button
                    type="button"
                    onClick={() => {
                      const map = mapRef.current;
                      if (map) void fetchInBounds(map);
                    }}
                    className="focus-ring shrink-0 rounded-sm border border-error-text px-2 py-0.5 font-semibold"
                  >
                    다시 불러오기
                  </button>
                </p>
              ) : loading ? (
                <p
                  className="mt-1 rounded-sm bg-surface-soft px-2 py-1 text-xs text-body shadow-card"
                  role="status"
                  aria-busy="true"
                  data-testid="feature-map-loading"
                >
                  장소를 불러오는 중…
                </p>
              ) : loaded && points.length === 0 ? (
                <p
                  className="mt-1 rounded-sm bg-surface-soft px-2 py-1 text-xs text-body shadow-card"
                  role="status"
                  data-testid="feature-map-empty"
                >
                  이 범위에 표시할 장소가 없습니다 — 지도를 움직여 보세요.
                </p>
              ) : null}
              {notice && (
                <p className="mt-1 rounded-sm bg-surface-soft px-2 py-1 text-xs text-body shadow-card">
                  {notice}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => void handleMyLocation()}
              aria-label="내 위치로 이동"
              aria-busy={locating}
              disabled={locating}
              data-testid="map-my-location"
              className="focus-ring pointer-events-auto absolute bottom-4 right-3 flex size-11 items-center justify-center rounded-full border border-hairline bg-canvas text-ink shadow-card hover:bg-surface-soft disabled:cursor-not-allowed disabled:text-muted"
            >
              <LocateFixed
                className={`h-5 w-5 ${locating ? 'animate-pulse' : ''}`}
                aria-hidden="true"
              />
            </button>
            {/* 자동 센터링 결정의 관측 창구. CI e2e에는 VWorld 키가 없어 실제 카메라를 볼 수 없으므로
                결정 자체를 노출해야 검증된다. 좌표는 4자리로 절사해 원좌표를 DOM에 싣지 않는다. */}
            <div
              className="sr-only"
              aria-hidden="true"
              data-testid="map-center-state"
              data-resolved={autoCenter.resolved ? 'true' : 'false'}
              data-source={autoCenter.source}
              data-reason={autoCenter.reason}
              data-consent={autoCenter.consent}
              data-permission={autoCenter.permission}
              data-center-lon={coarseCoordText(camera.center[0])}
              data-center-lat={coarseCoordText(camera.center[1])}
              data-zoom={String(camera.zoom)}
            />
          </div>

          <VWorldMap
            apiKey={apiKey}
            center={camera.center}
            zoom={camera.zoom}
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
                      className="min-h-11 w-full rounded-sm bg-ink px-3 text-sm font-semibold text-canvas hover:bg-ink/90"
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
              <div className="min-w-44 overflow-hidden rounded-sm border border-hairline bg-canvas py-1 text-sm shadow-card">
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
