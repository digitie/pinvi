/**
 * TanStack Query key factory — invalidate 일관성 위해 단일 위치.
 * `docs/architecture/frontend.md` §4.3.
 */

export const queryKeys = {
  auth: {
    me: () => ['auth', 'me'] as const,
    providers: () => ['auth', 'oauth-providers'] as const,
  },
  health: {
    base: () => ['health'] as const,
    db: () => ['health', 'db'] as const,
  },
  trips: {
    all: () => ['trips'] as const,
    list: (params: { bucket?: string }) => ['trips', 'list', params] as const,
    detail: (tripId: string) => ['trips', 'detail', tripId] as const,
    comments: (tripId: string) => ['trips', 'comments', tripId] as const,
  },
  noticePlans: {
    all: () => ['notice-plans'] as const,
    list: (params: { category?: string; page?: number }) =>
      ['notice-plans', 'list', params] as const,
    detail: (planId: string) => ['notice-plans', 'detail', planId] as const,
  },
  features: {
    inBounds: (params: { bounds: string; zoom: number; kinds: string[] }) =>
      ['features', 'in-bounds', params] as const,
    detail: (featureId: string) => ['features', 'detail', featureId] as const,
    weather: (featureId: string) => ['features', 'weather', featureId] as const,
  },
} as const;
