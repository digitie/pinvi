import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { FlatList, Pressable, Text, View } from 'react-native';
import type { TransportItem, TripWeatherCard } from '@pinvi/schemas';
import { useMinuteNow } from '@pinvi/hooks';
import {
  TRANSPORT_LAYER_META,
  placeCurrentWeather,
  pointsBounds,
  transportLayerStatusText,
  transportMarkerId,
  type TripMapPoint,
  type WeatherConditionKind,
} from '@pinvi/domain';
import { fitCameraToPoints, type CameraPadding, type CameraTarget } from '../lib/tripMapCamera';
import type { TripTransportState } from '../lib/useTripTransport';
import { usePoiWeatherPeekAll } from '../lib/poiWeather';
import { useVWorldToken } from '../lib/vworldToken';
import { TransportItemCard } from './TransportLayers';
import { Button, Muted } from './ui';
import { VWorldMapView, type VWorldMapHandle } from './VWorldMap';
import type { PlatformMarkerItem } from './VWorldMap.types';

/** 여행 장소가 없을 때의 시점 — 전국(웹 여행 지도와 같다). */
const KOREA_VIEW: CameraTarget = { center: [127.5, 36.5], zoom: 6 };
/** 목록에서 장소를 눌렀을 때 최소 줌. 이미 더 확대해 두었으면 그 줌을 유지한다. */
const FOCUS_ZOOM = 14;
/** 모두 담기의 최대 줌 — 장소가 한 곳이거나 몇 m 거리면 `fitBounds`가 최대로 확대하지 않게 한다. */
const FIT_MAX_ZOOM = 16;
const POI_MARKER_PREFIX = 'poi:';

function tripPoiMarkerId(poiId: string): string {
  return `${POI_MARKER_PREFIX}${poiId}`;
}

/**
 * 맞춤 여백(dp). 이름 라벨이 원 아래로 붙고 좌우로 퍼지므로 옆·아래를 넉넉히, 교통 칩 줄이 지도 위를 덮으면
 * 위를 더 비운다.
 */
function fitPadding(chips: boolean): CameraPadding {
  return { top: chips ? 72 : 32, right: 56, bottom: 40, left: 56 };
}

/**
 * 뜬 지도를 모든 장소에 다시 맞춘다 — `fitBounds({ paddingPx })`. 장소가 한 곳뿐이거나 범위가 좁아 최대 줌에
 * 닿으면 계산한 중심·줌으로 옮긴다(`fitBounds`에는 최대 줌 옵션이 없다).
 */
function fitMapToPoints(
  map: VWorldMapHandle | null,
  points: TripMapPoint[],
  size: { width: number; height: number },
  padding: CameraPadding,
): void {
  const bounds = pointsBounds(points);
  const target = fitCameraToPoints(points, size, padding, { maxZoom: FIT_MAX_ZOOM });
  if (!map || !bounds || !target) return;
  const single = bounds.west === bounds.east && bounds.south === bounds.north;
  if (single || target.zoom >= FIT_MAX_ZOOM) {
    map.flyTo(target);
    return;
  }
  map.fitBounds(
    { sw: [bounds.west, bounds.south], ne: [bounds.east, bounds.north] },
    { paddingPx: padding },
  );
}

export interface TripMapFocus {
  poiId: string;
  /** 같은 장소를 다시 눌러도(그 사이 지도를 옮겼어도) 다시 가운데로 가져오도록 누를 때마다 늘린다. */
  seq: number;
}

export interface TripMapPanelProps {
  points: TripMapPoint[];
  selectedPoiId: string | null;
  focus: TripMapFocus | null;
  onSelectPoi: (poiId: string) => void;
  transport: TripTransportState;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  width: number;
  height: number;
  /**
   * 마커 이름 옆 현재 날씨의 출처 — 장소별 현재 카드 공유 캐시의 키(`tripId`, 목록 배지가 받은 카드를 요청 없이
   * 읽는다)와 여행 화면이 이미 받은 일자 카드(`placeWeatherCards`). 둘 다 없으면 날씨 아이콘이 없다.
   */
  tripId?: string | null;
  dayWeatherCards?: Readonly<Record<string, TripWeatherCard>>;
}

/**
 * 여행 상세 위쪽 지도 — 여행 장소(일자·마커 색 원 + 이름), 여행 장소 반경 교통 레이어(주유소·교통 돌발).
 *
 * 네이티브는 `vworld-map-rn`(MapLibre Native), Expo Web은 같은 계약의 웹 어댑터다(`VWorldMap`).
 * 접으면 지도를 내리고(unmount) 펼침 막대만 남긴다 — 목록을 넓게 쓸 수 있다.
 */
export function TripMapPanel(props: TripMapPanelProps) {
  const { collapsed, onToggleCollapsed, transport, points, width, height } = props;
  const mapRef = useRef<VWorldMapHandle>(null);
  // 모든 장소를 다시 담는다(지도 아래 막대 — 지도 위에 두면 출처 표기와 겹친다).
  const fitAll = () =>
    fitMapToPoints(mapRef.current, points, { width, height }, fitPadding(transport.visible));
  return (
    <View className="border-b border-hairline bg-canvas" testID="trip-map-panel">
      {collapsed ? null : <TripMapCanvas {...props} mapRef={mapRef} />}
      {collapsed ? null : <TripTransportStatus transport={transport} />}
      <View className="flex-row items-center justify-end gap-1 px-4">
        {!collapsed && points.length > 1 ? (
          <Pressable
            accessibilityRole="button"
            onPress={fitAll}
            className="min-h-11 justify-center px-2"
          >
            <Text className="text-sm font-medium text-ink">전체 보기</Text>
          </Pressable>
        ) : null}
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ expanded: !collapsed }}
          onPress={onToggleCollapsed}
          className="min-h-11 justify-center px-2"
        >
          <Text className="text-sm font-medium text-primary">
            {collapsed ? '지도 펼치기' : '지도 접기'}
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

function TripMapCanvas({
  points,
  selectedPoiId,
  focus,
  onSelectPoi,
  transport,
  width,
  height,
  mapRef,
  tripId = null,
  dayWeatherCards,
}: TripMapPanelProps & { mapRef: RefObject<VWorldMapHandle | null> }) {
  const tokenQuery = useVWorldToken();
  const lastZoomRef = useRef<number | null>(null);
  const padding = fitPadding(transport.visible);
  const size = { width, height };

  // 첫 시점 — `initialCenter`/`initialZoom`은 mount 때 한 번만 읽힌다. 펼치며 장소를 골랐으면 그 장소,
  // 아니면 모든 장소를 담는다.
  const [initial] = useState<CameraTarget>(() => {
    const focused = focus ? points.find((p) => p.poiId === focus.poiId) : undefined;
    if (focused) return { center: [focused.lon, focused.lat], zoom: FOCUS_ZOOM };
    return fitCameraToPoints(points, size, padding, { maxZoom: FIT_MAX_ZOOM }) ?? KOREA_VIEW;
  });

  // 목록에서 장소를 고르면 그 장소를 가운데로. mount 때의 요청은 첫 시점이 이미 반영했다.
  const handledFocusRef = useRef(focus?.seq ?? 0);
  useEffect(() => {
    if (!focus || focus.seq === handledFocusRef.current) return;
    handledFocusRef.current = focus.seq;
    const point = points.find((p) => p.poiId === focus.poiId);
    if (!point) return;
    mapRef.current?.flyTo({
      center: [point.lon, point.lat],
      zoom: Math.max(lastZoomRef.current ?? 0, FOCUS_ZOOM),
    });
  }, [focus, points, mapRef]);

  // 장소가 바뀌면(편집 뒤 돌아옴 등) 다시 모두 담는다. 같은 값이면 지도를 건드리지 않는다.
  const pointsKey = points.map((p) => `${p.poiId}@${p.lon},${p.lat}`).join(';');
  const fittedKeyRef = useRef(pointsKey);
  useEffect(() => {
    if (fittedKeyRef.current === pointsKey) return;
    fittedKeyRef.current = pointsKey;
    fitMapToPoints(mapRef.current, points, { width, height }, fitPadding(transport.visible));
  }, [pointsKey, points, width, height, transport.visible, mapRef]);

  // 선택은 id로 들고 항목은 지금 결과에서 다시 찾는다 — 레이어를 끄거나 결과에서 빠지면 카드도 닫힌다.
  const [selectedTransportId, setSelectedTransportId] = useState<string | null>(null);
  const selectedTransport: TransportItem | null =
    selectedTransportId != null ? transport.itemForMarker(selectedTransportId) : null;

  // 마커 이름 옆 현재 날씨 — 새 요청 없이 이미 받은 카드에서(웹 `usePlaceWeather`와 같은 판정). 모르면 null.
  const peekWeather = usePoiWeatherPeekAll();
  const now = useMinuteNow();
  const weatherByPoi = useMemo(() => {
    const result = new Map<string, { condition: WeatherConditionKind; night: boolean }>();
    if (now === 0) return result;
    for (const p of points) {
      const weather = placeCurrentWeather(
        tripId ? peekWeather(tripId, p.poiId) : null,
        dayWeatherCards?.[p.poiId] ?? null,
        now,
      );
      if (weather) result.set(p.poiId, { condition: weather.condition, night: weather.night });
    }
    return result;
  }, [points, tripId, peekWeather, dayWeatherCards, now]);

  const markers = useMemo<PlatformMarkerItem[]>(
    () => [
      ...transport.markers.map((m) => ({
        ...m,
        // 교통 항목은 여행 장소보다 작은 원(이름 없음) — 누르면 카드.
        compact: true,
        zIndex: 1,
        selected:
          selectedTransport != null &&
          m.id === transportMarkerId(selectedTransport.layer, selectedTransport.feature_id),
      })),
      ...points.map((p) => {
        const selected = p.poiId === selectedPoiId;
        return {
          id: tripPoiMarkerId(p.poiId),
          coordinate: [p.lon, p.lat] as [number, number],
          color: p.color,
          label: p.title,
          icon: p.icon,
          weather: weatherByPoi.get(p.poiId) ?? null,
          ariaLabel: p.title,
          selected,
          // 여행 장소가 교통 마커 위, 고른 장소가 맨 위.
          zIndex: selected ? 3 : 2,
        };
      }),
    ],
    [transport.markers, points, selectedPoiId, selectedTransport, weatherByPoi],
  );

  if (tokenQuery.isError || (tokenQuery.isSuccess && !tokenQuery.data.api_key)) {
    return (
      <View style={{ height }} className="items-center justify-center gap-2 bg-surface-soft px-6">
        <Muted>지도를 불러올 수 없습니다. 아래 일정은 그대로 볼 수 있습니다.</Muted>
        <Button label="다시 시도" variant="secondary" onPress={() => tokenQuery.refetch()} />
      </View>
    );
  }

  return (
    <View style={{ height }} testID="trip-map">
      {tokenQuery.isSuccess ? (
        <VWorldMapView
          ref={mapRef}
          apiKey={tokenQuery.data.api_key}
          mapType="base"
          initialCenter={initial.center}
          initialZoom={initial.zoom}
          markers={markers}
          onCameraChanged={(camera) => {
            lastZoomRef.current = camera.zoom;
          }}
          onFeaturePress={(marker) => {
            const id = (marker as { id?: unknown }).id;
            if (typeof id !== 'string') return;
            if (id.startsWith(POI_MARKER_PREFIX)) {
              setSelectedTransportId(null);
              onSelectPoi(id.slice(POI_MARKER_PREFIX.length));
              return;
            }
            setSelectedTransportId(transport.itemForMarker(id) ? id : null);
          }}
          style={{ flex: 1 }}
        />
      ) : (
        <View className="flex-1 items-center justify-center">
          <Muted>지도 키 발급 중…</Muted>
        </View>
      )}

      {transport.visible ? (
        <View className="absolute left-3 right-3 top-3">
          <TripTransportChips transport={transport} />
        </View>
      ) : null}

      <View
        className="absolute bottom-3 left-3 right-3 gap-2"
        style={{ pointerEvents: 'box-none' }}
      >
        {points.length === 0 ? (
          <View className="self-start rounded-md bg-canvas px-3 py-2">
            <Muted>지도에 표시할 장소가 없습니다.</Muted>
          </View>
        ) : null}
        {selectedTransport ? (
          <TransportItemCard
            item={selectedTransport}
            state={transport}
            key={selectedTransportId ?? ''}
            onClose={() => setSelectedTransportId(null)}
          />
        ) : null}
      </View>
    </View>
  );
}

type LayerMeta = (typeof TRANSPORT_LAYER_META)[number];
const layerKey = (meta: LayerMeta) => meta.layer;

/** 여행 장소 반경 교통 칩(주유소·교통 돌발). 기능이 꺼져 있으면 아무것도 그리지 않는다. */
export function TripTransportChips({ transport }: { transport: TripTransportState }) {
  const { enabled, toggle } = transport;
  const renderItem = useCallback(
    ({ item }: { item: LayerMeta }) => {
      const on = enabled.has(item.layer);
      return (
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ selected: on }}
          onPress={() => toggle(item.layer)}
          className={`min-h-11 justify-center rounded-full border px-4 ${on ? 'border-primary bg-primary' : 'border-hairline bg-canvas'}`}
        >
          <Text className={`text-sm font-medium ${on ? 'text-white' : 'text-body'}`}>
            {item.label}
          </Text>
        </Pressable>
      );
    },
    [enabled, toggle],
  );
  if (!transport.visible) return null;
  return (
    <FlatList
      data={TRANSPORT_LAYER_META}
      keyExtractor={layerKey}
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={{ gap: 8 }}
      renderItem={renderItem}
      extraData={enabled}
    />
  );
}

/** 켠 레이어의 상태 줄 — "주유소 · 12곳 · 여행 장소 10km 이내 · 5분 전 갱신"(웹 레이어 패널과 같은 문구). */
export function TripTransportStatus({ transport }: { transport: TripTransportState }) {
  if (!transport.visible) return null;
  const lines = TRANSPORT_LAYER_META.filter((meta) => transport.enabled.has(meta.layer)).flatMap(
    (meta) => {
      const text = transportLayerStatusText({
        meta,
        layerStatus: transport.status?.layers.find((s) => s.layer === meta.layer),
        result: transport.results.find((r) => r.layer === meta.layer),
        nearMode: true,
        zoom: null,
        loading: transport.loading,
        radiusM: transport.radiusM,
        receivedAt: transport.receivedAt,
        nowMs: transport.nowMs,
      });
      return text ? [{ layer: meta.layer, text: `${meta.label} · ${text}` }] : [];
    },
  );
  if (lines.length === 0) return null;
  return (
    <View testID="trip-transport-status" className="px-4 pt-1.5">
      {lines.map((line) => (
        <Muted key={line.layer}>{line.text}</Muted>
      ))}
    </View>
  );
}
