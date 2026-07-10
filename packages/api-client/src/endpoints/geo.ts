import { GeoCandidateListSchema } from '@pinvi/schemas';
import type { ApiClient } from '../client';

/** `docs/integrations/kor-travel-geo.md` — kor-travel-geo v2 proxy API. */
export const geoApi = (client: ApiClient) => ({
  reverse: (
    params: {
      lon: number;
      lat: number;
      radiusM?: number;
    },
    opts?: { signal?: AbortSignal },
  ) => {
    const qs = new URLSearchParams();
    qs.set('lon', String(params.lon));
    qs.set('lat', String(params.lat));
    if (params.radiusM != null) qs.set('radius_m', String(params.radiusM));
    return client.request(`/geo/reverse?${qs.toString()}`, {
      method: 'GET',
      schema: GeoCandidateListSchema,
      signal: opts?.signal,
    });
  },
});
