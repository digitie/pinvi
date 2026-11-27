import { cameraBbox, clamp, type MapCamera } from '../lib/cameraBbox';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { FlatList, Pressable, Text, View } from 'react-native';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { transportApi } from '@pinvi/api-client';
import type { TransportItem, TransportLayer, TransportLayerResult } from '@pinvi/schemas';
import {
  TRANSPORT_LAYER_META,
  formatFuelPrice,
  fuelBrand,
  fuelStationFacilities,
  fuelStationPriceRows,
  paletteHex,
  parseTransportMarkerId,
  requestableTransportLayers,
  transportFreshnessAgeSeconds,
  transportFreshnessLabel,
  transportItemTitle,
  transportLayerLabel,
  transportMarkerId,
  restAreaFuelPriceRows,
  type FuelPriceRow,
} from '@pinvi/domain';
import { apiClient } from '../lib/api';
import { Body, Card, Muted, Subheading } from './ui';

const DEBOUNCE_MS = 400;
/** 클러스터링이 없는 네이티브 마커라 레이어당 상한을 낮게 둔다. */
const LIMIT = 100;

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
    queryFn: ({ signal }) =>
      transportApi(apiClient).markersInBounds(
        { bbox: bbox ?? '', zoom: zoom ?? 5, layers, limit: LIMIT },
        { signal },
      ),
    enabled: visible && bbox != null && zoom != null && layers.length > 0,
    // 지도를 옮기는 동안 지난 마커를 유지한다(응답 전 깜빡임 방지).
    placeholderData: keepPreviousData,
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

  /** 마커 press id → 항목. transport 마커가 아니면(내 위치 등)·지금 결과에 없으면 null. */
  const itemForMarker = (id: string): TransportItem | null => {
    const parsed = parseTransportMarkerId(id);
    if (!parsed) return null;
    return items.find((i) => i.layer === parsed.layer && i.feature_id === parsed.featureId) ?? null;
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

type LayerMeta = (typeof TRANSPORT_LAYER_META)[number];
const layerKey = (meta: LayerMeta) => meta.layer;
export function TransportChips({ state }: { state: MobileTransportState }) {
  const renderItem = useCallback(
    ({ item }: { item: LayerMeta }) => <TransportChip meta={item} state={state} />,
    [state],
  );
  if (!state.visible) return null;
  return (
    <FlatList
      data={TRANSPORT_LAYER_META}
      keyExtractor={layerKey}
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={{ gap: 8 }}
      renderItem={renderItem}
    />
  );
}

/**
 * 카드의 주유소 정보 — 웹 교통 상세와 같은 규칙(`@pinvi/domain` fuelStation): 판매 중인 유종만, `1,689원/L`,
 * 7일 넘은 값은 "오래됨", 상표 이름, 편의시설.
 */
function fuelInfoOf(
  item: TransportItem,
  nowMs: number,
): { brand: string | null; rows: FuelPriceRow[]; facilities: string[] } {
  if (item.layer === 'fuel_station') {
    return {
      brand: fuelBrand(item.brand_code, item.brand_name)?.name ?? null,
      rows: fuelStationPriceRows(item.prices, nowMs),
      facilities: fuelStationFacilities(item),
    };
  }
  if (item.layer === 'rest_area' && item.fuel_prices) {
    return {
      brand: fuelBrand(null, item.fuel_prices.oil_company)?.name ?? null,
      rows: restAreaFuelPriceRows(item.fuel_prices, nowMs),
      facilities: [],
    };
  }
  return { brand: null, rows: [], facilities: [] };
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

/** 마커를 누르면 하단에 뜨는 카드 — 현재가·신선도만(가격 추이는 웹에서). 탐색 지도·여행 지도 공용. */
export function TransportItemCard({
  item,
  state,
  onClose,
}: {
  item: TransportItem;
  state: { results: readonly TransportLayerResult[]; receivedAt: number | null };
  onClose: () => void;
}) {
  const result = state.results.find((r) => r.layer === item.layer);
  const freshness = result?.freshness;
  // 카드를 연 시각 — react-query 캐시에서 꺼낸 결과도 받은 뒤 흐른 시간을 더해 센다.
  const [openedAt] = useState(() => Date.now());
  const fuel = fuelInfoOf(item, openedAt);
  const subtitle = subtitleOf(item);
  return (
    <Card className="gap-1">
      <View className="flex-row items-start justify-between gap-2">
        <View className="flex-1">
          <Subheading>{transportItemTitle(item)}</Subheading>
          <Muted>{transportLayerLabel(item.layer)}</Muted>
        </View>
        <Pressable
          accessibilityRole="button"
          onPress={onClose}
          className="min-h-11 justify-center px-2"
        >
          <Text className="text-sm text-muted">닫기</Text>
        </Pressable>
      </View>
      {subtitle ? <Body>{subtitle}</Body> : null}
      {/* 굵기는 weight가 아니라 정적 글꼴 family로(Body의 font-pinvi-regular 위에 weight만 얹으면 기기에서 굵지 않다). */}
      {fuel.brand ? (
        <Text className="text-sm font-pinvi-semibold text-ink">{fuel.brand}</Text>
      ) : null}
      {fuel.rows.map((row) => (
        <View
          key={row.key}
          className="flex-row items-center justify-between gap-2 border-b border-hairline py-1"
          testID={`transport-fuel-price-${row.key}`}
          accessible
          accessibilityLabel={`${row.label} ${formatFuelPrice(row.price)}${row.old ? ', 오래됨' : ''}`}
        >
          <Body>{row.label}</Body>
          <View className="flex-row items-center gap-2">
            {row.old ? (
              // iOS Text는 배경을 둥글게 자르지 않는다 — View가 모양을 갖는다.
              <View className="overflow-hidden rounded-full bg-warning-bg px-2 py-0.5">
                <Text className="text-xs font-pinvi-semibold text-warning-text">오래됨</Text>
              </View>
            ) : null}
            <Text className="text-sm font-pinvi-bold text-ink">{formatFuelPrice(row.price)}</Text>
          </View>
        </View>
      ))}
      {item.layer === 'fuel_station' && fuel.rows.length === 0 ? (
        <Muted>등록된 유효 유가가 없습니다.</Muted>
      ) : null}
      {fuel.facilities.length > 0 ? <Muted>편의시설 · {fuel.facilities.join(' · ')}</Muted> : null}
      {freshness && state.receivedAt ? (
        <Muted>
          {transportFreshnessLabel(
            transportFreshnessAgeSeconds(freshness, state.receivedAt, openedAt),
          )}
          {freshness.stale ? ' · 오래된 정보' : ''}
        </Muted>
      ) : null}
    </Card>
  );
}

function TransportChip({ meta, state }: { meta: LayerMeta; state: MobileTransportState }) {
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
}
