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
  resolveMarkerStyle,
  transportItemTitle,
  transportMarkerId,
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
export function useTransportLayers({ active }: { active: boolean }) {
  const [status, setStatus] = useState<TransportStatusResponse | null>(null);
  const [enabled, setEnabled] = useState<ReadonlySet<TransportLayer>>(() => new Set());
  const [zoom, setZoom] = useState<number | null>(null);
  const [fetched, setFetched] = useState<Fetched | null>(null);
  const [detail, setDetail] = useState<TransportDetailTarget | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());

  const mapRef = useRef<MapLibreMap | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const latestRef = useRef(0);
  const cacheRef = useRef(new Map<string, Fetched & { cachedAt: number }>());

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
    async (map: MapLibreMap, layersOn: ReadonlySet<TransportLayer>) => {
      const requestId = latestRef.current + 1;
      latestRef.current = requestId;
      abortRef.current?.abort();
      const z = clampZoom(map.getZoom());
      setZoom(z);
      const layers = requestableTransportLayers(layersOn, z);
      if (layers.length === 0) {
        setFetched(null);
        return;
      }
      const bbox = boundsToBbox(map.getBounds(), z);
      const key = `${z}:${bbox}:${layers.join(',')}`;
      const cached = cacheRef.current.get(key);
      if (cached && Date.now() - cached.cachedAt <= CACHE_TTL_MS) {
        setFetched({ results: cached.results, receivedAt: cached.receivedAt });
        return;
      }
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const data = await transportApi(apiClient).markersInBounds(
          { bbox, zoom: z, layers, limit: LIMIT },
          { signal: controller.signal },
        );
        if (requestId !== latestRef.current) return;
        const receivedAt = Date.now();
        const cache = cacheRef.current;
        cache.delete(key);
        cache.set(key, { results: data.layers, receivedAt, cachedAt: receivedAt });
        while (cache.size > CACHE_MAX) {
          const first = cache.keys().next().value;
          if (first == null) break;
          cache.delete(first);
        }
        setFetched({ results: data.layers, receivedAt });
        setNowMs(receivedAt);
      } catch (err) {
        if (isAbortError(err) || requestId !== latestRef.current) return;
        // 요청 자체가 실패했다(응답 해석 실패 포함) — 요청한 레이어를 "불러올 수 없음"으로 보인다.
        // 다음 지도 이동이 곧 재시도다.
        setFetched({
          results: layers.map((layer) => ({
            layer,
            status: 'unavailable' as const,
            reason: 'UPSTREAM_UNAVAILABLE' as const,
            truncated: false,
            items: [],
          })),
          receivedAt: Date.now(),
        });
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
      if (!visibleRef.current) return;
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
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
      if (debounceRef.current) clearTimeout(debounceRef.current);
      const map = mapRef.current;
      if (map) void fetchNow(map, next);
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
  useEffect(() => {
    if (visible && mapRef.current && enabledRef.current.size > 0) {
      void fetchNow(mapRef.current, enabledRef.current);
    }
  }, [visible, fetchNow]);

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
