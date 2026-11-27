/**
 * 지도 transport 레이어 공용 로직 (ADR-076) — 웹·모바일이 같은 규칙을 쓴다.
 *
 * - 레이어별 최소 줌: 저배율에서 전국 주유소 1.2만 곳이 상한에 잘려 보이는 것을 피한다.
 * - 신선도: 기기 시계와 타임스탬프 차가 아니라 **Map `age_seconds` + 응답을 받은 뒤 흐른 시간**으로
 *   센다(기기 시계가 틀려도, viewport 캐시를 거쳐도 맞는다). 오래됨 판정은 Map `stale`만 쓴다.
 * - 마커 id: `transport:<layer>:<feature_id>` — feature 마커 id와 섞이지 않게 접두로 가른다(ADR-076 D7).
 */

import { TransportLayerSchema } from '@pinvi/schemas';
import type {
  HighwayIncidentItem,
  TransportFreshness,
  TransportItem,
  TransportLayer,
  TransportLayerResult,
  TransportLayerStatus,
} from '@pinvi/schemas';

export interface TransportLayerMeta {
  layer: TransportLayer;
  label: string;
  /** 이 줌 미만에서는 요청하지 않는다. */
  minZoom: number;
}

/**
 * 지도에 켤 수 있는 레이어. 표시 순서 = 이 배열 순서.
 *
 * 휴게소·공항은 지도에서 뺐다(소유자 결정 2026-11-16) — API 계약(`TransportLayer`)에는 남아 있지만 화면은
 * 켜지 않는다. 여행 지도는 여행 장소 반경(주유소 10 km·교통 돌발 20 km, `/transport/markers-near`)만 보인다.
 */
export const TRANSPORT_LAYER_META: readonly TransportLayerMeta[] = [
  { layer: 'fuel_station', label: '주유소', minZoom: 11 },
  { layer: 'highway_incident', label: '교통 돌발', minZoom: 7 },
];

/** 여행 지도 반경 문구 — 서버가 알려 준 반경(m)을 "여행 장소 10km 이내"로. */
export function transportRadiusLabel(radiusM: number): string {
  const km = radiusM / 1000;
  return `여행 장소 ${Number.isInteger(km) ? km : km.toFixed(1)}km 이내`;
}

/** 반경 조회 기준 장소 상한 — 서버 `NEAR_MAX_POINTS`와 같다(넘으면 400). */
export const TRANSPORT_NEAR_MAX_POINTS = 60;

/** 반경 조회 좌표 키 — 5자리(≈1 m, `markersNear` 쿼리와 같은 정밀도). 배열 identity가 아니라 값으로 비교한다. */
export function transportNearPointsKey(points: ReadonlyArray<{ lon: number; lat: number }>): string {
  return points.map((p) => `${p.lon.toFixed(5)},${p.lat.toFixed(5)}`).join(';');
}

/** 여행 장소 좌표 → 반경 조회 기준점. 5자리로 같은 곳은 처음 것만 남긴다(순서 유지). */
export function dedupeTransportNearPoints(
  points: ReadonlyArray<{ lon: number; lat: number }>,
): { lon: number; lat: number }[] {
  const seen = new Set<string>();
  return points.flatMap((p) => {
    const key = transportNearPointsKey([p]);
    if (seen.has(key)) return [];
    seen.add(key);
    return [{ lon: p.lon, lat: p.lat }];
  });
}

/** 요청한 레이어 하나의 "불러올 수 없음" 결과(응답에 빠졌거나 요청 자체가 실패). */
export function unavailableTransportLayerResult(layer: TransportLayer): TransportLayerResult {
  return { layer, status: 'unavailable', reason: 'UPSTREAM_UNAVAILABLE', truncated: false, items: [] };
}

/**
 * 응답 결과 + 요청했는데 응답에 없는 레이어를 "불러올 수 없음"으로 채운다 — 화면이 "불러오는 중"에 머물지 않게.
 * 요청 자체가 실패했으면 `results`를 빈 배열로 넘긴다.
 */
export function withUnavailableTransportLayers(
  results: readonly TransportLayerResult[],
  requested: readonly TransportLayer[],
): TransportLayerResult[] {
  const returned = new Set(results.map((result) => result.layer));
  return [
    ...results,
    ...requested.filter((layer) => !returned.has(layer)).map(unavailableTransportLayerResult),
  ];
}

/** 켠 레이어의 상태 줄 입력(웹 레이어 패널·모바일 여행 지도 공용). */
export interface TransportLayerStatusInput {
  meta: Pick<TransportLayerMeta, 'layer' | 'minZoom'>;
  /** `/transport/status`의 이 레이어 항목(없으면 모름). */
  layerStatus: Pick<TransportLayerStatus, 'available'> | null | undefined;
  /** 이 레이어의 지금 결과(아직 없으면 undefined). */
  result: TransportLayerResult | undefined;
  /** 여행 장소 반경 모드 — 줌 안내 없음, 반경 문구. */
  nearMode: boolean;
  zoom: number | null;
  /** 결과가 오기 전 "불러오는 중"을 보일지(조회가 실제로 나갈 수 있는 상태인지). */
  loading: boolean;
  /** 반경 모드에서 서버가 알려 준 레이어별 반경(m). */
  radiusM: Partial<Record<TransportLayer, number>> | null;
  receivedAt: number | null;
  nowMs: number;
}

/** 켠 레이어의 결과가 아직 없을 때의 상태 줄. */
export const TRANSPORT_STATUS_LOADING_TEXT = '불러오는 중';

/** "N곳 · 여행 장소 10km 이내 · 5분 전 갱신" 같은 상태 줄. 보일 것이 없으면 null. */
export function transportLayerStatusText(input: TransportLayerStatusInput): string | null {
  const { meta, layerStatus, result } = input;
  if (layerStatus && !layerStatus.available) return '일시적으로 불러올 수 없음';
  // 여행 장소 반경 모드는 줌과 무관하게 조회한다.
  if (!input.nearMode && input.zoom != null && input.zoom < meta.minZoom) return '확대하면 보여요';
  if (!result) return input.loading ? TRANSPORT_STATUS_LOADING_TEXT : null;
  if (result.status !== 'ok') return '일시적으로 불러올 수 없음';
  const parts: string[] = [`${result.items.length}곳`];
  const radius = input.nearMode ? input.radiusM?.[meta.layer] : undefined;
  if (radius != null) parts.push(transportRadiusLabel(radius));
  if (result.truncated) parts.push(input.nearMode ? '가까운 곳만 표시' : '일부만 표시 — 확대하세요');
  if (result.freshness && input.receivedAt != null) {
    parts.push(
      transportFreshnessLabel(
        transportFreshnessAgeSeconds(result.freshness, input.receivedAt, input.nowMs),
      ),
    );
    if (result.freshness.stale) parts.push('오래된 정보');
  }
  return parts.join(' · ');
}

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

// 유종 이름·가격 문구·판매 판정은 `fuelStation.ts`가 소유한다(transport 공개 유가 화면 기준).

const MARKER_PREFIX = 'transport:';

export function transportMarkerId(layer: TransportLayer, featureId: string): string {
  return `${MARKER_PREFIX}${layer}:${featureId}`;
}

// 화면에서 뺀 레이어(휴게소·공항)의 id도 계약상 유효하다 — 메타가 아니라 계약 목록으로 판별한다.
const LAYERS: ReadonlySet<string> = new Set<string>(TransportLayerSchema.options);

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
