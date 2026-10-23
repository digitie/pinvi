import {
  FuelPriceHistoryResponseSchema,
  TransportDetailResponseSchema,
  TransportMarkersInBoundsResponseSchema,
  TransportStatusResponseSchema,
} from '@pinvi/schemas';
import type { TransportLayer } from '@pinvi/schemas';
import type { ApiClient } from '../client';

/** layer → PinVi 상세 경로 segment(Map과 같은 복수 kebab). */
export const TRANSPORT_LAYER_PATH: Record<TransportLayer, string> = {
  fuel_station: 'fuel-stations',
  rest_area: 'rest-areas',
  highway_incident: 'highway-incidents',
  airport: 'airports',
};

/**
 * 지도 transport 레이어 — Map REST 경유(ADR-076, `docs/api/transport.md`).
 *
 * `status`·`markersInBounds`는 Map 장애에도 200이고 레이어별 `status`로 강등된다. 상세·가격 추이는
 * 404 `TRANSPORT_FEATURE_NOT_FOUND`·503 `TRANSPORT_UNAVAILABLE`/`TRANSPORT_DISABLED`를 던진다.
 */
export const transportApi = (client: ApiClient) => ({
  status: (opts?: { signal?: AbortSignal }) =>
    client.request('/transport/status', {
      method: 'GET',
      schema: TransportStatusResponseSchema,
      signal: opts?.signal,
    }),

  /** bbox format: `lng_min,lat_min,lng_max,lat_max` — `featureApi.inBounds`와 같다. */
  markersInBounds: (
    params: { bbox: string; zoom: number; layers: TransportLayer[]; limit?: number },
    opts?: { signal?: AbortSignal },
  ) => {
    const qs = new URLSearchParams();
    qs.set('bbox', params.bbox);
    qs.set('zoom', String(params.zoom));
    qs.set('layers', params.layers.join(','));
    if (params.limit) qs.set('limit', String(params.limit));
    return client.request(`/transport/markers-in-bounds?${qs.toString()}`, {
      method: 'GET',
      schema: TransportMarkersInBoundsResponseSchema,
      signal: opts?.signal,
    });
  },

  detail: (layer: TransportLayer, featureId: string, opts?: { signal?: AbortSignal }) =>
    client.request(
      `/transport/${TRANSPORT_LAYER_PATH[layer]}/${encodeURIComponent(featureId)}`,
      { method: 'GET', schema: TransportDetailResponseSchema, signal: opts?.signal },
    ),

  fuelPriceHistory: (
    featureId: string,
    params: { productKey?: string; days?: number } = {},
    opts?: { signal?: AbortSignal },
  ) => {
    const qs = new URLSearchParams();
    if (params.productKey) qs.set('product_key', params.productKey);
    if (params.days) qs.set('days', String(params.days));
    const query = qs.toString();
    const suffix = query ? `?${query}` : '';
    return client.request(
      `/transport/fuel-stations/${encodeURIComponent(featureId)}/price-history${suffix}`,
      { method: 'GET', schema: FuelPriceHistoryResponseSchema, signal: opts?.signal },
    );
  },
});
