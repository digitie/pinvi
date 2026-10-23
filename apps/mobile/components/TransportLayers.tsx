import { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { transportApi } from '@pinvi/api-client';
import type { TransportItem, TransportLayer, TransportLayerResult } from '@pinvi/schemas';
import {
  TRANSPORT_LAYER_META,
  formatFuelPrice,
  fuelProductLabel,
  paletteHex,
  parseTransportMarkerId,
  requestableTransportLayers,
  transportFreshnessAgeSeconds,
  transportFreshnessLabel,
  transportItemTitle,
  transportLayerLabel,
  transportMarkerId,
} from '@pinvi/domain';
import { apiClient } from '../lib/api';
import { Body, Card, Muted, Subheading } from './ui';

/** `vworld-map-rn` `onCameraChanged`가 주는 카메라. */
export type MapCamera = {
  center: [number, number];
  zoom: number;
  bounds?: { ne: [number, number]; sw: [number, number] };
};

const DEBOUNCE_MS = 400;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/**
 * 카메라 → `lng_min,lat_min,lng_max,lat_max`(국내 범위로 clamp). bounds가 없으면 중심·줌으로 어림한다.
 * 소수 3자리로 반올림해 작은 흔들림이 새 요청이 되지 않게 한다.
 */
export function cameraBbox(camera: MapCamera): string {
  let west: number;
  let south: number;
  let east: number;
  let north: number;
  if (camera.bounds) {
    [west, south] = camera.bounds.sw;
    [east, north] = camera.bounds.ne;
  } else {
    const lonSpan = 360 / 2 ** camera.zoom;
    const latSpan = lonSpan * 1.6;
    [west, south] = [camera.center[0] - lonSpan, camera.center[1] - latSpan / 2];
    [east, north] = [camera.center[0] + lonSpan, camera.center[1] + latSpan / 2];
  }
  const w = clamp(Math.min(west, east), 124, 132);
  const e = clamp(Math.max(west, east), 124, 132);
  const s = clamp(Math.min(south, north), 33, 43);
  const n = clamp(Math.max(south, north), 33, 43);
  return [w, s, e, n].map((v) => v.toFixed(3)).join(',');
}

/** 지도 화면의 transport 레이어 상태(ADR-076). 기능이 꺼져 있으면 `visible=false`. */
export function useMobileTransport(camera: MapCamera | null) {
  const [enabled, setEnabled] = useState<ReadonlySet<TransportLayer>>(() => new Set());
  const [settled, setSettled] = useState<MapCamera | null>(camera);

  useEffect(() => {
    const id = setTimeout(() => setSettled(camera), DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [camera]);

  const statusQuery = useQuery({
    queryKey: ['transport', 'status'],
    queryFn: () => transportApi(apiClient).status(),
    retry: false,
    staleTime: 5 * 60_000,
  });
  const visible = statusQuery.data?.enabled === true;

  const zoom = settled ? Math.round(clamp(settled.zoom, 5, 19)) : null;
  const layers = zoom == null ? [] : requestableTransportLayers(enabled, zoom);
  const bbox = settled ? cameraBbox(settled) : null;

  const markersQuery = useQuery({
    queryKey: ['transport', 'markers', bbox, zoom, layers.join(',')],
    queryFn: () =>
      transportApi(apiClient).markersInBounds({ bbox: bbox ?? '', zoom: zoom ?? 5, layers }),
    enabled: visible && bbox != null && zoom != null && layers.length > 0,
    retry: false,
    staleTime: 60_000,
  });

  const results: TransportLayerResult[] = useMemo(
    () =>
      layers.length === 0
        ? []
        : (markersQuery.data?.layers ?? []).filter((r) => enabled.has(r.layer)),
    [markersQuery.data, enabled, layers.length],
  );

  const items = useMemo(
    () => results.flatMap((r) => (r.status === 'ok' ? r.items : [])),
    [results],
  );

  const markers = useMemo(
    () =>
      items.flatMap((item) =>
        item.coord
          ? [
              {
                id: transportMarkerId(item.layer, item.feature_id),
                coordinate: [item.coord.lon, item.coord.lat] as [number, number],
                color: paletteHex(item.marker_color),
                ariaLabel: transportItemTitle(item),
              },
            ]
          : [],
      ),
    [items],
  );

  /** 마커 press id → 항목. transport 마커가 아니면(내 위치 등) null. */
  const itemForMarker = (id: string): TransportItem | null => {
    const parsed = parseTransportMarkerId(id);
    if (!parsed) return null;
    return (
      items.find((i) => i.layer === parsed.layer && i.feature_id === parsed.featureId) ?? null
    );
  };

  const toggle = (layer: TransportLayer) => {
    setEnabled((prev) => {
      const next = new Set(prev);
      if (next.has(layer)) next.delete(layer);
      else next.add(layer);
      return next;
    });
  };

  return {
    visible,
    enabled,
    zoom,
    results,
    receivedAt: markersQuery.dataUpdatedAt || null,
    markers,
    itemForMarker,
    toggle,
  };
}

export type MobileTransportState = ReturnType<typeof useMobileTransport>;

export function TransportChips({ state }: { state: MobileTransportState }) {
  if (!state.visible) return null;
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={{ gap: 8 }}
    >
      {TRANSPORT_LAYER_META.map((meta) => {
        const on = state.enabled.has(meta.layer);
        const result = state.results.find((r) => r.layer === meta.layer);
        const hint =
          on && state.zoom != null && state.zoom < meta.minZoom
            ? ' · 확대'
            : on && result && result.status !== 'ok'
              ? ' · 불가'
              : '';
        return (
          <Pressable
            key={meta.layer}
            accessibilityRole="button"
            accessibilityState={{ selected: on }}
            onPress={() => state.toggle(meta.layer)}
            className={`min-h-11 justify-center rounded-full border px-4 ${on ? 'border-primary bg-primary' : 'border-hairline bg-canvas'}`}
          >
            <Text className={`text-sm font-medium ${on ? 'text-white' : 'text-body'}`}>
              {meta.label}
              {hint}
            </Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

function pricesOf(item: TransportItem): { label: string; value: string }[] {
  if (item.layer === 'fuel_station') {
    return item.prices.map((p) => ({
      label: fuelProductLabel(p.product_key, p.product_name),
      value: formatFuelPrice(p.price),
    }));
  }
  if (item.layer === 'rest_area' && item.fuel_prices) {
    return [
      { label: '휘발유', value: formatFuelPrice(item.fuel_prices.gasoline_price) },
      { label: '경유', value: formatFuelPrice(item.fuel_prices.diesel_price) },
    ];
  }
  return [];
}

function subtitleOf(item: TransportItem): string | null {
  switch (item.layer) {
    case 'highway_incident':
      return [item.incident_type, item.process_status, item.route_name, item.point_name]
        .filter(Boolean)
        .join(' · ');
    case 'airport':
      return `${item.iata_code}${item.icao_code ? ` / ${item.icao_code}` : ''}`;
    default:
      return item.address.road ?? item.address.jibun ?? null;
  }
}

/** 마커를 누르면 하단에 뜨는 카드 — 현재가·신선도만(가격 추이는 웹에서). */
export function TransportItemCard({
  item,
  state,
  onClose,
}: {
  item: TransportItem;
  state: MobileTransportState;
  onClose: () => void;
}) {
  const result = state.results.find((r) => r.layer === item.layer);
  const freshness = result?.freshness;
  const prices = pricesOf(item);
  const subtitle = subtitleOf(item);
  return (
    <Card className="gap-1">
      <View className="flex-row items-start justify-between gap-2">
        <View className="flex-1">
          <Subheading>{transportItemTitle(item)}</Subheading>
          <Muted>{transportLayerLabel(item.layer)}</Muted>
        </View>
        <Pressable accessibilityRole="button" onPress={onClose} className="min-h-11 justify-center px-2">
          <Text className="text-sm text-muted">닫기</Text>
        </Pressable>
      </View>
      {subtitle ? <Body>{subtitle}</Body> : null}
      {prices.map((p) => (
        <View key={p.label} className="flex-row justify-between">
          <Body>{p.label}</Body>
          <Body className="font-semibold">{p.value}</Body>
        </View>
      ))}
      {freshness && state.receivedAt ? (
        <Muted>
          {transportFreshnessLabel(
            transportFreshnessAgeSeconds(freshness, state.receivedAt, state.receivedAt),
          )}
          {freshness.stale ? ' · 오래된 정보' : ''}
        </Muted>
      ) : null}
    </Card>
  );
}
