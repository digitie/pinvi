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
      status?: string;
      severity?: string;
      violationType?: string;
      provider?: string;
      datasetKey?: string;
      featureId?: string;
      pageSize?: number;
      cursor?: string;
    }) => ['admin', 'integrity-issues', params] as const,
    consistencyReports: (params: { severityMax?: string; pageSize?: number; cursor?: string }) =>
      ['admin', 'consistency-reports', params] as const,
    upstreamSystemLogs: (params: {
      level?: string;
      source?: string;
      q?: string;
      pageSize?: number;
      cursor?: string;
    }) => ['admin', 'upstream-system-logs', params] as const,
    upstreamApiCallLogs: (params: {
      method?: string;
      minStatus?: number;
      path?: string;
      pageSize?: number;
      cursor?: string;
    }) => ['admin', 'upstream-api-call-logs', params] as const,
    users: (params: { page?: number; status?: string; q?: string }) =>
      ['admin', 'users', params] as const,
    user: (userId: string) => ['admin', 'user', userId] as const,
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
    emails: (params: { status?: string; limit?: number }) =>
      ['admin', 'emails', params] as const,
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
  },
} as const;
