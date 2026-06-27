'use client';

import { useMemo, useState, type FormEvent } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import {
  ApiClient,
  ApiError,
  adminApi,
  queryKeys,
  type AdminFeatureListParams,
} from '@pinvi/api-client';
import type {
  AdminFeatureDetail,
  AdminFeatureSort,
  AdminFeatureSortOrder,
  AdminFeatureSummary,
} from '@pinvi/schemas';
import { Eye, RefreshCw, Search } from 'lucide-react';
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const FEATURE_KINDS = ['place', 'event', 'notice', 'price', 'weather', 'route', 'area'] as const;
const FEATURE_STATUSES = ['active', 'inactive', 'hidden', 'broken', 'deleted'] as const;
const ISSUE_FILTERS = [
  { value: 'all', label: '이슈 전체' },
  { value: 'yes', label: '이슈 있음' },
  { value: 'no', label: '이슈 없음' },
] as const;
const SORT_OPTIONS: AdminFeatureSort[] = [
  'name',
  'updated_at',
  'created_at',
  'kind',
  'status',
  'provider',
  'issue_count',
];
const PAGE_SIZE_OPTIONS = [25, 50, 100, 200, 500] as const;

type KindFilter = (typeof FEATURE_KINDS)[number] | 'all';
type StatusFilter = (typeof FEATURE_STATUSES)[number] | 'all';
type IssueFilter = (typeof ISSUE_FILTERS)[number]['value'];

const inputClass = 'rounded-sm border border-hairline px-2 py-1 text-sm';

function valuesFromCsv(value: string): string[] | undefined {
  const values = value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  return values.length > 0 ? values : undefined;
}

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('ko-KR') : '—';
}

function coordLabel(feature: Pick<AdminFeatureSummary, 'lon' | 'lat'>) {
  return typeof feature.lon === 'number' && typeof feature.lat === 'number'
    ? `${feature.lon.toFixed(5)}, ${feature.lat.toFixed(5)}`
    : '—';
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-52 overflow-auto rounded-sm bg-surface-soft p-3 text-xs leading-relaxed text-body">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function CountLine({ detail }: { detail: AdminFeatureDetail }) {
  return (
    <div className="grid grid-cols-3 gap-2 text-xs sm:grid-cols-6">
      <span className="rounded-sm bg-surface-soft px-2 py-1">sources {detail.sources.length}</span>
      <span className="rounded-sm bg-surface-soft px-2 py-1">issues {detail.issues.length}</span>
      <span className="rounded-sm bg-surface-soft px-2 py-1">
        overrides {detail.overrides.length}
      </span>
      <span className="rounded-sm bg-surface-soft px-2 py-1">
        versions {detail.versions.length}
      </span>
      <span className="rounded-sm bg-surface-soft px-2 py-1">
        changes {detail.change_requests.length}
      </span>
      <span className="rounded-sm bg-surface-soft px-2 py-1">files {detail.files.length}</span>
    </div>
  );
}

function DetailInspector({ featureId }: { featureId: string | null }) {
  const detailQuery = useQuery({
    queryKey: featureId ? queryKeys.admin.feature(featureId) : ['admin', 'feature', null],
    queryFn: () => adminApi(apiClient).getFeature(featureId as string),
    enabled: Boolean(featureId),
  });

  if (!featureId) {
    return (
      <section
        className="rounded-sm border border-hairline bg-white p-4 text-sm text-muted"
        data-testid="admin-features-detail-empty"
      >
        목록에서 feature를 선택하면 상세 정보가 표시됩니다.
      </section>
    );
  }

  const detail = detailQuery.data ?? null;
  const error = detailQuery.isError
    ? detailQuery.error instanceof ApiError
      ? detailQuery.error.message
      : '상세 조회 실패'
    : null;

  return (
    <section
      className="space-y-4 rounded-sm border border-hairline bg-white p-4"
      data-testid="admin-features-detail"
    >
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold text-ink">
            {detail?.feature.name ?? 'Feature detail'}
          </h2>
          <p className="break-all font-mono text-xs text-muted">{featureId}</p>
        </div>
        <button
          type="button"
          onClick={() => void detailQuery.refetch()}
          className="inline-flex items-center gap-1 rounded-sm border border-hairline px-2 py-1 text-xs"
          data-testid="admin-features-detail-refresh"
        >
          <RefreshCw className="h-3 w-3" aria-hidden="true" />
          갱신
        </button>
      </header>

      {detailQuery.isLoading && <p className="text-sm text-muted">불러오는 중...</p>}
      {error && (
        <p
          role="alert"
          className="rounded-sm bg-error-bg p-3 text-sm text-error-text"
          data-testid="admin-features-detail-error"
        >
          {error}
        </p>
      )}

      {detail && (
        <>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-sm">
            <dt className="text-muted">kind/status</dt>
            <dd>
              {detail.feature.kind} / {detail.feature.status}
            </dd>
            <dt className="text-muted">category</dt>
            <dd>{detail.feature.category}</dd>
            <dt className="text-muted">coord</dt>
            <dd className="font-mono">{coordLabel(detail.feature)}</dd>
            <dt className="text-muted">region</dt>
            <dd>
              {detail.feature.sido_code ?? '—'} / {detail.feature.sigungu_code ?? '—'} /{' '}
              {detail.feature.legal_dong_code ?? '—'}
            </dd>
            <dt className="text-muted">marker</dt>
            <dd>
              {detail.feature.marker_color ?? '—'} / {detail.feature.marker_icon ?? '—'}
            </dd>
            <dt className="text-muted">updated</dt>
            <dd>{formatDateTime(detail.feature.updated_at)}</dd>
          </dl>

          <CountLine detail={detail} />

          <div className="space-y-2 text-sm">
            <details open>
              <summary className="cursor-pointer font-medium">sources</summary>
              <ul className="mt-2 space-y-1 text-xs">
                {detail.sources.slice(0, 6).map((source) => (
                  <li key={source.source_record_key} className="break-all rounded-sm bg-surface-soft p-2">
                    {source.provider} / {source.dataset_key} / {source.source_role} /{' '}
                    {source.confidence}
                  </li>
                ))}
                {detail.sources.length === 0 && <li className="text-muted">—</li>}
              </ul>
            </details>
            <details>
              <summary className="cursor-pointer font-medium">issues</summary>
              <ul className="mt-2 space-y-1 text-xs">
                {detail.issues.slice(0, 6).map((issue) => (
                  <li key={issue.issue_id} className="rounded-sm bg-surface-soft p-2">
                    {issue.severity} / {issue.violation_type} / {issue.status}: {issue.message}
                  </li>
                ))}
                {detail.issues.length === 0 && <li className="text-muted">—</li>}
              </ul>
            </details>
            <details>
              <summary className="cursor-pointer font-medium">address</summary>
              <JsonBlock value={detail.feature.address} />
            </details>
            <details>
              <summary className="cursor-pointer font-medium">detail</summary>
              <JsonBlock value={detail.feature.detail} />
            </details>
            <details>
              <summary className="cursor-pointer font-medium">urls / raw_refs</summary>
              <JsonBlock value={{ urls: detail.feature.urls, raw_refs: detail.feature.raw_refs }} />
            </details>
          </div>
        </>
      )}
    </section>
  );
}

export default function AdminFeaturesPage() {
  const [queryInput, setQueryInput] = useState('');
  const [providerInput, setProviderInput] = useState('');
  const [categoryInput, setCategoryInput] = useState('');
  const [submitted, setSubmitted] = useState({
    q: '',
    providers: undefined as string[] | undefined,
    categories: undefined as string[] | undefined,
  });
  const [kind, setKind] = useState<KindFilter>('all');
  const [status, setStatus] = useState<StatusFilter>('active');
  const [issue, setIssue] = useState<IssueFilter>('all');
  const [sort, setSort] = useState<AdminFeatureSort>('name');
  const [order, setOrder] = useState<AdminFeatureSortOrder>('asc');
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZE_OPTIONS)[number]>(50);
  const [cursorStack, setCursorStack] = useState<string[]>([]);
  const [selectedFeatureId, setSelectedFeatureId] = useState<string | null>(null);

  const cursor = cursorStack.length > 0 ? cursorStack[cursorStack.length - 1] : undefined;
  const pageIndex = cursorStack.length + 1;

  const resetCursor = () => {
    setCursorStack([]);
    setSelectedFeatureId(null);
  };

  const params = useMemo<AdminFeatureListParams>(
    () => ({
      q: submitted.q || undefined,
      kind: kind === 'all' ? undefined : [kind],
      category: submitted.categories,
      status: status === 'all' ? Array.from(FEATURE_STATUSES) : [status],
      provider: submitted.providers,
      hasIssue: issue === 'all' ? undefined : issue === 'yes',
      pageSize,
      cursor,
      sort,
      order,
    }),
    [cursor, issue, kind, order, pageSize, sort, status, submitted],
  );

  const featuresQuery = useQuery({
    queryKey: queryKeys.admin.features(params),
    queryFn: () => adminApi(apiClient).listFeatures(params),
    placeholderData: keepPreviousData,
  });

  const data = featuresQuery.data ?? null;
  const nextCursor = data?.next_cursor ?? null;
  const error = featuresQuery.isError
    ? featuresQuery.error instanceof ApiError
      ? featuresQuery.error.message
      : '조회 실패'
    : null;

  const onSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitted({
      q: queryInput.trim(),
      providers: valuesFromCsv(providerInput),
      categories: valuesFromCsv(categoryInput),
    });
    resetCursor();
  };

  const columns: AdminTableColumn<AdminFeatureSummary>[] = [
    {
      key: 'feature',
      header: 'feature',
      sortable: true,
      sortValue: (feature) => feature.name,
      cell: (feature) => (
        <div>
          <div className="font-medium">{feature.name}</div>
          <div className="break-all font-mono text-xs text-muted">{feature.feature_id}</div>
        </div>
      ),
    },
    {
      key: 'kind',
      header: 'kind/status',
      sortable: true,
      sortValue: (feature) => `${feature.kind}:${feature.status}`,
      cell: (feature) => (
        <div className="text-xs">
          <div>{feature.kind}</div>
          <div className="text-muted">{feature.status}</div>
        </div>
      ),
    },
    {
      key: 'provider',
      header: 'provider',
      sortable: true,
      sortValue: (feature) => feature.primary_provider ?? '',
      cell: (feature) => (
        <div className="text-xs">
          <div>{feature.primary_provider ?? '—'}</div>
          <div className="text-muted">{feature.primary_dataset_key ?? '—'}</div>
        </div>
      ),
    },
    {
      key: 'issue_count',
      header: 'issues',
      sortable: true,
      sortValue: (feature) => feature.issue_count,
      align: 'right',
      cell: (feature) => feature.issue_count,
    },
    {
      key: 'coord',
      header: 'coord/address',
      cell: (feature) => (
        <div className="text-xs">
          <div className="font-mono">{coordLabel(feature)}</div>
          <div className="max-w-64 truncate text-muted">{feature.address_label ?? '—'}</div>
        </div>
      ),
    },
    {
      key: 'updated_at',
      header: 'updated',
      sortable: true,
      sortValue: (feature) => new Date(feature.updated_at).getTime(),
      cell: (feature) => formatDateTime(feature.updated_at),
    },
    {
      key: 'action',
      header: '',
      cell: (feature) => (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            setSelectedFeatureId(feature.feature_id);
          }}
          className="inline-flex items-center gap-1 rounded-sm border border-hairline px-2 py-1 text-xs"
          data-testid={`admin-features-detail-${feature.feature_id}`}
        >
          <Eye className="h-3 w-3" aria-hidden="true" />
          상세
        </button>
      ),
    },
  ];

  return (
    <AdminPage
      title="Features"
      description="kor-travel-map admin API 기반 feature 목록과 원천 상세 조회"
    >
      <FilterBar>
        <form onSubmit={onSearch} className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <label htmlFor="admin-features-search" className="text-xs text-muted">
            검색
          </label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-2 h-4 w-4 text-muted" />
            <input
              id="admin-features-search"
              type="search"
              value={queryInput}
              onChange={(event) => setQueryInput(event.target.value)}
              className={`${inputClass} w-56 pl-7`}
              placeholder="name, address, feature_id"
              data-testid="admin-features-search"
            />
          </div>
          <input
            type="text"
            value={providerInput}
            onChange={(event) => setProviderInput(event.target.value)}
            className={`${inputClass} w-36`}
            placeholder="provider"
            data-testid="admin-features-provider-filter"
          />
          <input
            type="text"
            value={categoryInput}
            onChange={(event) => setCategoryInput(event.target.value)}
            className={`${inputClass} w-36`}
            placeholder="category"
            data-testid="admin-features-category-filter"
          />
          <button
            type="submit"
            className="rounded-sm border border-hairline px-3 py-1 text-sm"
            data-testid="admin-features-search-submit"
          >
            조회
          </button>
        </form>

        <select
          value={kind}
          onChange={(event) => {
            setKind(event.target.value as KindFilter);
            resetCursor();
          }}
          className={inputClass}
          data-testid="admin-features-kind-filter"
        >
          <option value="all">kind 전체</option>
          {FEATURE_KINDS.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as StatusFilter);
            resetCursor();
          }}
          className={inputClass}
          data-testid="admin-features-status-filter"
        >
          <option value="all">status 전체</option>
          {FEATURE_STATUSES.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <select
          value={issue}
          onChange={(event) => {
            setIssue(event.target.value as IssueFilter);
            resetCursor();
          }}
          className={inputClass}
          data-testid="admin-features-issue-filter"
        >
          {ISSUE_FILTERS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </FilterBar>

      <FilterBar>
        <label htmlFor="admin-features-sort" className="text-xs text-muted">
          정렬
        </label>
        <select
          id="admin-features-sort"
          value={sort}
          onChange={(event) => {
            setSort(event.target.value as AdminFeatureSort);
            resetCursor();
          }}
          className={inputClass}
          data-testid="admin-features-sort-filter"
        >
          {SORT_OPTIONS.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <select
          value={order}
          onChange={(event) => {
            setOrder(event.target.value as AdminFeatureSortOrder);
            resetCursor();
          }}
          className={inputClass}
          data-testid="admin-features-order-filter"
        >
          <option value="asc">asc</option>
          <option value="desc">desc</option>
        </select>
        <select
          value={String(pageSize)}
          onChange={(event) => {
            setPageSize(Number(event.target.value) as typeof pageSize);
            resetCursor();
          }}
          className={inputClass}
          data-testid="admin-features-page-size"
        >
          {PAGE_SIZE_OPTIONS.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={featuresQuery.isFetching}
          onClick={() => void featuresQuery.refetch()}
          className="inline-flex items-center gap-1 rounded-sm border border-hairline px-3 py-1 text-sm disabled:opacity-50"
          data-testid="admin-features-refresh"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          갱신
        </button>
        <span className="ml-auto text-xs text-muted">
          {data?.items.length ?? 0}행 / page {pageIndex}
          {data?.duration_ms !== null && data?.duration_ms !== undefined
            ? ` / ${data.duration_ms}ms`
            : ''}
        </span>
      </FilterBar>

      {error && (
        <p
          role="alert"
          className="rounded-sm bg-error-bg p-3 text-sm text-error-text"
          data-testid="admin-features-error"
        >
          {error}
        </p>
      )}

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_28rem]">
        <div className="min-w-0 space-y-3">
          <AdminTable
            columns={columns}
            rows={data?.items ?? []}
            loading={featuresQuery.isLoading}
            rowKey={(feature) => feature.feature_id}
            rowTestId={(feature) => `admin-features-row-${feature.feature_id}`}
            onRowClick={(feature) => setSelectedFeatureId(feature.feature_id)}
            empty="feature가 없습니다."
          />

          <div className="flex items-center justify-between text-sm">
            <button
              type="button"
              disabled={cursorStack.length === 0}
              onClick={() => {
                setCursorStack([]);
                setSelectedFeatureId(null);
              }}
              className="rounded-sm border border-hairline px-3 py-1 disabled:opacity-50"
              data-testid="admin-features-first"
            >
              첫 페이지
            </button>
            <span className="text-muted">page {pageIndex}</span>
            <button
              type="button"
              disabled={!nextCursor}
              onClick={() => {
                if (!nextCursor) return;
                setCursorStack((stack) => [...stack, nextCursor]);
                setSelectedFeatureId(null);
              }}
              className="rounded-sm border border-hairline px-3 py-1 disabled:opacity-50"
              data-testid="admin-features-next"
            >
              다음
            </button>
          </div>
        </div>

        <DetailInspector featureId={selectedFeatureId} />
      </section>
    </AdminPage>
  );
}
