'use client';

import { useMemo, useState, type FormEvent } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { EyeOff, Gavel, Loader2, RefreshCw, RotateCcw, Send, Trash2, XCircle } from 'lucide-react';
import {
  ApiError,
  adminApi,
  queryKeys,
  type AdminContentReportListParams,
} from '@pinvi/api-client';
import type { AdminContentReportRecord, ContentModerationActionType } from '@pinvi/schemas';
import { AdminPage, FilterBar, Section } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { apiClient } from '@/lib/api';

const STATUS_OPTIONS = [
  { value: '', label: '상태 전체' },
  { value: 'received', label: 'received' },
  { value: 'reviewing', label: 'reviewing' },
  { value: 'hidden', label: 'hidden' },
  { value: 'taken_down', label: 'taken_down' },
  { value: 'rejected', label: 'rejected' },
  { value: 'appealed', label: 'appealed' },
  { value: 'restored', label: 'restored' },
] as const;

const TARGET_OPTIONS = [
  { value: '', label: '대상 전체' },
  { value: 'trip', label: 'trip' },
  { value: 'comment', label: 'comment' },
  { value: 'attachment', label: 'attachment' },
  { value: 'share_link', label: 'share_link' },
] as const;

const ACTION_LABEL: Record<Exclude<ContentModerationActionType, 'appeal'>, string> = {
  review: '검토 시작',
  hide: '숨김',
  takedown: '게시중단',
  restore: '복구',
  reject: '기각',
};

type ModerationAction = keyof typeof ACTION_LABEL;
type StatusFilter = Exclude<(typeof STATUS_OPTIONS)[number]['value'], ''>;
type TargetFilter = Exclude<(typeof TARGET_OPTIONS)[number]['value'], ''>;

const textareaClass =
  'min-h-24 rounded-sm border border-hairline px-3 py-2 text-sm outline-none focus:border-primary';

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('ko-KR') : '-';
}

function actionIcon(action: ModerationAction) {
  if (action === 'review') return <Gavel className="h-3.5 w-3.5" />;
  if (action === 'hide') return <EyeOff className="h-3.5 w-3.5" />;
  if (action === 'takedown') return <Trash2 className="h-3.5 w-3.5" />;
  if (action === 'restore') return <RotateCcw className="h-3.5 w-3.5" />;
  return <XCircle className="h-3.5 w-3.5" />;
}

function availableActions(item: AdminContentReportRecord): ModerationAction[] {
  return item.next_actions.filter((action): action is ModerationAction => action !== 'appeal');
}

function ErrorBox({ message }: { message: string }) {
  return (
    <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">
      {message}
    </p>
  );
}

export default function AdminModerationPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_OPTIONS)[number]['value']>('');
  const [targetFilter, setTargetFilter] = useState<(typeof TARGET_OPTIONS)[number]['value']>('');
  const [selectedReport, setSelectedReport] = useState<AdminContentReportRecord | null>(null);
  const [selectedAction, setSelectedAction] = useState<ModerationAction>('review');
  const [accessReason, setAccessReason] = useState('');
  const [resolutionSummary, setResolutionSummary] = useState('');
  const [notice, setNotice] = useState<string | null>(null);

  const params = useMemo<AdminContentReportListParams>(
    () => ({
      status: statusFilter ? (statusFilter as StatusFilter) : undefined,
      targetType: targetFilter ? (targetFilter as TargetFilter) : undefined,
      pageSize: 100,
    }),
    [statusFilter, targetFilter],
  );

  const reportsQuery = useQuery({
    queryKey: queryKeys.admin.contentReports(params),
    queryFn: () => adminApi(apiClient).listContentReports(params),
    placeholderData: keepPreviousData,
  });

  const actionMutation = useMutation({
    mutationFn: async () => {
      if (!selectedReport) throw new Error('신고가 선택되지 않았습니다.');
      const body = {
        access_reason: accessReason.trim(),
        resolution_summary: resolutionSummary.trim(),
      };
      const api = adminApi(apiClient);
      if (selectedAction === 'review')
        return api.reviewContentReport(selectedReport.report_id, body);
      if (selectedAction === 'hide') return api.hideContentReport(selectedReport.report_id, body);
      if (selectedAction === 'takedown') {
        return api.takedownContentReport(selectedReport.report_id, body);
      }
      if (selectedAction === 'restore')
        return api.restoreContentReport(selectedReport.report_id, body);
      return api.rejectContentReport(selectedReport.report_id, body);
    },
    onSuccess: (report) => {
      setNotice(`${report.report_id} 신고를 ${ACTION_LABEL[selectedAction]} 처리했습니다.`);
      setSelectedReport(null);
      setAccessReason('');
      setResolutionSummary('');
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.contentReportsAll() });
    },
  });

  const error =
    (reportsQuery.isError &&
      (reportsQuery.error instanceof ApiError
        ? reportsQuery.error.message
        : '신고 목록 조회에 실패했습니다.')) ||
    (actionMutation.isError &&
      (actionMutation.error instanceof ApiError
        ? actionMutation.error.message
        : actionMutation.error instanceof Error
          ? actionMutation.error.message
          : '신고 조치에 실패했습니다.')) ||
    null;

  const selectAction = (report: AdminContentReportRecord, action: ModerationAction) => {
    setSelectedReport(report);
    setSelectedAction(action);
    setAccessReason('');
    setResolutionSummary(report.resolution_summary ?? '');
    setNotice(null);
  };

  const columns: AdminTableColumn<AdminContentReportRecord>[] = [
    {
      key: 'target',
      header: 'target',
      sortable: true,
      sortValue: (item) => `${item.target_type}:${item.target_id}`,
      cell: (item) => (
        <div>
          <div className="font-mono text-xs">{item.target_id}</div>
          <div className="text-xs text-muted">{item.target_type}</div>
        </div>
      ),
    },
    {
      key: 'reason',
      header: '사유',
      sortable: true,
      sortValue: (item) => item.reason_code,
      cell: (item) => (
        <div>
          <div>{item.reason_code}</div>
          <div className="max-w-sm truncate text-xs text-muted">{item.reason_text}</div>
        </div>
      ),
    },
    {
      key: 'status',
      header: '상태',
      sortable: true,
      sortValue: (item) => item.status,
      cell: (item) => item.status,
    },
    {
      key: 'reporter',
      header: 'reporter',
      sortable: true,
      sortValue: (item) => item.reporter_user_id ?? '',
      cell: (item) => <span className="font-mono text-xs">{item.reporter_user_id ?? '-'}</span>,
    },
    {
      key: 'created',
      header: '접수',
      sortable: true,
      sortValue: (item) => new Date(item.created_at).getTime(),
      cell: (item) => formatDateTime(item.created_at),
    },
    {
      key: 'actions',
      header: '조치',
      cell: (item) => {
        const actions = availableActions(item);
        return (
          <div className="flex items-center gap-1">
            {actions.length === 0 && <span className="text-xs text-muted">-</span>}
            {actions.map((action) => (
              <button
                key={action}
                type="button"
                onClick={() => selectAction(item, action)}
                className="inline-flex h-8 items-center gap-1 rounded-sm border border-hairline px-2 text-xs hover:bg-surface-soft"
                data-testid={`admin-moderation-action-${action}-${item.report_id}`}
              >
                {actionIcon(action)}
                {ACTION_LABEL[action]}
              </button>
            ))}
          </div>
        );
      },
    },
  ];

  const submitAction = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setNotice(null);
    actionMutation.mutate();
  };

  return (
    <AdminPage
      title="Moderation"
      description="콘텐츠 신고 접수, 숨김, 게시중단, 복구, 이의제기 심사 큐."
      actions={
        <button
          type="button"
          onClick={() => void reportsQuery.refetch()}
          disabled={reportsQuery.isFetching}
          className="inline-flex h-10 items-center gap-2 rounded-sm border border-hairline bg-white px-3 text-sm font-semibold text-ink hover:bg-surface-soft disabled:opacity-50"
        >
          {reportsQuery.isFetching ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          )}
          새로고침
        </button>
      }
    >
      {notice && (
        <p className="rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text">{notice}</p>
      )}
      {error && <ErrorBox message={error} />}

      <FilterBar>
        <select
          value={statusFilter}
          onChange={(event) =>
            setStatusFilter(event.target.value as (typeof STATUS_OPTIONS)[number]['value'])
          }
          className="rounded-sm border border-hairline px-2 py-1 text-sm"
          data-testid="admin-moderation-status-filter"
        >
          {STATUS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <select
          value={targetFilter}
          onChange={(event) =>
            setTargetFilter(event.target.value as (typeof TARGET_OPTIONS)[number]['value'])
          }
          className="rounded-sm border border-hairline px-2 py-1 text-sm"
        >
          {TARGET_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </FilterBar>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <AdminTable
          columns={columns}
          rows={reportsQuery.data?.items ?? []}
          loading={reportsQuery.isLoading}
          rowKey={(row) => row.report_id}
          rowTestId={(row) => `admin-moderation-row-${row.report_id}`}
        />

        {selectedReport && (
          <Section title="Moderation 조치">
            <form className="grid gap-3" onSubmit={submitAction}>
              <div className="font-mono text-xs text-muted">{selectedReport.report_id}</div>
              <label className="grid gap-1 text-sm font-semibold text-ink">
                Action
                <select
                  value={selectedAction}
                  onChange={(event) => setSelectedAction(event.target.value as ModerationAction)}
                  className="h-10 rounded-sm border border-hairline px-3 text-sm outline-none focus:border-primary"
                >
                  {availableActions(selectedReport).map((action) => (
                    <option key={action} value={action}>
                      {ACTION_LABEL[action]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="grid gap-1 text-sm font-semibold text-ink">
                처리 요약
                <textarea
                  value={resolutionSummary}
                  onChange={(event) => setResolutionSummary(event.target.value)}
                  className={textareaClass}
                  maxLength={2000}
                  required
                />
              </label>
              <label className="grid gap-1 text-sm font-semibold text-ink">
                접근 사유
                <textarea
                  value={accessReason}
                  onChange={(event) => setAccessReason(event.target.value)}
                  className={textareaClass}
                  maxLength={500}
                  required
                />
              </label>
              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={actionMutation.isPending}
                  className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-sm bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50"
                  data-testid="admin-moderation-action-submit"
                >
                  {actionMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Send className="h-4 w-4" aria-hidden="true" />
                  )}
                  적용
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedReport(null)}
                  className="h-10 rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
                >
                  취소
                </button>
              </div>
            </form>
          </Section>
        )}
      </div>
    </AdminPage>
  );
}
