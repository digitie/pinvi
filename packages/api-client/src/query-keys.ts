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
  public: {
    beaches: (params: { sido_code?: string; sigungu_code?: string; q?: string; cursor?: string }) =>
      ['public', 'beaches', params] as const,
    beach: (featureId: string) => ['public', 'beach', featureId] as const,
    beachMarkers: (params: { bbox?: string; sido_code?: string; sigungu_code?: string }) =>
      ['public', 'beach-markers', params] as const,
    festivalsMonthly: (params: { year?: number; month?: number; cursor?: string }) =>
      ['public', 'festivals-monthly', params] as const,
    festival: (featureId: string) => ['public', 'festival', featureId] as const,
    festivalMarkers: (params: { year?: number; month?: number; bbox?: string }) =>
      ['public', 'festival-markers', params] as const,
  },
  admin: {
    all: () => ['admin'] as const,
    me: () => ['admin', 'me'] as const,
    stats: () => ['admin', 'stats', 'overview'] as const,
    etlSummary: () => ['admin', 'etl', 'summary'] as const,
    providerSync: (params: { key?: string }) => ['admin', 'provider-sync', params] as const,
    providerSyncAll: () => ['admin', 'provider-sync'] as const,
    providerImportJobs: (params: {
      status?: string;
      kind?: string;
      loadBatchId?: string;
      parentJobId?: string;
      pageSize?: number;
      cursor?: string;
    }) => ['admin', 'provider-import-jobs', params] as const,
    providerImportJobsAll: () => ['admin', 'provider-import-jobs'] as const,
    dedupReviews: (params: {
      q?: string;
      status?: string[];
      provider?: string[];
      datasetKey?: string[];
      kind?: string[];
      category?: string[];
      minScore?: number;
      maxScore?: number;
      pageSize?: number;
      cursor?: string;
    }) => ['admin', 'dedup-reviews', params] as const,
    dedupReviewsAll: () => ['admin', 'dedup-reviews'] as const,
    categoryMappings: (params: { q?: string; includeCounts?: boolean; activeOnly?: boolean }) =>
      ['admin', 'category-mappings', params] as const,
    integrityIssues: (params: {
      source?: string;
      status?: string;
      severity?: string;
      violationType?: string;
      provider?: string;
      datasetKey?: string;
      featureId?: string;
      pageSize?: number;
      cursor?: string;
    }) => ['admin', 'integrity-issues', params] as const,
    integrityIssuesAll: () => ['admin', 'integrity-issues'] as const,
    securityIncidents: (params: {
      status?: string;
      severity?: string;
      overdue?: string;
      pageSize?: number;
    }) => ['admin', 'security-incidents', params] as const,
    securityIncidentsAll: () => ['admin', 'security-incidents'] as const,
    dsrRequests: (params: {
      status?: string;
      requestType?: string;
      overdue?: boolean;
      pageSize?: number;
    }) => ['admin', 'dsr-requests', params] as const,
    dsrRequestsAll: () => ['admin', 'dsr-requests'] as const,
    contentReports: (params: { status?: string; targetType?: string; pageSize?: number }) =>
      ['admin', 'content-reports', params] as const,
    contentReportsAll: () => ['admin', 'content-reports'] as const,
    retentionSummary: () => ['admin', 'retention', 'summary'] as const,
    retentionRuns: (params: { pageSize?: number } = {}) =>
      ['admin', 'retention', 'runs', params] as const,
    retentionAll: () => ['admin', 'retention'] as const,
    consistencyReports: (params: { severityMax?: string; pageSize?: number; cursor?: string }) =>
      ['admin', 'consistency-reports', params] as const,
    upstreamSystemLogs: (params: {
      level?: string;
      source?: string;
      q?: string;
      requestId?: string;
      pageSize?: number;
      cursor?: string;
    }) => ['admin', 'upstream-system-logs', params] as const,
    upstreamApiCallLogs: (params: {
      method?: string;
      minStatus?: number;
      path?: string;
      requestId?: string;
      pageSize?: number;
      cursor?: string;
    }) => ['admin', 'upstream-api-call-logs', params] as const,
    debugLogStreamStatus: () => ['admin', 'debug-log-stream-status'] as const,
    requestTimeline: (requestId: string) => ['admin', 'request-timeline', requestId] as const,
    users: (params: { page?: number; status?: string; q?: string }) =>
      ['admin', 'users', params] as const,
    user: (userId: string) => ['admin', 'user', userId] as const,
    rbacPermissionMatrix: () => ['admin', 'rbac', 'permission-matrix'] as const,
    trips: (params: {
      page?: number;
      status?: string;
      visibility?: string;
      ownerUserId?: string;
      q?: string;
    }) => ['admin', 'trips', params] as const,
    trip: (tripId: string) => ['admin', 'trip', tripId] as const,
    pois: (params: { page?: number; tripId?: string; hasBrokenLink?: boolean; q?: string }) =>
      ['admin', 'pois', params] as const,
    poi: (poiId: string) => ['admin', 'poi', poiId] as const,
    features: (params: {
      q?: string;
      kind?: string[];
      category?: string[];
      status?: string[];
      provider?: string[];
      datasetKey?: string[];
      hasCoord?: boolean;
      hasIssue?: boolean;
      issueType?: string[];
      pageSize?: number;
      cursor?: string;
      sort?: string;
      order?: string;
    }) => ['admin', 'features', params] as const,
    feature: (featureId: string) => ['admin', 'feature', featureId] as const,
    featureSources: (featureId: string) => ['admin', 'feature', featureId, 'sources'] as const,
    featureOverrides: (featureId: string) => ['admin', 'feature', featureId, 'overrides'] as const,
    featureWeatherValues: (featureId: string) =>
      ['admin', 'feature', featureId, 'weather-values'] as const,
    featureChangeRequests: (params: {
      q?: string;
      status?: string[];
      action?: string[];
      pageSize?: number;
    }) => ['admin', 'feature-change-requests', params] as const,
    featureChangeRequestsAll: () => ['admin', 'feature-change-requests'] as const,
    featureRequests: (params: { status?: string; page?: number }) =>
      ['admin', 'feature-requests', params] as const,
    // list-prefix 키 — mutation 후 invalidate 일관성용(파라미터 무관 전체 무효화).
    featureRequestsAll: () => ['admin', 'feature-requests'] as const,
    emails: (params: { status?: string; limit?: number }) => ['admin', 'emails', params] as const,
    emailDeliverability: () => ['admin', 'emails', 'deliverability'] as const,
    emailsAll: () => ['admin', 'emails'] as const,
    audit: (params: { limit?: number }) => ['admin', 'audit', params] as const,
    locationAudit: (params: { userId?: string; from?: string; to?: string; limit?: number }) =>
      ['admin', 'location-audit', params] as const,
    apiCalls: (params: {
      provider?: string;
      statusCode?: number;
      errorClass?: string;
      limit?: number;
    }) => ['admin', 'api-calls', params] as const,
    mcpTokens: (params: { userId?: string; status?: string; q?: string; limit?: number }) =>
      ['admin', 'mcp-tokens', params] as const,
    mcpTokensAll: () => ['admin', 'mcp-tokens'] as const,
    backupSnapshots: (params: { limit?: number } = {}) =>
      ['admin', 'backup', 'snapshots', params] as const,
    seedScenarios: () => ['admin', 'seed', 'scenarios'] as const,
    resetStatus: () => ['admin', 'reset', 'status'] as const,
  },
} as const;

export interface TripRealtimeInvalidationEvent {
  type: string;
  trip_id?: string;
  payload?: Record<string, unknown>;
}

export type PinviQueryKey = readonly unknown[];

const TRIP_DETAIL_REALTIME_EVENTS = new Set([
  'trip.updated',
  'trip.deleted',
  'trip.member_changed',
  'day.created',
  'day.updated',
  'day.deleted',
  'poi.created',
  'poi.updated',
  'poi.deleted',
  'poi.reordered',
]);

const TRIP_COMMENT_REALTIME_EVENTS = new Set(['comment.created', 'comment.deleted']);

function tripIdForRealtimeEvent(
  event: TripRealtimeInvalidationEvent,
  fallbackTripId?: string,
): string | null {
  if (typeof event.trip_id === 'string' && event.trip_id.length > 0) return event.trip_id;
  if (fallbackTripId && fallbackTripId.length > 0) return fallbackTripId;
  return null;
}

export function tripRealtimeInvalidationKeys(
  event: TripRealtimeInvalidationEvent,
  fallbackTripId?: string,
): PinviQueryKey[] {
  const tripId = tripIdForRealtimeEvent(event, fallbackTripId);

  if (TRIP_COMMENT_REALTIME_EVENTS.has(event.type)) {
    return tripId ? [queryKeys.trips.comments(tripId)] : [];
  }

  if (TRIP_DETAIL_REALTIME_EVENTS.has(event.type)) {
    const keys: PinviQueryKey[] = [queryKeys.trips.all()];
    if (tripId) keys.push(queryKeys.trips.detail(tripId));
    return keys;
  }

  return [];
}
