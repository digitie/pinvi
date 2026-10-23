/**
 * 지도 transport 레이어 공용 로직 (ADR-076) — 웹·모바일이 같은 규칙을 쓴다.
 *
 * - 레이어별 최소 줌: 저배율에서 전국 주유소 1.2만 곳이 상한에 잘려 보이는 것을 피한다.
 * - 신선도: 기기 시계와 타임스탬프 차가 아니라 **Map `age_seconds` + 응답을 받은 뒤 흐른 시간**으로
 *   센다(기기 시계가 틀려도, viewport 캐시를 거쳐도 맞는다). 오래됨 판정은 Map `stale`만 쓴다.
 * - 마커 id: `transport:<layer>:<feature_id>` — feature 마커 id와 섞이지 않게 접두로 가른다(ADR-076 D7).
 */

import type {
  HighwayIncidentItem,
  TransportFreshness,
  TransportItem,
  TransportLayer,
} from '@pinvi/schemas';

export interface TransportLayerMeta {
  layer: TransportLayer;
  label: string;
  /** 이 줌 미만에서는 요청하지 않는다. */
  minZoom: number;
}

/** 표시 순서 = 이 배열 순서. */
export const TRANSPORT_LAYER_META: readonly TransportLayerMeta[] = [
  { layer: 'fuel_station', label: '주유소', minZoom: 11 },
  { layer: 'rest_area', label: '휴게소', minZoom: 8 },
  { layer: 'highway_incident', label: '교통 돌발', minZoom: 7 },
  { layer: 'airport', label: '공항', minZoom: 5 },
];

const META_BY_LAYER = new Map(TRANSPORT_LAYER_META.map((meta) => [meta.layer, meta]));

export function transportLayerLabel(layer: TransportLayer): string {
  return META_BY_LAYER.get(layer)?.label ?? layer;
}

export function transportLayerMinZoom(layer: TransportLayer): number {
  return META_BY_LAYER.get(layer)?.minZoom ?? 0;
}

/** 켜 둔 레이어 중 이 줌에서 요청할 레이어(표시 순서 유지). */
export function requestableTransportLayers(
  enabled: ReadonlySet<TransportLayer>,
  zoom: number,
): TransportLayer[] {
  return TRANSPORT_LAYER_META.filter(
    (meta) => enabled.has(meta.layer) && zoom >= meta.minZoom,
  ).map((meta) => meta.layer);
}

/** 응답을 받은 시각(`receivedAtMs`)과 지금(`nowMs`)으로 센 데이터 나이(초, 0 이상). */
export function transportFreshnessAgeSeconds(
  freshness: Pick<TransportFreshness, 'age_seconds'>,
  receivedAtMs: number,
  nowMs: number,
): number {
  const elapsed = Math.max(0, (nowMs - receivedAtMs) / 1000);
  return Math.max(0, Math.floor(freshness.age_seconds + elapsed));
}

/** "방금 갱신" / "n분 전 갱신" / "n시간 전 갱신" / "n일 전 갱신". */
export function transportFreshnessLabel(ageSeconds: number): string {
  const age = Math.max(0, Math.floor(ageSeconds));
  if (age < 60) return '방금 갱신';
  const minutes = Math.floor(age / 60);
  if (minutes < 60) return `${minutes}분 전 갱신`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}시간 전 갱신`;
  return `${Math.floor(hours / 24)}일 전 갱신`;
}

const FUEL_PRODUCT_LABEL: Record<string, string> = {
  gasoline: '휘발유',
  premium_gasoline: '고급휘발유',
  diesel: '경유',
  kerosene: '등유',
  lpg: 'LPG',
};

/** 유종 이름. Map이 준 이름을 우선하고, 없으면 표준 키로, 그것도 모르면 키 그대로. */
export function fuelProductLabel(productKey: string, productName?: string | null): string {
  const name = productName?.trim();
  if (name) return name;
  return FUEL_PRODUCT_LABEL[productKey] ?? productKey;
}

/** 원/L 가격. `null`은 지금 판매하지 않는다는 뜻이다. */
export function formatFuelPrice(price: number | null | undefined): string {
  if (price == null || !Number.isFinite(price)) return '판매 안 함';
  return `${Math.round(price).toLocaleString('ko-KR')}원`;
}

const MARKER_PREFIX = 'transport:';

export function transportMarkerId(layer: TransportLayer, featureId: string): string {
  return `${MARKER_PREFIX}${layer}:${featureId}`;
}

const LAYERS: ReadonlySet<string> = new Set(TRANSPORT_LAYER_META.map((meta) => meta.layer));

/** `transportMarkerId`의 역. transport 마커가 아니면 `null`. */
export function parseTransportMarkerId(
  id: string,
): { layer: TransportLayer; featureId: string } | null {
  if (!id.startsWith(MARKER_PREFIX)) return null;
  const rest = id.slice(MARKER_PREFIX.length);
  const sep = rest.indexOf(':');
  if (sep <= 0) return null;
  const layer = rest.slice(0, sep);
  const featureId = rest.slice(sep + 1);
  if (!LAYERS.has(layer) || featureId.length === 0) return null;
  return { layer: layer as TransportLayer, featureId };
}

/** 항목의 표시 이름(돌발은 `title`). */
export function transportItemTitle(item: TransportItem): string {
  return item.layer === 'highway_incident' ? item.title : item.name;
}

/** 돌발 목록 — 발생 시각 내림차순, 시각 없는 항목은 뒤. */
export function sortIncidentsByRecency(items: readonly HighwayIncidentItem[]): HighwayIncidentItem[] {
  const time = (item: HighwayIncidentItem): number | null => {
    const parsed = item.occurred_at ? Date.parse(item.occurred_at) : Number.NaN;
    return Number.isFinite(parsed) ? parsed : null;
  };
  return [...items].sort((a, b) => {
    const ta = time(a);
    const tb = time(b);
    if (ta === tb) return 0;
    if (ta === null) return 1;
    if (tb === null) return -1;
    return tb - ta;
  });
}
