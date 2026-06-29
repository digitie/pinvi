'use client';

import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi } from '@pinvi/api-client';
import type { NoticePlan, NoticePoi, NoticePoiCreate, NoticePoiUpdate } from '@pinvi/schemas';
import { Edit3, Plus, Save, Trash2, X } from 'lucide-react';
import { NoticeAttachmentPanel } from '@/components/admin/NoticeAttachmentPanel';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const inputClass = 'mt-0.5 w-full rounded-sm border border-hairline px-2 py-1 text-sm';

type PoiDraft = {
  day_index: string;
  sort_order: string;
  feature_id: string;
  feature_snapshot: string;
  memo: string;
  budget_amount: string;
  currency: string;
  user_url: string;
  custom_marker_color: string;
  custom_marker_icon: string;
};

function newDraft(nextSortOrder: string): PoiDraft {
  return {
    day_index: '1',
    sort_order: nextSortOrder,
    feature_id: '',
    feature_snapshot: '{}',
    memo: '',
    budget_amount: '',
    currency: 'KRW',
    user_url: '',
    custom_marker_color: '',
    custom_marker_icon: '',
  };
}

function draftFromPoi(poi: NoticePoi): PoiDraft {
  return {
    day_index: String(poi.day_index),
    sort_order: poi.sort_order,
    feature_id: poi.feature_id ?? '',
    feature_snapshot: JSON.stringify(poi.feature_snapshot ?? {}, null, 2),
    memo: poi.memo ?? '',
    budget_amount: poi.budget_amount ?? '',
    currency: poi.currency,
    user_url: poi.user_url ?? '',
    custom_marker_color: poi.custom_marker_color ?? '',
    custom_marker_icon: poi.custom_marker_icon ?? '',
  };
}

function parseFeatureSnapshot(value: string): Record<string, unknown> {
  const trimmed = value.trim();
  if (!trimmed) return {};
  const parsed: unknown = JSON.parse(trimmed);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('feature snapshot은 JSON object여야 합니다.');
  }
  return parsed as Record<string, unknown>;
}

function createBody(draft: PoiDraft): NoticePoiCreate {
  return {
    day_index: Number(draft.day_index || 1),
    sort_order: draft.sort_order.trim(),
    feature_id: draft.feature_id.trim() || null,
    feature_snapshot: parseFeatureSnapshot(draft.feature_snapshot),
    memo: draft.memo.trim() || null,
    budget_amount: draft.budget_amount.trim() || null,
    currency: draft.currency.trim() || 'KRW',
    user_url: draft.user_url.trim() || null,
    custom_marker_color: draft.custom_marker_color.trim() || null,
    custom_marker_icon: draft.custom_marker_icon.trim() || null,
  };
}

function updateBody(draft: PoiDraft): NoticePoiUpdate {
  return createBody(draft);
}

function nextSortOrder(plan: NoticePlan): string {
  const max = plan.pois.reduce(
    (acc, poi) => Math.max(acc, Number.parseInt(poi.sort_order, 10) || 0),
    0,
  );
  return String(max + 1000).padStart(6, '0');
}

export function NoticePoiEditor({
  plan,
  onReload,
}: {
  plan: NoticePlan;
  onReload: () => Promise<void>;
}) {
  const [newPoi, setNewPoi] = useState(() => newDraft(nextSortOrder(plan)));
  const [editing, setEditing] = useState<NoticePoi | null>(null);
  const [editDraft, setEditDraft] = useState<PoiDraft | null>(null);
  const [selectedAttachmentPoiId, setSelectedAttachmentPoiId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setNewPoi(newDraft(nextSortOrder(plan)));
  }, [plan]);

  const createMutation = useMutation({
    mutationFn: () => adminApi(apiClient).createNoticePoi(plan.notice_plan_id, createBody(newPoi)),
    onSuccess: async () => {
      setMessage('POI를 추가했습니다.');
      setError(null);
      await onReload();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'POI 추가에 실패했습니다.'),
  });

  const updateMutation = useMutation({
    mutationFn: () => {
      if (!editing || !editDraft) throw new Error('수정할 POI가 없습니다.');
      return adminApi(apiClient).updateNoticePoi(
        plan.notice_plan_id,
        editing.notice_poi_id,
        updateBody(editDraft),
        editing.version,
      );
    },
    onSuccess: async () => {
      setMessage('POI를 저장했습니다.');
      setError(null);
      setEditing(null);
      setEditDraft(null);
      await onReload();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'POI 저장에 실패했습니다.'),
  });

  const deleteMutation = useMutation({
    mutationFn: (poi: NoticePoi) =>
      adminApi(apiClient).deleteNoticePoi(plan.notice_plan_id, poi.notice_poi_id, poi.version),
    onSuccess: async () => {
      setMessage('POI를 삭제했습니다.');
      setError(null);
      await onReload();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'POI 삭제에 실패했습니다.'),
  });

  const startEdit = (poi: NoticePoi) => {
    setEditing(poi);
    setEditDraft(draftFromPoi(poi));
    setSelectedAttachmentPoiId(poi.notice_poi_id);
    setMessage(null);
    setError(null);
  };

  const columns = useMemo<AdminTableColumn<NoticePoi>[]>(
    () => [
      {
        key: 'day',
        header: 'day',
        sortable: true,
        sortValue: (row) => row.day_index,
        cell: (row) => row.day_index,
      },
      {
        key: 'sort',
        header: 'sort',
        sortable: true,
        sortValue: (row) => row.sort_order,
        cell: (row) => <span className="font-mono text-xs">{row.sort_order}</span>,
      },
      {
        key: 'feature',
        header: 'feature',
        cell: (row) => row.feature_id ?? '자유 POI',
      },
      {
        key: 'memo',
        header: '메모',
        cell: (row) => row.memo ?? '—',
      },
      {
        key: 'actions',
        header: '작업',
        cell: (row) => (
          <div className="flex gap-1">
            <button
              type="button"
              onClick={() => startEdit(row)}
              className="inline-flex h-8 items-center gap-1 rounded-sm border border-hairline px-2 text-xs font-semibold"
              data-testid={`admin-notice-poi-edit-${row.notice_poi_id}`}
            >
              <Edit3 className="h-3.5 w-3.5" aria-hidden="true" />
              편집
            </button>
            <button
              type="button"
              onClick={() => deleteMutation.mutate(row)}
              className="inline-flex h-8 items-center gap-1 rounded-sm border border-hairline px-2 text-xs font-semibold text-error-text"
            >
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
              삭제
            </button>
          </div>
        ),
      },
    ],
    [deleteMutation],
  );

  const submitNew = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage(null);
    setError(null);
    try {
      createBody(newPoi);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'POI 입력값이 올바르지 않습니다.');
      return;
    }
    createMutation.mutate();
  };

  const submitEdit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage(null);
    setError(null);
    try {
      if (editDraft) updateBody(editDraft);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'POI 입력값이 올바르지 않습니다.');
      return;
    }
    updateMutation.mutate();
  };

  const busy = createMutation.isPending || updateMutation.isPending || deleteMutation.isPending;

  return (
    <section className="space-y-4 rounded-sm border border-hairline bg-white p-4">
      <header>
        <h2 className="text-sm font-semibold text-ink">POI 편집</h2>
        <p className="mt-1 text-xs text-muted">
          feature_id 없이도 추천용 자유 POI를 만들 수 있습니다.
        </p>
      </header>

      {message && (
        <p className="rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text">{message}</p>
      )}
      {error && (
        <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text">
          {error}
        </p>
      )}

      <form
        onSubmit={submitNew}
        className="grid grid-cols-1 gap-2 md:grid-cols-6"
        data-testid="admin-notice-poi-create"
      >
        <PoiFields draft={newPoi} onChange={setNewPoi} compact />
        <div className="md:col-span-6">
          <button
            type="submit"
            disabled={busy}
            className="inline-flex h-9 items-center gap-1 rounded-sm bg-primary px-3 text-sm font-semibold text-white disabled:opacity-50"
            data-testid="admin-notice-poi-add"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            POI 추가
          </button>
        </div>
      </form>

      <AdminTable
        rows={plan.pois}
        columns={columns}
        rowKey={(row) => row.notice_poi_id}
        empty="등록된 POI가 없습니다."
        rowTestId={(row) => `admin-notice-poi-row-${row.notice_poi_id}`}
      />

      {editing && editDraft && (
        <form
          onSubmit={submitEdit}
          className="space-y-3 rounded-sm border border-hairline bg-surface-soft p-3"
        >
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-ink">POI 수정</h3>
            <button
              type="button"
              onClick={() => {
                setEditing(null);
                setEditDraft(null);
              }}
              className="inline-flex h-8 items-center gap-1 rounded-sm border border-hairline px-2 text-xs font-semibold"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
              닫기
            </button>
          </div>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-6">
            <PoiFields draft={editDraft} onChange={setEditDraft} />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="inline-flex h-9 items-center gap-1 rounded-sm bg-ink px-3 text-sm font-semibold text-white disabled:opacity-50"
            data-testid="admin-notice-poi-save"
          >
            <Save className="h-4 w-4" aria-hidden="true" />
            POI 저장
          </button>
        </form>
      )}

      {selectedAttachmentPoiId && (
        <NoticeAttachmentPanel
          planId={plan.notice_plan_id}
          poiId={selectedAttachmentPoiId}
          title="선택한 POI 첨부"
        />
      )}
    </section>
  );
}

function PoiFields({
  draft,
  onChange,
  compact = false,
}: {
  draft: PoiDraft;
  onChange: (next: PoiDraft) => void;
  compact?: boolean;
}) {
  const update = (patch: Partial<PoiDraft>) => onChange({ ...draft, ...patch });
  return (
    <>
      <label className="block text-xs text-muted">
        day
        <input
          value={draft.day_index}
          onChange={(event) => update({ day_index: event.target.value })}
          className={inputClass}
          inputMode="numeric"
          data-testid="admin-notice-poi-day"
        />
      </label>
      <label className="block text-xs text-muted">
        sort
        <input
          value={draft.sort_order}
          onChange={(event) => update({ sort_order: event.target.value })}
          className={inputClass}
          data-testid="admin-notice-poi-sort"
        />
      </label>
      <label className="block text-xs text-muted md:col-span-2">
        feature_id
        <input
          value={draft.feature_id}
          onChange={(event) => update({ feature_id: event.target.value })}
          className={inputClass}
          data-testid="admin-notice-poi-feature"
        />
      </label>
      <label className="block text-xs text-muted md:col-span-2">
        memo
        <input
          value={draft.memo}
          onChange={(event) => update({ memo: event.target.value })}
          className={inputClass}
          data-testid="admin-notice-poi-memo"
        />
      </label>
      {!compact && (
        <>
          <label className="block text-xs text-muted">
            budget
            <input
              value={draft.budget_amount}
              onChange={(event) => update({ budget_amount: event.target.value })}
              className={inputClass}
              inputMode="decimal"
            />
          </label>
          <label className="block text-xs text-muted">
            currency
            <input
              value={draft.currency}
              onChange={(event) => update({ currency: event.target.value.toUpperCase() })}
              className={inputClass}
              maxLength={3}
            />
          </label>
          <label className="block text-xs text-muted md:col-span-2">
            URL
            <input
              value={draft.user_url}
              onChange={(event) => update({ user_url: event.target.value })}
              className={inputClass}
            />
          </label>
          <label className="block text-xs text-muted">
            marker color
            <input
              value={draft.custom_marker_color}
              onChange={(event) => update({ custom_marker_color: event.target.value })}
              className={inputClass}
              placeholder="P-07"
            />
          </label>
          <label className="block text-xs text-muted">
            marker icon
            <input
              value={draft.custom_marker_icon}
              onChange={(event) => update({ custom_marker_icon: event.target.value })}
              className={inputClass}
              placeholder="cafe"
            />
          </label>
          <label className="block text-xs text-muted md:col-span-6">
            feature snapshot JSON
            <textarea
              value={draft.feature_snapshot}
              onChange={(event) => update({ feature_snapshot: event.target.value })}
              className={`${inputClass} min-h-24 font-mono`}
            />
          </label>
        </>
      )}
    </>
  );
}
