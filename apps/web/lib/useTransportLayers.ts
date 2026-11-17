'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { transportApi } from '@pinvi/api-client';
import type {
  TransportItem,
  TransportLayer,
  TransportLayerResult,
  TransportStatusResponse,
} from '@pinvi/schemas';
import {
  requestableTransportLayers,
  TRANSPORT_LAYER_META,
  TRANSPORT_NEAR_MAX_POINTS,
  resolveMarkerStyle,
  transportItemTitle,
  transportMarkerId,
  transportNearPointsKey,
  withUnavailableTransportLayers,
} from '@pinvi/domain';
import type { MapLibreMap } from '@/components/map/vworldPrimitives';
import { apiClient } from '@/lib/api';
import { isAbortError } from '@/lib/abort';
import { boundsToBbox, clampZoom } from '@/lib/featureBounds';

const DEBOUNCE_MS = 250;
const CACHE_MAX = 32;
const CACHE_TTL_MS = 60_000;
const LIMIT = 200;
/** 신선도 문구("n분 전")를 다시 그리는 주기. */
const NOW_TICK_MS = 30_000;

export type TransportMapPoint = {
  id: string;
  lngLat: [number, number];
  layer: TransportLayer;
  featureId: string;
  title: string;
  icon: string;
  color: string;
  markerColor: string;
};

export type TransportDetailTarget = {
  layer: TransportLayer;
  featureId: string;
  title: string;
};

type Fetched = {
  results: TransportLayerResult[];
  /** 응답을 받은 시각 — 신선도는 Map `age_seconds` + 이후 경과로 센다(ADR-076). */
  receivedAt: number;
};

function toPoints(results: readonly TransportLayerResult[]): TransportMapPoint[] {
  return results.flatMap((result) =>
    result.status !== 'ok'
      ? []
      : result.items.flatMap((item: TransportItem) => {
          if (!item.coord) return [];
          const style = resolveMarkerStyle({
            upstreamColor: item.marker_color,
            upstreamIcon: item.marker_icon,
            upstreamCategory: item.category,
          });
          return [
            {
              id: transportMarkerId(item.layer, item.feature_id),
              lngLat: [item.coord.lon, item.coord.lat] as [number, number],
              layer: item.layer,
              featureId: item.feature_id,
              title: transportItemTitle(item),
              icon: style.icon,
              color: style.hex,
              markerColor: style.color,
            },
          ];
        }),
  );
}

/**
 * 지도 transport 레이어 상태(ADR-076) — 탐색 지도·여행 지도 공용.
 *
 * `active=false`면 아무 요청도 하지 않는다(비로그인 공유 화면은 반드시 false — `/transport/*`는 로그인
 * 필요라 401이 로그인 화면 이동을 부른다). 실패는 조용히 레이어 상태로만 보인다 — 장소 마커와 여행 화면이
 * 이 기능 때문에 깨지면 안 된다.
 */
export function useTransportLayers({
  active,
  nearPoints = null,
}: {
  active: boolean;
  /**
   * 여행 지도: 기준 장소(여행 장소) 좌표. 주면 viewport가 아니라 이 장소들의 반경(주유소 10 km·교통 돌발
   * 20 km — 서버 정책, `/transport/markers-near`)으로 조회하고 지도 이동·줌으로 다시 조회하지 않는다.
   * `null`이면(탐색 지도) 지금처럼 viewport로 조회한다.
   */
  nearPoints?: ReadonlyArray<{ lon: number; lat: number }> | null;
}) {
  const nearMode = nearPoints != null;
  // 좌표 배열의 identity가 아니라 값으로 다시 조회한다 — 부모가 렌더마다 새 배열을 만들어도 조회는 한 번.
  const nearKey = nearPoints ? transportNearPointsKey(nearPoints) : null;
  const nearPointsRef = useRef(nearPoints);
  useEffect(() => {
    nearPointsRef.current = nearPoints;
  }, [nearPoints]);
  const [radiusM, setRadiusM] = useState<Partial<Record<TransportLayer, number>> | null>(null);
  const [status, setStatus] = useState<TransportStatusResponse | null>(null);
  const [enabled, setEnabled] = useState<ReadonlySet<TransportLayer>>(() => new Set());
  const [zoom, setZoom] = useState<number | null>(null);
  const [fetched, setFetched] = useState<Fetched | null>(null);
  const [detail, setDetail] = useState<TransportDetailTarget | null>(null);
  // 지도가 한 번이라도 viewport를 알렸는가 — 없으면(VWorld fallback) 조회가 없어 "불러오는 중"을 띄우지 않는다.
  const [hasMap, setHasMap] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());

  const mapRef = useRef<MapLibreMap | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const latestRef = useRef(0);
  const cacheRef = useRef(
    new Map<
      string,
      Fetched & { cachedAt: number; radiusM: Partial<Record<TransportLayer, number>> | null }
    >(),
  );

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    transportApi(apiClient)
      .status({ signal: controller.signal })
      .then(setStatus)
      .catch(() => {
        // 상태를 못 읽으면 컨트롤을 숨긴다 — 지도 본 기능에 영향이 없어야 한다.
      });
    return () => controller.abort();
  }, [active]);

  const visible = active && status?.enabled === true;
  const hasData = fetched != null;

  // 신선도 문구만 다시 그린다 — 기능이 꺼져 있거나 보여 줄 결과가 없으면 지도 화면을 깨우지 않는다.
  useEffect(() => {
    if (!visible || !hasData) return;
    const id = setInterval(() => setNowMs(Date.now()), NOW_TICK_MS);
    return () => clearInterval(id);
  }, [visible, hasData]);

  const fetchNow = useCallback(
    async (map: MapLibreMap | null, layersOn: ReadonlySet<TransportLayer>) => {
      const requestId = latestRef.current + 1;
      latestRef.current = requestId;
      abortRef.current?.abort();
      const near = nearPointsRef.current;
      let layers: TransportLayer[];
      let key: string;
      let request: (signal: AbortSignal) => Promise<{
        layers: TransportLayerResult[];
        radius_m?: Partial<Record<TransportLayer, number>>;
      }>;
      if (near) {
        // 여행 장소 반경 — 줌과 무관하게 켠 레이어를 모두 조회한다(반경이 이미 범위를 좁힌다).
        if (map) setZoom(clampZoom(map.getZoom()));
        layers = TRANSPORT_LAYER_META.filter((meta) => layersOn.has(meta.layer)).map(
          (meta) => meta.layer,
        );
        const points = near.slice(0, TRANSPORT_NEAR_MAX_POINTS);
        key = `near:${transportNearPointsKey(points)}:${layers.join(',')}`;
        request = (signal) =>
          transportApi(apiClient).markersNear({ points, layers, limit: LIMIT }, { signal });
      } else {
        if (!map) return;
        const z = clampZoom(map.getZoom());
        setZoom(z);
        layers = requestableTransportLayers(layersOn, z);
        const bbox = boundsToBbox(map.getBounds(), z);
        key = `${z}:${bbox}:${layers.join(',')}`;
        request = (signal) =>
          transportApi(apiClient).markersInBounds(
            { bbox, zoom: z, layers, limit: LIMIT },
            { signal },
          );
      }
      if (layers.length === 0) {
        setFetched(null);
        return;
      }
      const cached = cacheRef.current.get(key);
      if (cached && Date.now() - cached.cachedAt <= CACHE_TTL_MS) {
        setFetched({ results: cached.results, receivedAt: cached.receivedAt });
        if (cached.radiusM) setRadiusM(cached.radiusM);
        return;
      }
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const data = await request(controller.signal);
        if (requestId !== latestRef.current) return;
        const radius = data.radius_m ?? null;
        if (radius) setRadiusM(radius);
        const receivedAt = Date.now();
        // 요청한 레이어가 응답에 없으면 "불러오는 중"에 머물지 않게 불러올 수 없음으로 채운다.
        const results = withUnavailableTransportLayers(data.layers, layers);
        const cache = cacheRef.current;
        cache.delete(key);
        cache.set(key, { results, receivedAt, cachedAt: receivedAt, radiusM: radius });
        while (cache.size > CACHE_MAX) {
          const first = cache.keys().next().value;
          if (first == null) break;
          cache.delete(first);
        }
        setFetched({ results, receivedAt });
        setNowMs(receivedAt);
      } catch (err) {
        if (isAbortError(err) || requestId !== latestRef.current) return;
        // 요청 자체가 실패했다(응답 해석 실패 포함) — 요청한 레이어를 "불러올 수 없음"으로 보인다.
        // 다음 지도 이동이 곧 재시도다.
        setFetched({ results: withUnavailableTransportLayers([], layers), receivedAt: Date.now() });
      }
    },
    [],
  );

  const enabledRef = useRef(enabled);
  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);
  // 콜백 identity를 고정한다 — 상태 응답이 와도 지도 쪽 콜백들이 다시 만들어지지 않게.
  const visibleRef = useRef(visible);
  useEffect(() => {
    visibleRef.current = visible;
  }, [visible]);

  /** 지도 load·moveend·zoomend에서 부른다(디바운스). 꺼져 있으면 아무것도 하지 않는다. */
  const onViewportChange = useCallback(
    (map: MapLibreMap) => {
      mapRef.current = map;
      setHasMap(true);
      // 여행 장소 반경 모드는 지도 이동과 무관하다 — 장소·레이어가 바뀔 때만 조회한다.
      if (!visibleRef.current || nearPointsRef.current) return;
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        // 아직 움직이는 중(애니메이션 맞춤)이면 건너뛴다 — 끝나는 moveend가 다시 부른다.
        if (map.isMoving()) return;
        void fetchNow(map, enabledRef.current);
      }, DEBOUNCE_MS);
    },
    [fetchNow],
  );

  const toggle = useCallback(
    (layer: TransportLayer) => {
      const next = new Set(enabledRef.current);
      if (next.has(layer)) next.delete(layer);
      else next.add(layer);
      enabledRef.current = next;
      setEnabled(next);
      // 바로 조회하지 않고 지도가 멈출 때까지 기다린다 — 조회는 그때의 bounds를 읽고, 그 사이 지도 이동의
      // moveend는 같은 디바운스를 다시 미룬다. 결과가 와서 교통 패널이 자라면(#619 재맞춤) 지도가 옮겨지고
      // moveend가 새 bounds로 한 번 더 조회한다(#686 운영 진단 2026-11-08).
      if (debounceRef.current) clearTimeout(debounceRef.current);
      // 진행 중인 이전 조회는 바로 끊는다(꺼 둔 레이어의 늦은 응답이 남지 않게).
      abortRef.current?.abort();
      if (nearPointsRef.current) {
        // 여행 장소 반경은 bounds를 읽지 않는다 — 지도 상태와 무관하게 잠시 뒤 조회한다.
        debounceRef.current = setTimeout(
          () => void fetchNow(mapRef.current, enabledRef.current),
          DEBOUNCE_MS,
        );
        return;
      }
      if (!mapRef.current) return;
      debounceRef.current = setTimeout(() => {
        const map = mapRef.current;
        // 켠 직후 재맞춤이 애니메이션 중이면(한 핀 flyTo) 그 moveend가 조회한다.
        if (map && !map.isMoving()) void fetchNow(map, enabledRef.current);
      }, DEBOUNCE_MS);
    },
    [fetchNow],
  );

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      abortRef.current?.abort();
    };
  }, []);

  // 컨트롤이 보이기 시작했을 때(상태 응답 도착) 이미 떠 있는 지도로 한 번 맞춘다.
  // 여행 장소 반경 모드는 장소 목록(값)이 바뀌어도 다시 조회한다.
  useEffect(() => {
    if (visible && (mapRef.current || nearKey != null) && enabledRef.current.size > 0) {
      void fetchNow(mapRef.current, enabledRef.current);
    }
  }, [visible, nearKey, fetchNow]);

  const results = useMemo(() => {
    if (!fetched) return [] as TransportLayerResult[];
    // 꺼 둔 레이어의 지난 결과는 감춘다(토글 직후 응답 전 깜빡임 방지).
    return fetched.results.filter((result) => enabled.has(result.layer));
  }, [fetched, enabled]);
  const points = useMemo(() => toPoints(results), [results]);
  const selectedId = detail ? transportMarkerId(detail.layer, detail.featureId) : null;

  return {
    visible,
    status,
    enabled,
    // 반경 모드는 지도 없이도 조회한다 — 켠 레이어는 바로 "불러오는 중"을 차지한다.
    hasMap: hasMap || nearMode,
    /** 여행 장소 반경 모드(줌 안내 없음, 반경 문구). */
    nearMode,
    /** 반경 모드에서 서버가 알려 준 레이어별 반경(m). */
    radiusM,
    zoom,
    results,
    receivedAt: fetched?.receivedAt ?? null,
    nowMs,
    points,
    selectedId,
    toggle,
    onViewportChange,
    detail,
    openDetail: setDetail,
    closeDetail: useCallback(() => setDetail(null), []),
  };
}

export type TransportLayersState = ReturnType<typeof useTransportLayers>;
