'use client';

import { useMemo, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import {
  ApiClient,
  ApiError,
  adminApi,
  queryKeys,
  type AdminConsistencyReportListParams,
  type AdminIntegrityIssueListParams,
} from '@pinvi/api-client';
import type { AdminConsistencyReportRecord, AdminIntegrityIssueRecord } from '@pinvi/schemas';
import { RefreshCw } from 'lucide-react';
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

export default function AdminIntegrityPage() {
  const [issueStatus, setIssueStatus] =
    useState<(typeof ISSUE_STATUS_OPTIONS)[number]['value']>('open');
  const [severity, setSeverity] = useState<(typeof SEVERITY_OPTIONS)[number]['value']>('all');
  const [provider, setProvider] = useState('');
  const [reportSeverity, setReportSeverity] =
    useState<(typeof REPORT_SEVERITY_OPTIONS)[number]['value']>('all');

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
    </AdminPage>
  );
}
