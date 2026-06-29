'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type {
  AdminFeatureDetailOverride,
  AdminFeatureDetailSource,
  WeatherMetric,
} from '@pinvi/schemas';
import { ArrowLeft, CloudSun, Database, History, RefreshCw } from 'lucide-react';
import { AdminPage, FilterBar, Section } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

type FeatureDetailTab = 'sources' | 'overrides' | 'weather-values';

const TAB_META: Record<FeatureDetailTab, { label: string; description: string }> = {
  sources: {
    label: 'Sources',
    description: 'kor-travel-map source link 원천과 match 정보를 조회',
  },
  overrides: {
    label: 'Overrides',
    description: '수동 override history를 read-only로 확인',
  },
  'weather-values': {
    label: 'Weather Values',
    description: 'weather card metric 값을 시간·스타일 단위로 확인',
  },
};

function firstParam(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('ko-KR') : '—';
}

function featureTabHref(featureId: string, tab: FeatureDetailTab) {
  return `/admin/features/${encodeURIComponent(featureId)}/${tab}`;
}

function ErrorBox({ message }: { message: string }) {
  return (
    <p
      role="alert"
      className="rounded-sm bg-error-bg p-3 text-sm text-error-text"
      data-testid="admin-feature-tab-error"
    >
      {message}
    </p>
  );
}

function JsonInline({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="text-muted">—</span>;
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return <span>{String(value)}</span>;
  }
  return <span className="font-mono text-xs">{JSON.stringify(value)}</span>;
}

function TabNav({ featureId, activeTab }: { featureId: string; activeTab: FeatureDetailTab }) {
  const items: Array<{ tab: FeatureDetailTab; icon: typeof Database }> = [
    { tab: 'sources', icon: Database },
    { tab: 'overrides', icon: History },
    { tab: 'weather-values', icon: CloudSun },
  ];
  return (
    <FilterBar>
      <Link
        href="/admin/features"
        className="inline-flex items-center gap-1 rounded-sm border border-hairline px-3 py-1 text-sm"
        data-testid="admin-feature-tab-back"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
        목록
      </Link>
      {items.map(({ tab, icon: Icon }) => (
        <Link
          key={tab}
          href={featureTabHref(featureId, tab)}
          className={`inline-flex items-center gap-1 rounded-sm border px-3 py-1 text-sm ${
            activeTab === tab ? 'border-ink bg-ink text-white' : 'border-hairline bg-white text-ink'
          }`}
          aria-current={activeTab === tab ? 'page' : undefined}
          data-testid={`admin-feature-tab-${tab}`}
        >
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
          {TAB_META[tab].label}
        </Link>
      ))}
      <span className="min-w-0 break-all font-mono text-xs text-muted">{featureId}</span>
    </FilterBar>
  );
}

const sourceColumns: AdminTableColumn<AdminFeatureDetailSource>[] = [
  {
    key: 'source',
    header: 'source',
    sortable: true,
    sortValue: (row) => row.source_record_key,
    cell: (row) => (
      <div className="min-w-0">
        <div className="break-all font-mono text-xs">{row.source_record_key}</div>
        <div className="text-xs text-muted">
          {row.provider} / {row.dataset_key}
        </div>
      </div>
    ),
  },
  {
    key: 'entity',
    header: 'entity',
    sortable: true,
    sortValue: (row) => row.source_entity_id,
    cell: (row) => (
      <div className="text-xs">
        <div>{row.source_entity_type}</div>
        <div className="break-all font-mono text-muted">{row.source_entity_id}</div>
      </div>
    ),
  },
  {
    key: 'match',
    header: 'match',
    sortable: true,
    sortValue: (row) => row.confidence,
    cell: (row) => (
      <div className="text-xs">
        <div>
          {row.source_role} / {row.match_method}
        </div>
        <div className="text-muted">confidence {row.confidence}</div>
      </div>
    ),
  },
  {
    key: 'raw',
    header: 'raw',
    cell: (row) => (
      <div className="text-xs">
        <div>{row.raw_name ?? '—'}</div>
        <div className="max-w-72 truncate text-muted">{row.raw_address ?? '—'}</div>
      </div>
    ),
  },
  {
    key: 'linked_at',
    header: 'linked',
    sortable: true,
    sortValue: (row) => new Date(row.linked_at).getTime(),
    cell: (row) => formatDateTime(row.linked_at),
  },
];

const overrideColumns: AdminTableColumn<AdminFeatureDetailOverride>[] = [
  {
    key: 'field',
    header: 'field',
    sortable: true,
    sortValue: (row) => row.field_path,
    cell: (row) => <span className="break-all font-mono text-xs">{row.field_path}</span>,
  },
  {
    key: 'status',
    header: 'status',
    sortable: true,
    sortValue: (row) => row.status,
    cell: (row) => (
      <div className="text-xs">
        <div>{row.status}</div>
        <div className="text-muted">
          {row.prevent_provider_reactivation ? 'provider reactivation blocked' : 'reactivation ok'}
        </div>
      </div>
    ),
  },
  {
    key: 'values',
    header: 'values',
    cell: (row) => (
      <div className="space-y-1 text-xs">
        <div>
          <span className="text-muted">source </span>
          <JsonInline value={row.source_value} />
        </div>
        <div>
          <span className="text-muted">override </span>
          <JsonInline value={row.override_value} />
        </div>
      </div>
    ),
  },
  {
    key: 'reason',
    header: 'reason',
    cell: (row) => row.reason ?? '—',
  },
  {
    key: 'created_at',
    header: 'created',
    sortable: true,
    sortValue: (row) => new Date(row.created_at).getTime(),
    cell: (row) => formatDateTime(row.created_at),
  },
];

const weatherColumns: AdminTableColumn<WeatherMetric>[] = [
  {
    key: 'metric',
    header: 'metric',
    sortable: true,
    sortValue: (row) => row.metric_key,
    cell: (row) => (
      <div className="text-xs">
        <div className="font-mono">{row.metric_key}</div>
        <div className="text-muted">{row.metric_name ?? '—'}</div>
      </div>
    ),
  },
  {
    key: 'style',
    header: 'style',
    sortable: true,
    sortValue: (row) => row.forecast_style,
    cell: (row) => (
      <div className="text-xs">
        <div>{row.forecast_style}</div>
        <div className="text-muted">{row.timeline_bucket ?? '—'}</div>
      </div>
    ),
  },
  {
    key: 'value',
    header: 'value',
    cell: (row) => (
      <div className="text-xs">
        <div>
          {row.value_text ?? row.value_number ?? '—'} {row.unit ?? ''}
        </div>
        <div className="text-muted">{row.severity ?? 'normal'}</div>
      </div>
    ),
  },
  {
    key: 'time',
    header: 'time',
    sortable: true,
    sortValue: (row) =>
      new Date(row.valid_at ?? row.observed_at ?? row.issued_at ?? '1970-01-01').getTime(),
    cell: (row) => (
      <div className="text-xs">
        <div>{formatDateTime(row.valid_at)}</div>
        <div className="text-muted">obs {formatDateTime(row.observed_at)}</div>
      </div>
    ),
  },
];

function SourcesTab({ featureId }: { featureId: string }) {
  const query = useQuery({
    queryKey: queryKeys.admin.featureSources(featureId),
    queryFn: () => adminApi(apiClient).getFeatureSources(featureId),
  });
  const error = query.isError
    ? query.error instanceof ApiError
      ? query.error.message
      : 'source 조회 실패'
    : null;
  return (
    <Section title="source links">
      {error && <ErrorBox message={error} />}
      <AdminTable
        columns={sourceColumns}
        rows={query.data?.items ?? []}
        loading={query.isLoading}
        rowKey={(row) => row.source_record_key}
        rowTestId={(row) => `admin-feature-source-row-${row.source_record_key}`}
        empty="source link가 없습니다."
      />
    </Section>
  );
}

function OverridesTab({ featureId }: { featureId: string }) {
  const query = useQuery({
    queryKey: queryKeys.admin.featureOverrides(featureId),
    queryFn: () => adminApi(apiClient).getFeatureOverrides(featureId),
  });
  const error = query.isError
    ? query.error instanceof ApiError
      ? query.error.message
      : 'override 조회 실패'
    : null;
  return (
    <Section title="override history">
      {error && <ErrorBox message={error} />}
      <AdminTable
        columns={overrideColumns}
        rows={query.data?.items ?? []}
        loading={query.isLoading}
        rowKey={(row) => row.override_id}
        rowTestId={(row) => `admin-feature-override-row-${row.override_id}`}
        empty="override가 없습니다."
      />
    </Section>
  );
}

function WeatherValuesTab({ featureId }: { featureId: string }) {
  const query = useQuery({
    queryKey: queryKeys.admin.featureWeatherValues(featureId),
    queryFn: () => adminApi(apiClient).getFeatureWeatherValues(featureId),
  });
  const error = query.isError
    ? query.error instanceof ApiError
      ? query.error.message
      : 'weather 값 조회 실패'
    : null;
  const data = query.data ?? null;
  return (
    <Section title="weather values">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-muted">
        <span>asof {formatDateTime(data?.asof)}</span>
        <span>latest {formatDateTime(data?.latest_at)}</span>
        <span>{data?.is_stale ? 'stale' : 'fresh'}</span>
        <span>{data?.source_styles.join(', ') || 'source style 없음'}</span>
        <button
          type="button"
          onClick={() => void query.refetch()}
          className="ml-auto inline-flex items-center gap-1 rounded-sm border border-hairline px-2 py-1 text-xs text-ink"
          data-testid="admin-feature-weather-refresh"
        >
          <RefreshCw className="h-3 w-3" aria-hidden="true" />
          갱신
        </button>
      </div>
      {error && <ErrorBox message={error} />}
      <AdminTable
        columns={weatherColumns}
        rows={data?.items ?? []}
        loading={query.isLoading}
        rowKey={(row) =>
          `${row.metric_key}:${row.forecast_style}:${row.timeline_bucket ?? ''}:${
            row.valid_at ?? row.observed_at ?? row.issued_at ?? ''
          }`
        }
        rowTestId={(row) => `admin-feature-weather-row-${row.metric_key}`}
        empty="weather 값이 없습니다."
      />
    </Section>
  );
}

export function FeatureDetailSubpage({ tab }: { tab: FeatureDetailTab }) {
  const params = useParams();
  const featureId = firstParam(params.feature_id);
  const title = TAB_META[tab].label;

  if (!featureId) {
    return (
      <AdminPage title={title} description="feature_id가 필요합니다.">
        <ErrorBox message="feature_id가 비어 있습니다." />
      </AdminPage>
    );
  }

  return (
    <AdminPage
      title={title}
      description={TAB_META[tab].description}
      actions={
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="inline-flex items-center gap-1 rounded-sm border border-hairline px-3 py-1 text-sm"
          data-testid="admin-feature-tab-page-refresh"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          새로고침
        </button>
      }
    >
      <div className="space-y-4" data-testid="admin-feature-subpage">
        <TabNav featureId={featureId} activeTab={tab} />
        {tab === 'sources' && <SourcesTab featureId={featureId} />}
        {tab === 'overrides' && <OverridesTab featureId={featureId} />}
        {tab === 'weather-values' && <WeatherValuesTab featureId={featureId} />}
      </div>
    </AdminPage>
  );
}
