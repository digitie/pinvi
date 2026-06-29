'use client';

import { useMemo, useState, type FormEvent } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ApiClient,
  ApiError,
  adminApi,
  queryKeys,
  type AdminCategoryMappingListParams,
} from '@pinvi/api-client';
import type { AdminCategoryMappingItem } from '@pinvi/schemas';
import { CATEGORY_MARKER, markerStyleFor, paletteHex, paletteLabelColor } from '@pinvi/domain';
import { Download, Edit3, RefreshCw, RotateCcw, Save, Search, X } from 'lucide-react';
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const inputClass = 'rounded-sm border border-hairline px-2 py-1 text-sm';
const MARKER_COLORS = Array.from(
  { length: 16 },
  (_, index) => `P-${String(index + 1).padStart(2, '0')}`,
);

function formatNumber(value: number | null | undefined) {
  return value === null || value === undefined ? '—' : value.toLocaleString('ko-KR');
}

function localMarkerFor(item: AdminCategoryMappingItem) {
  const hasLocal = Object.prototype.hasOwnProperty.call(CATEGORY_MARKER, item.label);
  const local = hasLocal ? CATEGORY_MARKER[item.label] : null;
  const fallback = markerStyleFor(item.label, null);
  const defaultColor = local?.color ?? fallback.color;
  const defaultIcon = local?.icon ?? fallback.icon;
  const color = item.effective_marker_color ?? defaultColor;
  const localIcon = item.effective_maki_icon ?? item.marker_icon ?? defaultIcon;
  return {
    color,
    hex: paletteHex(color),
    labelColor: paletteLabelColor(color),
    localIcon,
    mapped: Boolean(local || item.has_override),
    iconDrift: Boolean(local && defaultIcon !== item.maki_icon && !item.marker_icon),
    defaultColor,
    defaultIcon,
  };
}

export default function AdminCategoryMappingPage() {
  const queryClient = useQueryClient();
  const [queryInput, setQueryInput] = useState('');
  const [submittedQ, setSubmittedQ] = useState('');
  const [activeMode, setActiveMode] = useState<'all' | 'active'>('all');
  const [includeCounts, setIncludeCounts] = useState(true);
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [draftDisplayName, setDraftDisplayName] = useState('');
  const [draftColor, setDraftColor] = useState('');
  const [draftIcon, setDraftIcon] = useState('');
  const [accessReason, setAccessReason] = useState('');
  const [mutationMessage, setMutationMessage] = useState<string | null>(null);

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

  const refreshCategoryMappings = async () => {
    await queryClient.invalidateQueries({
      queryKey: queryKeys.admin.categoryMappings(params),
    });
  };

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!selectedCode) throw new Error('수정할 카테고리를 선택하세요.');
      return adminApi(apiClient).updateCategoryMapping(selectedCode, {
        display_name_ko: draftDisplayName.trim() || null,
        marker_color: draftColor || null,
        marker_icon: draftIcon.trim() || null,
        access_reason: accessReason.trim(),
      });
    },
    onSuccess: async () => {
      setMutationMessage('override 저장 완료');
      setAccessReason('');
      await refreshCategoryMappings();
    },
  });

  const rollbackMutation = useMutation({
    mutationFn: async () => {
      if (!selectedCode) throw new Error('rollback할 카테고리를 선택하세요.');
      return adminApi(apiClient).rollbackCategoryMapping(selectedCode, {
        access_reason: accessReason.trim(),
      });
    },
    onSuccess: async () => {
      setMutationMessage('override rollback 완료');
      setAccessReason('');
      await refreshCategoryMappings();
    },
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
  const overrideCount = enrichedRows.filter((row) => row.item.has_override).length;
  const selectedRow = enrichedRows.find((row) => row.item.code === selectedCode) ?? null;
  const error = mappingsQuery.isError
    ? mappingsQuery.error instanceof ApiError
      ? mappingsQuery.error.message
      : '카테고리 매핑 조회에 실패했습니다.'
    : null;
  const mutationError =
    updateMutation.error || rollbackMutation.error
      ? updateMutation.error instanceof ApiError
        ? updateMutation.error.message
        : rollbackMutation.error instanceof ApiError
          ? rollbackMutation.error.message
          : '카테고리 override 저장에 실패했습니다.'
      : null;
  const mutationPending = updateMutation.isPending || rollbackMutation.isPending;

  const openEditor = (row: (typeof enrichedRows)[number]) => {
    setSelectedCode(row.item.code);
    setDraftDisplayName(row.item.display_name_ko ?? '');
    setDraftColor(row.item.marker_color ?? row.marker.defaultColor);
    setDraftIcon(row.item.marker_icon ?? row.marker.defaultIcon);
    setAccessReason('');
    setMutationMessage(null);
    updateMutation.reset();
    rollbackMutation.reset();
  };

  const closeEditor = () => {
    setSelectedCode(null);
    setDraftDisplayName('');
    setDraftColor('');
    setDraftIcon('');
    setAccessReason('');
    setMutationMessage(null);
    updateMutation.reset();
    rollbackMutation.reset();
  };

  const saveOverride = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMutationMessage(null);
    updateMutation.reset();
    rollbackMutation.reset();
    updateMutation.mutate();
  };

  const rollbackOverride = () => {
    setMutationMessage(null);
    updateMutation.reset();
    rollbackMutation.reset();
    rollbackMutation.mutate();
  };

  const columns: AdminTableColumn<(typeof enrichedRows)[number]>[] = [
    {
      key: 'category',
      header: 'category',
      sortable: true,
      sortValue: (row) => row.item.label,
      cell: (row) => (
        <div>
          <div className="font-medium">{row.item.label}</div>
          {row.item.effective_label !== row.item.label && (
            <div className="text-xs text-ink">{row.item.effective_label}</div>
          )}
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
      sortValue: (row) =>
        row.item.has_override ? 3 : row.marker.mapped ? (row.marker.iconDrift ? 1 : 2) : 0,
      cell: (row) =>
        row.item.has_override
          ? 'override'
          : row.marker.mapped
            ? row.marker.iconDrift
              ? 'icon drift'
              : 'mapped'
            : 'fallback',
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
    {
      key: 'actions',
      header: '',
      cell: (row) => (
        <button
          type="button"
          onClick={() => openEditor(row)}
          className="inline-flex h-8 w-8 items-center justify-center rounded-sm border border-hairline"
          aria-label={`${row.item.label} override 편집`}
          data-testid={`admin-category-edit-${row.item.code}`}
        >
          <Edit3 className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      ),
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
        upstream_label: item.label,
        effective_label: item.effective_label,
        path: item.path,
        upstream_maki_icon: item.maki_icon,
        override_display_name_ko: item.display_name_ko,
        override_marker_color: item.marker_color,
        override_marker_icon: item.marker_icon,
        effective_marker_color: marker.color,
        effective_marker_icon: marker.localIcon,
        mapping_status: marker.mapped ? (marker.iconDrift ? 'icon_drift' : 'mapped') : 'fallback',
        has_override: item.has_override,
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

      <section className="grid gap-3 md:grid-cols-6" data-testid="admin-category-summary">
        {[
          ['정본', data?.source_of_truth ?? '—'],
          ['카테고리', formatNumber(data?.filtered_count)],
          ['active', formatNumber(data?.active_count)],
          ['override', formatNumber(overrideCount)],
          ['fallback', formatNumber(unmappedCount)],
          ['icon drift', formatNumber(driftCount)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-sm border border-hairline bg-white p-3">
            <div className="text-xs text-muted">{label}</div>
            <div className="mt-1 break-all text-sm font-semibold text-ink">{value}</div>
          </div>
        ))}
      </section>

      {selectedRow && (
        <section
          className="rounded-sm border border-hairline bg-white p-4"
          data-testid="admin-category-editor"
        >
          <div className="mb-3 flex items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-ink">{selectedRow.item.label}</h2>
              <p className="font-mono text-xs text-muted">{selectedRow.item.code}</p>
            </div>
            <button
              type="button"
              onClick={closeEditor}
              className="inline-flex h-8 w-8 items-center justify-center rounded-sm border border-hairline"
              aria-label="override 편집 닫기"
              data-testid="admin-category-editor-close"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
          <form onSubmit={saveOverride} className="grid gap-3 lg:grid-cols-[1fr_1fr_1.4fr_auto]">
            <label className="grid gap-1 text-xs text-muted">
              표시명
              <input
                value={draftDisplayName}
                onChange={(event) => setDraftDisplayName(event.target.value)}
                className={inputClass}
                maxLength={120}
                data-testid="admin-category-display-name"
              />
            </label>
            <label className="grid gap-1 text-xs text-muted">
              아이콘
              <input
                value={draftIcon}
                onChange={(event) => setDraftIcon(event.target.value)}
                className={inputClass}
                pattern="[a-z0-9_-]{1,64}"
                data-testid="admin-category-marker-icon"
              />
            </label>
            <fieldset className="grid gap-1">
              <legend className="text-xs text-muted">색상</legend>
              <div className="flex flex-wrap gap-1.5" data-testid="admin-category-marker-colors">
                {MARKER_COLORS.map((color) => {
                  const hex = paletteHex(color);
                  return (
                    <button
                      key={color}
                      type="button"
                      onClick={() => setDraftColor(color)}
                      className={`h-7 w-7 rounded-full border ${
                        draftColor === color ? 'border-ink ring-2 ring-ink/20' : 'border-hairline'
                      }`}
                      style={{ backgroundColor: hex }}
                      aria-label={color}
                      data-testid={`admin-category-color-${color}`}
                    />
                  );
                })}
              </div>
            </fieldset>
            <label className="grid gap-1 text-xs text-muted lg:col-span-3">
              사유
              <input
                value={accessReason}
                onChange={(event) => setAccessReason(event.target.value)}
                className={inputClass}
                maxLength={500}
                required
                data-testid="admin-category-access-reason"
              />
            </label>
            <div className="flex items-end gap-2">
              <button
                type="submit"
                disabled={!accessReason.trim() || mutationPending}
                className="inline-flex h-9 items-center gap-1 rounded-sm border border-hairline px-3 text-sm disabled:opacity-50"
                data-testid="admin-category-save"
              >
                <Save className="h-3.5 w-3.5" aria-hidden="true" />
                저장
              </button>
              <button
                type="button"
                onClick={rollbackOverride}
                disabled={!accessReason.trim() || mutationPending}
                className="inline-flex h-9 items-center gap-1 rounded-sm border border-hairline px-3 text-sm disabled:opacity-50"
                data-testid="admin-category-rollback"
              >
                <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                rollback
              </button>
            </div>
          </form>
          {(mutationError || mutationMessage) && (
            <p
              role={mutationError ? 'alert' : 'status'}
              className={`mt-3 rounded-sm p-2 text-sm ${
                mutationError ? 'bg-error-bg text-error-text' : 'bg-success-bg text-success-text'
              }`}
              data-testid="admin-category-mutation-status"
            >
              {mutationError ?? mutationMessage}
            </p>
          )}
        </section>
      )}

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
