import {
  ExternalEnrichmentSchema,
  FeatureWeatherCardSchema,
  PoiCreateSchema,
  PoiMoveRequestSchema,
  PoiMoveResponseSchema,
  PoiPlaceDetailsSchema,
  PoiReorderRequestSchema,
  PoiResponseSchema,
  PoiUpdateSchema,
} from '@pinvi/schemas';
import { z } from 'zod';
import type { ApiClient } from '../client';
import type { PoiCreate, PoiMoveRequest, PoiReorderRequest, PoiUpdate } from '@pinvi/schemas';

/** `docs/api/pois.md` 정본 POI API. */
export const poiApi = (client: ApiClient) => ({
  create: (tripId: string, body: PoiCreate) =>
    client.request(`/trips/${tripId}/pois`, {
      method: 'POST',
      body: JSON.stringify(PoiCreateSchema.parse(body)),
      schema: PoiResponseSchema,
    }),

  update: (tripId: string, poiId: string, version: number, body: PoiUpdate) =>
    client.request(`/trips/${tripId}/pois/${poiId}`, {
      method: 'PATCH',
      headers: { 'If-Match': String(version) },
      body: JSON.stringify(PoiUpdateSchema.parse(body)),
      schema: PoiResponseSchema,
    }),

  delete: (tripId: string, poiId: string) =>
    client.requestNoContent(`/trips/${tripId}/pois/${poiId}`, {
      method: 'DELETE',
    }),

  reorder: (tripId: string, body: PoiReorderRequest) =>
    client.request(`/trips/${tripId}/pois/reorder`, {
      method: 'POST',
      body: JSON.stringify(PoiReorderRequestSchema.parse(body)),
      schema: z.array(PoiResponseSchema),
    }),

  /**
   * 장소 하나를 일자 안에서, 또는 다른 일자로 옮긴다 — `before_poi_id` 바로 앞, null이면 맨 끝.
   * `version`은 옮길 장소의 version(If-Match, 다르면 409 VERSION_CONFLICT).
   */
  move: (tripId: string, poiId: string, version: number, body: PoiMoveRequest) =>
    client.request(`/trips/${tripId}/pois/${poiId}/move`, {
      method: 'POST',
      headers: { 'If-Match': String(version) },
      body: JSON.stringify(PoiMoveRequestSchema.parse(body)),
      schema: PoiMoveResponseSchema,
    }),

  /**
   * 장소 하나의 현재 날씨 + 가까운 며칠 예보 + 특보(`asof` 없는 feature weather와 같은 셰입).
   * POI snapshot 좌표로 조회하므로 지도 feature가 없는 직접 추가 장소도 날씨가 나온다.
   */
  weather: (tripId: string, poiId: string, opts?: { signal?: AbortSignal }) =>
    client.request(`/trips/${tripId}/pois/${poiId}/weather`, {
      method: 'GET',
      schema: FeatureWeatherCardSchema,
      signal: opts?.signal,
    }),

  /** 장소 영업 정보(영업시간·휴무일·전화·웹사이트). 처음 열 때 서버가 한 번 받아 저장한다. */
  placeDetails: (tripId: string, poiId: string, opts?: { signal?: AbortSignal }) =>
    client.request(`/trips/${tripId}/pois/${poiId}/place-details`, {
      method: 'GET',
      schema: PoiPlaceDetailsSchema,
      signal: opts?.signal,
    }),

  /**
   * 저장된 전화가 없을 때 표시 시점에 Kakao Local로 찾은 전화·카카오맵 링크(저장하지 않음, ADR-054).
   * 확실히 맞는 장소가 없거나 장애면 `matched=false`.
   */
  kakaoPhone: (tripId: string, poiId: string, opts?: { signal?: AbortSignal }) =>
    client.request(`/trips/${tripId}/pois/${poiId}/place-details/kakao-phone`, {
      method: 'GET',
      schema: ExternalEnrichmentSchema,
      signal: opts?.signal,
    }),

  /** "다시 읽어오기" — 저장값을 출처에서 다시 받아 덮어쓴다(같은 장소 60초에 1회, 429). */
  refreshPlaceDetails: (tripId: string, poiId: string) =>
    client.request(`/trips/${tripId}/pois/${poiId}/place-details/refresh`, {
      method: 'POST',
      schema: PoiPlaceDetailsSchema,
    }),
});
