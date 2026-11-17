import { useCallback, useEffect, useMemo, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { transportApi } from '@pinvi/api-client';
import type { TransportItem, TransportLayer, TransportLayerResult } from '@pinvi/schemas';
import {
  TRANSPORT_LAYER_META,
  TRANSPORT_NEAR_MAX_POINTS,
  dedupeTransportNearPoints,
  parseTransportMarkerId,
  resolveMarkerStyle,
  transportItemTitle,
  transportMarkerId,
  transportNearPointsKey,
  withUnavailableTransportLayers,
} from '@pinvi/domain';
import { apiClient } from './api';

/** 칩을 누른 뒤 조회까지 — 연달아 누르면 마지막 상태로 한 번만 조회한다(웹 `useTransportLayers`와 같다). */
export const TRIP_TRANSPORT_DEBOUNCE_MS = 250;
/** 같은 장소·레이어 조합은 이 시간 동안 다시 조회하지 않는다. */
export const TRIP_TRANSPORT_CACHE_MS = 60_000;
const LIMIT = 200;
/** 신선도 문구("n분 전")를 다시 그리는 주기. */
const NOW_TICK_MS = 30_000;

export type TripTransportMarker = {
  id: string;
  coordinate: [number, number];
  color: string;
  ariaLabel: string;
};

type NearFetched = {
  results: TransportLayerResult[];
  radiusM: Partial<Record<TransportLayer, number>> | null;
  receivedAt: number;
};

/**
 * 여행 지도 교통 레이어(ADR-076) — 여행 장소 반경(주유소 10 km·교통 돌발 20 km, `/transport/markers-near`).
 *
 * 웹 `useTransportLayers`의 반경 모드와 같은 규칙이다.
 * - 지도 이동·줌으로는 다시 조회하지 않는다. 장소 좌표(5자리 반올림 값)나 켠 레이어가 바뀔 때만 조회한다.
 * - 칩을 누르면 250 ms 뒤 조회, 같은 장소·레이어 조합은 60초 캐시. 최소 줌 규칙은 쓰지 않는다.
 * - 응답에 빠진 레이어·요청 실패는 "불러올 수 없음"이다. 반경 문구는 서버 `radius_m`에서 온다.
 *
 * `active=false`면 아무것도 조회하지 않는다(`/transport/*`는 로그인 필요). 기능이 꺼져 있으면 `visible=false`.
 */
export function useTripTransport({
  active,
  points,
}: {
  active: boolean;
  points: ReadonlyArray<{ lon: number; lat: number }>;
}) {
  // 좌표 배열의 identity가 아니라 값으로 조회한다 — 화면이 렌더마다 새 배열을 만들어도 조회는 한 번.
  const nearKey = transportNearPointsKey(
    dedupeTransportNearPoints(points).slice(0, TRANSPORT_NEAR_MAX_POINTS),
  );
  const nearPoints = useMemo(
    () =>
      nearKey === ''
        ? []
        : nearKey.split(';').map((pair) => {
            const [lon, lat] = pair.split(',').map(Number);
            return { lon: lon ?? 0, lat: lat ?? 0 };
          }),
    [nearKey],
  );

  const [enabled, setEnabled] = useState<ReadonlySet<TransportLayer>>(() => new Set());
  // 조회에 쓰는 레이어 — 칩 상태를 디바운스해 따라간다.
  const [requested, setRequested] = useState<ReadonlySet<TransportLayer>>(enabled);
  useEffect(() => {
    if (requested === enabled) return;
    const id = setTimeout(() => setRequested(enabled), TRIP_TRANSPORT_DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [enabled, requested]);

  const statusQuery = useQuery({
    queryKey: ['transport', 'status'],
    queryFn: ({ signal }) => transportApi(apiClient).status({ signal }),
    enabled: active,
    retry: false,
    staleTime: 5 * 60_000,
  });
  const visible = active && statusQuery.data?.enabled === true;

  // 반경 모드는 최소 줌 규칙 없이 켠 레이어를 모두 조회한다(반경이 이미 범위를 좁힌다).
  const layers = useMemo(
    () =>
      TRANSPORT_LAYER_META.filter((meta) => requested.has(meta.layer)).map((meta) => meta.layer),
    [requested],
  );

  const nearQuery = useQuery({
    queryKey: ['transport', 'near', nearKey, layers.join(',')],
    queryFn: async ({ signal }): Promise<NearFetched> => {
      const data = await transportApi(apiClient).markersNear(
        { points: nearPoints, layers, limit: LIMIT },
        { signal },
      );
      return {
        results: withUnavailableTransportLayers(data.layers, layers),
        radiusM: data.radius_m ?? null,
        receivedAt: Date.now(),
      };
    },
    enabled: visible && nearPoints.length > 0 && layers.length > 0,
    // 장소·레이어가 바뀌어 다시 조회하는 동안 지난 결과를 유지한다(꺼 둔 레이어는 아래에서 감춘다).
    placeholderData: keepPreviousData,
    retry: false,
    staleTime: TRIP_TRANSPORT_CACHE_MS,
  });

  const fetched: NearFetched | null = useMemo(() => {
    if (layers.length === 0 || nearPoints.length === 0) return null;
    // 요청 자체가 실패했다(응답 해석 실패 포함) — 요청한 레이어를 "불러올 수 없음"으로 보인다.
    if (nearQuery.isError) {
      return {
        results: withUnavailableTransportLayers([], layers),
        radiusM: null,
        receivedAt: nearQuery.errorUpdatedAt,
      };
    }
    return nearQuery.data ?? null;
  }, [nearQuery.isError, nearQuery.errorUpdatedAt, nearQuery.data, layers, nearPoints.length]);

  // 꺼 둔 레이어의 지난 결과는 감춘다(토글 직후 응답 전 깜빡임 방지).
  const results = useMemo(
    () => (fetched ? fetched.results.filter((result) => enabled.has(result.layer)) : []),
    [fetched, enabled],
  );

  // 신선도 = Map `age_seconds` + 받은 뒤 흐른 시간. 시계는 받은 시각보다 앞서지 않게 둔다.
  const [tickMs, setTickMs] = useState(() => Date.now());
  const receivedAt = fetched?.receivedAt ?? null;
  const hasResults = receivedAt != null;
  useEffect(() => {
    if (!hasResults) return;
    const id = setInterval(() => setTickMs(Date.now()), NOW_TICK_MS);
    return () => clearInterval(id);
  }, [hasResults]);
  const nowMs = Math.max(tickMs, receivedAt ?? 0);

  const items = useMemo(
    () => results.flatMap((result) => (result.status === 'ok' ? result.items : [])),
    [results],
  );

  const markers: TripTransportMarker[] = useMemo(
    () =>
      items.flatMap((item) => {
        if (!item.coord) return [];
        const style = resolveMarkerStyle({
          upstreamColor: item.marker_color,
          upstreamIcon: item.marker_icon,
          upstreamCategory: item.category,
        });
        return [
          {
            id: transportMarkerId(item.layer, item.feature_id),
            coordinate: [item.coord.lon, item.coord.lat] as [number, number],
            color: style.hex,
            ariaLabel: transportItemTitle(item),
          },
        ];
      }),
    [items],
  );

  /** 마커 press id → 항목. transport 마커가 아니면(여행 장소 등)·지금 결과에 없으면 null. */
  const itemForMarker = useCallback(
    (id: string): TransportItem | null => {
      const parsed = parseTransportMarkerId(id);
      if (!parsed) return null;
      return (
        items.find((i) => i.layer === parsed.layer && i.feature_id === parsed.featureId) ?? null
      );
    },
    [items],
  );

  const toggle = useCallback((layer: TransportLayer) => {
    setEnabled((prev) => {
      const next = new Set(prev);
      if (next.has(layer)) next.delete(layer);
      else next.add(layer);
      return next;
    });
  }, []);

  return {
    visible,
    status: statusQuery.data ?? null,
    enabled,
    toggle,
    /** 켠 레이어의 결과가 아직 없으면 "불러오는 중"을 보일 수 있는가(기준 장소가 있어 조회가 나간다). */
    loading: nearPoints.length > 0,
    results,
    radiusM: fetched?.radiusM ?? null,
    receivedAt,
    nowMs,
    markers,
    itemForMarker,
  };
}

export type TripTransportState = ReturnType<typeof useTripTransport>;
