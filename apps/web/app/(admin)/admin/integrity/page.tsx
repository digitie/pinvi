'use client';

import { useMemo, useState, type FormEvent } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ApiClient,
  ApiError,
  adminApi,
  queryKeys,
  type AdminIntegrityIssueActionBody,
  type AdminConsistencyReportListParams,
  type AdminIntegrityIssueListParams,
} from '@pinvi/api-client';
import type { AdminConsistencyReportRecord, AdminIntegrityIssueRecord } from '@pinvi/schemas';
import { Ban, CheckCircle2, RefreshCw, RotateCcw, X } from 'lucide-react';
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const ISSUE_STATUS_OPTIONS = [
  { value: 'open', label: '열림' },
  { value: 'acknowledged', label: '확인' },
  { value: 'resolved', label: '해결' },
  { value: 'ignored', label: '무시' },
] as const;

const SEVERITY_OPTIONS = [
  { value: 'all', label: 'severity 전체' },
  { value: 'info', label: 'info' },
  { value: 'warning', label: 'warning' },
  { value: 'error', label: 'error' },
  { value: 'critical', label: 'critical' },
] as const;

const REPORT_SEVERITY_OPTIONS = [
  { value: 'all', label: 'report 전체' },
  { value: 'OK', label: 'OK' },
  { value: 'WARN', label: 'WARN' },
  { value: 'ERROR', label: 'ERROR' },
] as const;

type IssueAction = AdminIntegrityIssueActionBody['action'];

const ACTION_LABEL: Record<IssueAction, string> = {
  resolve: '해결',
  ignore: '무시',
  reopen: '재오픈',
};

const inputClass = 'rounded-sm border border-hairline px-2 py-1 text-sm';

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('ko-KR') : '—';
}

function ErrorBox({ message }: { message: string }) {
  return (
    <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">
      {message}
    </p>
  );
}

function issueActions(item: AdminIntegrityIssueRecord): IssueAction[] {
  return item.status === 'resolved' || item.status === 'ignored'
    ? ['reopen']
    : ['resolve', 'ignore'];
}

function IssueActionIcon({ action }: { action: IssueAction }) {
  if (action === 'resolve') {
    return <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />;
  }
  if (action === 'ignore') {
    return <Ban className="h-3.5 w-3.5" aria-hidden="true" />;
  }
  return <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />;
}

export default function AdminIntegrityPage() {
  const queryClient = useQueryClient();
  const [issueStatus, setIssueStatus] =
    useState<(typeof ISSUE_STATUS_OPTIONS)[number]['value']>('open');
  const [severity, setSeverity] = useState<(typeof SEVERITY_OPTIONS)[number]['value']>('all');
  const [provider, setProvider] = useState('');
  const [reportSeverity, setReportSeverity] =
    useState<(typeof REPORT_SEVERITY_OPTIONS)[number]['value']>('all');
  const [selectedIssue, setSelectedIssue] = useState<AdminIntegrityIssueRecord | null>(null);
  const [selectedAction, setSelectedAction] = useState<IssueAction>('resolve');
  const [accessReason, setAccessReason] = useState('');
  const [mapReason, setMapReason] = useState('');
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [mutationNotice, setMutationNotice] = useState<string | null>(null);

  const issueParams = useMemo<AdminIntegrityIssueListParams>(
    () => ({
      status: issueStatus,
      severity: severity === 'all' ? undefined : severity,
      provider: provider.trim() || undefined,
      pageSize: 50,
    }),
    [issueStatus, provider, severity],
  );
  const reportParams = useMemo<AdminConsistencyReportListParams>(
    () => ({
      severityMax: reportSeverity === 'all' ? undefined : reportSeverity,
      pageSize: 50,
    }),
    [reportSeverity],
  );

  const issuesQuery = useQuery({
    queryKey: queryKeys.admin.integrityIssues(issueParams),
    queryFn: () => adminApi(apiClient).listIntegrityIssues(issueParams),
    placeholderData: keepPreviousData,
  });
  const reportsQuery = useQuery({
    queryKey: queryKeys.admin.consistencyReports(reportParams),
    queryFn: () => adminApi(apiClient).listConsistencyReports(reportParams),
    placeholderData: keepPreviousData,
  });
  const actionMutation = useMutation({
    mutationFn: ({ issue, action }: { issue: AdminIntegrityIssueRecord; action: IssueAction }) =>
      adminApi(apiClient).actionIntegrityIssue(issue.issue_id, {
        action,
        access_reason: accessReason.trim(),
        kor_travel_map_reason: mapReason.trim() || undefined,
      }),
    onMutate: () => {
      setMutationError(null);
      setMutationNotice(null);
    },
    onError: (error) => {
      setMutationError(
        error instanceof ApiError ? error.message : '정합성 issue 조치에 실패했습니다.',
      );
    },
    onSuccess: (result) => {
      setMutationNotice(
        `${result.issue.issue_id} issue를 ${ACTION_LABEL[result.action]} 처리했습니다.`,
      );
      setSelectedIssue(null);
      setAccessReason('');
      setMapReason('');
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.integrityIssuesAll() });
      void issuesQuery.refetch();
    },
  });

  const issuesError = issuesQuery.isError
    ? issuesQuery.error instanceof ApiError
      ? issuesQuery.error.message
      : '정합성 issue 조회에 실패했습니다.'
    : null;
  const reportsError = reportsQuery.isError
    ? reportsQuery.error instanceof ApiError
      ? reportsQuery.error.message
      : '정합성 report 조회에 실패했습니다.'
    : null;

  const issueColumns: AdminTableColumn<AdminIntegrityIssueRecord>[] = [
    {
      key: 'issue',
      header: 'issue',
      sortable: true,
      sortValue: (item) => item.issue_id,
      cell: (item) => (
        <div>
          <div className="font-mono text-xs">{item.issue_id}</div>
          <div className="text-xs text-muted">{item.violation_type}</div>
        </div>
      ),
    },
    {
      key: 'severity',
      header: 'severity',
      sortable: true,
      sortValue: (item) => item.severity,
      cell: (item) => item.severity,
    },
    {
      key: 'status',
      header: '상태',
      sortable: true,
      sortValue: (item) => item.status,
      cell: (item) => item.status,
    },
    {
      key: 'target',
      header: 'target',
      sortable: true,
      sortValue: (item) => item.feature_id ?? item.source_record_key ?? '',
      cell: (item) => (
        <div>
          <div className="font-mono text-xs">{item.feature_id ?? '—'}</div>
          <div className="font-mono text-xs text-muted">{item.source_record_key ?? '—'}</div>
        </div>
      ),
    },
    {
      key: 'message',
      header: 'message',
      sortable: true,
      sortValue: (item) => item.message,
      cell: (item) => item.message,
    },
    {
      key: 'detected',
      header: '감지',
      sortable: true,
      sortValue: (item) => new Date(item.detected_at).getTime(),
      cell: (item) => formatDateTime(item.detected_at),
    },
    {
      key: 'actions',
      header: '조치',
      cell: (item) => (
        <div className="flex items-center gap-1">
          {issueActions(item).map((action) => (
            <button
              key={action}
              type="button"
              onClick={() => {
                setSelectedIssue(item);
                setSelectedAction(action);
                setAccessReason('');
                setMapReason('');
                setMutationError(null);
                setMutationNotice(null);
              }}
              className="inline-flex items-center gap-1 rounded-sm border border-hairline px-2 py-1 text-xs hover:bg-surface-soft"
              data-testid={`admin-integrity-action-${action}-${item.issue_id}`}
            >
              <IssueActionIcon action={action} />
              {ACTION_LABEL[action]}
            </button>
          ))}
        </div>
      ),
    },
  ];

  const reportColumns: AdminTableColumn<AdminConsistencyReportRecord>[] = [
    {
      key: 'report',
      header: 'report',
      sortable: true,
      sortValue: (item) => item.report_id,
      cell: (item) => (
        <div>
          <div className="font-mono text-xs">{item.report_id}</div>
          <div className="font-mono text-xs text-muted">{item.batch_id}</div>
        </div>
      ),
    },
    {
      key: 'severity',
      header: 'severity',
      sortable: true,
      sortValue: (item) => item.severity_max,
      cell: (item) => item.severity_max,
    },
    {
      key: 'cases',
      header: 'cases',
      sortable: true,
      sortValue: (item) => item.cases.length,
      cell: (item) => item.cases.length.toLocaleString('ko-KR'),
      align: 'right',
    },
    {
      key: 'started',
      header: '시작',
      sortable: true,
      sortValue: (item) => new Date(item.started_at).getTime(),
      cell: (item) => formatDateTime(item.started_at),
    },
    {
      key: 'finished',
      header: '완료',
      sortable: true,
      sortValue: (item) => (item.finished_at ? new Date(item.finished_at).getTime() : 0),
      cell: (item) => formatDateTime(item.finished_at),
    },
  ];

  const submitIssueAction = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedIssue) return;
    if (!accessReason.trim()) {
      setMutationError('운영 사유를 입력하세요.');
      return;
    }
    actionMutation.mutate({ issue: selectedIssue, action: selectedAction });
  };

  return (
    <AdminPage
      title="정합성"
      description="kor-travel-map consistency issue와 report 조회"
      actions={
        <button
          type="button"
          onClick={() => {
            void issuesQuery.refetch();
            void reportsQuery.refetch();
          }}
          className="inline-flex items-center gap-1 rounded-sm border border-hairline px-3 py-1 text-sm"
          data-testid="admin-integrity-refresh"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          갱신
        </button>
      }
    >
      <FilterBar>
        <select
          value={issueStatus}
          onChange={(event) => setIssueStatus(event.target.value as typeof issueStatus)}
          className={inputClass}
          data-testid="admin-integrity-status"
        >
          {ISSUE_STATUS_OPTIONS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <select
          value={severity}
          onChange={(event) => setSeverity(event.target.value as typeof severity)}
          className={inputClass}
          data-testid="admin-integrity-severity"
        >
          {SEVERITY_OPTIONS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <input
          value={provider}
          onChange={(event) => setProvider(event.target.value)}
          className={`${inputClass} w-40`}
          placeholder="provider"
          data-testid="admin-integrity-provider"
        />
        <select
          value={reportSeverity}
          onChange={(event) => setReportSeverity(event.target.value as typeof reportSeverity)}
          className={inputClass}
          data-testid="admin-integrity-report-severity"
        >
          {REPORT_SEVERITY_OPTIONS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <span className="ml-auto text-xs text-muted">
          {issuesQuery.data?.items.length ?? 0} issues / {reportsQuery.data?.items.length ?? 0}{' '}
          reports
        </span>
      </FilterBar>

      {issuesError && <ErrorBox message={issuesError} />}
      {mutationError && (
        <p
          role="alert"
          className="rounded-sm bg-error-bg p-3 text-sm text-error-text"
          data-testid="admin-integrity-action-error"
        >
          {mutationError}
        </p>
      )}
      {mutationNotice && (
        <p
          className="rounded-sm bg-surface-soft p-3 text-sm text-body"
          data-testid="admin-integrity-action-notice"
        >
          {mutationNotice}
        </p>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Issues</h2>
        <AdminTable
          columns={issueColumns}
          rows={issuesQuery.data?.items ?? []}
          loading={issuesQuery.isLoading}
          rowKey={(item) => item.issue_id}
          rowTestId={(item) => `admin-integrity-issue-row-${item.issue_id}`}
          empty="정합성 issue가 없습니다."
        />
      </section>

      {reportsError && <ErrorBox message={reportsError} />}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Reports</h2>
        <AdminTable
          columns={reportColumns}
          rows={reportsQuery.data?.items ?? []}
          loading={reportsQuery.isLoading}
          rowKey={(item) => item.report_id}
          rowTestId={(item) => `admin-integrity-report-row-${item.report_id}`}
          empty="정합성 report가 없습니다."
        />
      </section>

      {selectedIssue && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4"
          role="presentation"
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="admin-integrity-action-title"
            className="w-full max-w-lg rounded-sm border border-hairline bg-white p-4 shadow-xl"
            data-testid="admin-integrity-action-dialog"
          >
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <h2 id="admin-integrity-action-title" className="text-base font-semibold text-ink">
                  정합성 issue {ACTION_LABEL[selectedAction]}
                </h2>
                <p className="font-mono text-xs text-muted">{selectedIssue.issue_id}</p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedIssue(null)}
                className="rounded-sm border border-hairline p-1 text-muted hover:text-ink"
                aria-label="닫기"
                data-testid="admin-integrity-action-close"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <dl className="mb-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-sm">
              <dt className="text-muted">status</dt>
              <dd>{selectedIssue.status}</dd>
              <dt className="text-muted">type</dt>
              <dd>{selectedIssue.violation_type}</dd>
              <dt className="text-muted">target</dt>
              <dd className="break-all font-mono text-xs">
                {selectedIssue.feature_id ?? selectedIssue.source_record_key ?? '—'}
              </dd>
              <dt className="text-muted">message</dt>
              <dd>{selectedIssue.message}</dd>
            </dl>
            <form className="space-y-3" onSubmit={submitIssueAction}>
              <label className="block text-xs text-muted">
                운영 사유 (Pinvi audit)
                <textarea
                  value={accessReason}
                  onChange={(event) => setAccessReason(event.target.value)}
                  className="mt-1 w-full rounded-sm border border-hairline px-2 py-1 text-sm"
                  rows={2}
                  data-testid="admin-integrity-action-access-reason"
                />
              </label>
              <label className="block text-xs text-muted">
                kor_travel_map 전달 사유
                <textarea
                  value={mapReason}
                  onChange={(event) => setMapReason(event.target.value)}
                  className="mt-1 w-full rounded-sm border border-hairline px-2 py-1 text-sm"
                  rows={2}
                  data-testid="admin-integrity-action-map-reason"
                />
              </label>
              <div className="flex items-center justify-end gap-2 border-t border-hairline pt-3">
                <button
                  type="button"
                  onClick={() => setSelectedIssue(null)}
                  className="rounded-sm border border-hairline px-3 py-1 text-sm"
                  data-testid="admin-integrity-action-cancel"
                >
                  취소
                </button>
                <button
                  type="submit"
                  disabled={actionMutation.isPending}
                  className="inline-flex items-center gap-1 rounded-sm border border-ink bg-ink px-3 py-1 text-sm text-white disabled:opacity-50"
                  data-testid="admin-integrity-action-submit"
                >
                  <IssueActionIcon action={selectedAction} />
                  반영
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </AdminPage>
  );
}
