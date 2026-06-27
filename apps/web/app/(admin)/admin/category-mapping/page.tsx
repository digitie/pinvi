'use client';

import { useMemo, useState, type FormEvent } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import {
  ApiClient,
  ApiError,
  adminApi,
  queryKeys,
  type AdminCategoryMappingListParams,
} from '@pinvi/api-client';
import type { AdminCategoryMappingItem } from '@pinvi/schemas';
import { CATEGORY_MARKER, markerStyleFor, paletteHex, paletteLabelColor } from '@pinvi/domain';
import { Download, RefreshCw, Search } from 'lucide-react';
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const inputClass = 'rounded-sm border border-hairline px-2 py-1 text-sm';

function formatNumber(value: number | null | undefined) {
  return value === null || value === undefined ? '—' : value.toLocaleString('ko-KR');
}

function localMarkerFor(item: AdminCategoryMappingItem) {
  const hasLocal = Object.prototype.hasOwnProperty.call(CATEGORY_MARKER, item.label);
  const local = hasLocal ? CATEGORY_MARKER[item.label] : null;
  const fallback = markerStyleFor(item.label, null);
  const color = local?.color ?? fallback.color;
  const localIcon = local?.icon ?? fallback.icon;
  return {
    color,
    hex: paletteHex(color),
    labelColor: paletteLabelColor(color),
    localIcon,
    mapped: Boolean(local),
    iconDrift: Boolean(local && local.icon !== item.maki_icon),
  };
}

export default function AdminCategoryMappingPage() {
  const [queryInput, setQueryInput] = useState('');
  const [submittedQ, setSubmittedQ] = useState('');
  const [activeMode, setActiveMode] = useState<'all' | 'active'>('all');
  const [includeCounts, setIncludeCounts] = useState(true);

  const params = useMemo<AdminCategoryMappingListParams>(
    () => ({
      q: submittedQ || undefined,
      activeOnly: activeMode === 'active',
      includeCounts,
    }),
    [activeMode, includeCounts, submittedQ],
  );

  const mappingsQuery = useQuery({
    queryKey: queryKeys.admin.categoryMappings(params),
    queryFn: () => adminApi(apiClient).listCategoryMappings(params),
    placeholderData: keepPreviousData,
  });

  const data = mappingsQuery.data ?? null;
  const rows = useMemo(() => data?.items ?? [], [data?.items]);
  const enrichedRows = useMemo(
    () =>
      rows.map((item) => ({
        item,
        marker: localMarkerFor(item),
      })),
    [rows],
  );
  const unmappedCount = enrichedRows.filter((row) => !row.marker.mapped).length;
  const driftCount = enrichedRows.filter((row) => row.marker.iconDrift).length;
  const error = mappingsQuery.isError
    ? mappingsQuery.error instanceof ApiError
      ? mappingsQuery.error.message
      : '카테고리 매핑 조회에 실패했습니다.'
    : null;

  const columns: AdminTableColumn<(typeof enrichedRows)[number]>[] = [
    {
      key: 'category',
      header: 'category',
      sortable: true,
      sortValue: (row) => row.item.label,
      cell: (row) => (
        <div>
          <div className="font-medium">{row.item.label}</div>
          <div className="font-mono text-xs text-muted">{row.item.code}</div>
          <div className="text-xs text-muted">{row.item.path.join(' / ') || '—'}</div>
        </div>
      ),
    },
    {
      key: 'active',
      header: 'active',
      sortable: true,
      sortValue: (row) => (row.item.is_active ? 1 : 0),
      cell: (row) => (row.item.is_active ? 'active' : 'inactive'),
    },
    {
      key: 'upstream_icon',
      header: 'upstream icon',
      sortable: true,
      sortValue: (row) => row.item.maki_icon,
      cell: (row) => <span className="font-mono text-xs">{row.item.maki_icon}</span>,
    },
    {
      key: 'pinvi_marker',
      header: 'Pinvi marker',
      sortable: true,
      sortValue: (row) => row.marker.color,
      cell: (row) => (
        <div className="flex items-center gap-2">
          <span
            className="inline-flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-semibold"
            style={{ backgroundColor: row.marker.hex, color: row.marker.labelColor }}
            aria-hidden="true"
          >
            {row.marker.color.replace('P-', '')}
          </span>
          <div>
            <div className="font-mono text-xs">{row.marker.color}</div>
            <div className="text-xs text-muted">{row.marker.localIcon}</div>
          </div>
        </div>
      ),
    },
    {
      key: 'mapping',
      header: 'mapping',
      sortable: true,
      sortValue: (row) => (row.marker.mapped ? (row.marker.iconDrift ? 1 : 2) : 0),
      cell: (row) =>
        row.marker.mapped ? (row.marker.iconDrift ? 'icon drift' : 'mapped') : 'fallback',
    },
    {
      key: 'features',
      header: 'features',
      sortable: true,
      sortValue: (row) => row.item.db_feature_count ?? -1,
      cell: (row) => formatNumber(row.item.db_feature_count),
      align: 'right',
    },
    {
      key: 'sort',
      header: 'sort',
      sortable: true,
      sortValue: (row) => row.item.sort_order,
      cell: (row) => row.item.sort_order.toLocaleString('ko-KR'),
      align: 'right',
    },
  ];

  const onSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmittedQ(queryInput.trim());
  };

  const exportJson = () => {
    if (!data) return;
    const payload = {
      source_of_truth: data.source_of_truth,
      mode: data.mode,
      exported_at: new Date().toISOString(),
      items: enrichedRows.map(({ item, marker }) => ({
        code: item.code,
        label: item.label,
        path: item.path,
        upstream_maki_icon: item.maki_icon,
        pinvi_marker_color: marker.color,
        pinvi_default_icon: marker.localIcon,
        mapping_status: marker.mapped ? (marker.iconDrift ? 'icon_drift' : 'mapped') : 'fallback',
        db_feature_count: item.db_feature_count,
      })),
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = 'pinvi-category-mappings.json';
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <AdminPage
      title="카테고리 매핑"
      description="kor-travel-map 카테고리 카탈로그와 Pinvi 마커 팔레트 연결"
      actions={
        <>
          <button
            type="button"
            onClick={() => void mappingsQuery.refetch()}
            className="inline-flex items-center gap-1 rounded-sm border border-hairline px-3 py-1 text-sm"
            data-testid="admin-category-refresh"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            갱신
          </button>
          <button
            type="button"
            onClick={exportJson}
            disabled={!data}
            className="inline-flex items-center gap-1 rounded-sm border border-hairline px-3 py-1 text-sm disabled:opacity-50"
            data-testid="admin-category-export"
          >
            <Download className="h-3.5 w-3.5" aria-hidden="true" />
            내보내기
          </button>
        </>
      }
    >
      <FilterBar>
        <form onSubmit={onSearch} className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <label htmlFor="admin-category-search" className="text-xs text-muted">
            검색
          </label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-2 h-4 w-4 text-muted" />
            <input
              id="admin-category-search"
              value={queryInput}
              onChange={(event) => setQueryInput(event.target.value)}
              className={`${inputClass} w-56 pl-7`}
              placeholder="code, label, icon..."
              data-testid="admin-category-search"
            />
          </div>
          <button
            type="submit"
            className="rounded-sm border border-hairline px-3 py-1 text-sm"
            data-testid="admin-category-submit"
          >
            조회
          </button>
        </form>
        <select
          value={activeMode}
          onChange={(event) => setActiveMode(event.target.value as typeof activeMode)}
          className={inputClass}
          data-testid="admin-category-active"
        >
          <option value="all">전체</option>
          <option value="active">active</option>
        </select>
        <label className="flex items-center gap-2 text-xs text-muted">
          <input
            type="checkbox"
            checked={includeCounts}
            onChange={(event) => setIncludeCounts(event.target.checked)}
            data-testid="admin-category-counts"
          />
          counts
        </label>
        <span className="ml-auto text-xs text-muted">{rows.length}행</span>
      </FilterBar>

      {error && (
        <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">
          {error}
        </p>
      )}

      <section className="grid gap-3 md:grid-cols-5" data-testid="admin-category-summary">
        {[
          ['정본', data?.source_of_truth ?? '—'],
          ['카테고리', formatNumber(data?.filtered_count)],
          ['active', formatNumber(data?.active_count)],
          ['fallback', formatNumber(unmappedCount)],
          ['icon drift', formatNumber(driftCount)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-sm border border-hairline bg-white p-3">
            <div className="text-xs text-muted">{label}</div>
            <div className="mt-1 break-all text-sm font-semibold text-ink">{value}</div>
          </div>
        ))}
      </section>

      <AdminTable
        columns={columns}
        rows={enrichedRows}
        loading={mappingsQuery.isLoading}
        rowKey={(row) => row.item.code}
        rowTestId={(row) => `admin-category-row-${row.item.code}`}
        empty="카테고리가 없습니다."
        initialSort={{ columnKey: 'sort', desc: false }}
      />
    </AdminPage>
  );
}
