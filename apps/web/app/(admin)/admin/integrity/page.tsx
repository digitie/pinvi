'use client';

import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
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
import { Ban, CheckCircle2, ChevronRight, RefreshCw, RotateCcw, X } from 'lucide-react';
import { AdminPage, Section } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { FilterBar, FilterField } from '@/components/admin/filter-bar';
import { Button } from '@/components/admin/ui/button';
// KTM `src/components/ui/dialog.tsx` 프리미티브로 수렴(T-356). 이 페이지의 손수 만든
// `role="dialog"` + scrim + Escape/Tab 트랩은 base-ui가 대신한다.
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/admin/ui/dialog';
import { Input } from '@/components/admin/ui/input';
import { NativeSelect } from '@/components/admin/ui/native-select';
import { NativeSelectOption } from '@/components/admin/ui/native-select-option';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const ISSUE_STATUS_OPTIONS = [
  { value: 'open', label: '열림' },
  { value: 'acknowledged', label: '확인' },
  { value: 'resolved', label: '해결' },
  { value: 'ignored', label: '무시' },
] as const;

const ISSUE_SOURCE_OPTIONS = [
  { value: 'all', label: 'source 전체' },
  { value: 'kor_travel_map', label: 'kor-travel-map' },
  { value: 'pinvi_app', label: 'Pinvi app' },
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
  if (item.source === 'pinvi_app') {
    return [];
  }
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
  const [issueSource, setIssueSource] =
    useState<(typeof ISSUE_SOURCE_OPTIONS)[number]['value']>('all');
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
  const [issueCursor, setIssueCursor] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [mutationNotice, setMutationNotice] = useState<string | null>(null);
  const accessReasonRef = useRef<HTMLTextAreaElement | null>(null);
  const actionTriggerRef = useRef<HTMLElement | null>(null);

  const closeIssueActionDialog = () => {
    setSelectedIssue(null);
    // Clear per-issue input/error so reopening for a different issue never shows
    // the previous issue's reason text or error (#347).
    setAccessReason('');
    setMapReason('');
    setMutationError(null);
    // Return focus to the row action button that opened the dialog (WCAG 2.4.3);
    // Esc/backdrop/cancel would otherwise drop focus to <body> (#347).
    const trigger = actionTriggerRef.current;
    actionTriggerRef.current = null;
    trigger?.focus();
  };

  useEffect(() => {
    if (selectedIssue) {
      accessReasonRef.current?.focus();
    }
  }, [selectedIssue]);

  // Escape 닫기 + Tab focus-trap은 base-ui `Dialog`가 담당한다(T-356) — 손수 만든
  // `handleDialogKeyDown`은 걷어냈다. 두 트랩을 겹치면 서로의 preventDefault를 밟는다.

  const issueParams = useMemo<AdminIntegrityIssueListParams>(
    () => ({
      source: issueSource,
      status: issueStatus,
      severity: severity === 'all' ? undefined : severity,
      provider: provider.trim() || undefined,
      pageSize: 50,
      cursor: issueCursor ?? undefined,
    }),
    [issueCursor, issueSource, issueStatus, provider, severity],
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
      closeIssueActionDialog();
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
          <div className="flex flex-wrap items-center gap-1 text-xs text-muted">
            <span>{item.violation_type}</span>
            <span className="rounded-sm border border-hairline px-1 font-mono">{item.source}</span>
          </div>
        </div>
      ),
    },
    {
      key: 'source',
      header: 'source',
      sortable: true,
      sortValue: (item) => item.source,
      cell: (item) => item.source,
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
          {issueActions(item).length === 0 && <span className="text-xs text-muted">read-only</span>}
          {issueActions(item).map((action) => (
            <button
              key={action}
              type="button"
              onClick={(event) => {
                actionTriggerRef.current = event.currentTarget;
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
      accessReasonRef.current?.focus();
      return;
    }
    actionMutation.mutate({ issue: selectedIssue, action: selectedAction });
  };

  const resetIssueCursor = () => setIssueCursor(null);

  return (
    <AdminPage
      title="정합성"
      description="kor-travel-map consistency issue와 Pinvi app integrity issue 조회"
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
        <FilterField htmlFor="admin-integrity-source-filter" label="source">
          <NativeSelect
            id="admin-integrity-source-filter"
            value={issueSource}
            onChange={(event) => {
              setIssueSource(event.target.value as typeof issueSource);
              resetIssueCursor();
            }}
            data-testid="admin-integrity-source"
          >
            {ISSUE_SOURCE_OPTIONS.map((item) => (
              <NativeSelectOption key={item.value} value={item.value}>
                {item.label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </FilterField>
        <FilterField htmlFor="admin-integrity-status-filter" label="상태">
          <NativeSelect
            id="admin-integrity-status-filter"
            value={issueStatus}
            onChange={(event) => {
              setIssueStatus(event.target.value as typeof issueStatus);
              resetIssueCursor();
            }}
            data-testid="admin-integrity-status"
          >
            {ISSUE_STATUS_OPTIONS.map((item) => (
              <NativeSelectOption key={item.value} value={item.value}>
                {item.label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </FilterField>
        <FilterField htmlFor="admin-integrity-severity-filter" label="severity">
          <NativeSelect
            id="admin-integrity-severity-filter"
            value={severity}
            onChange={(event) => {
              setSeverity(event.target.value as typeof severity);
              resetIssueCursor();
            }}
            data-testid="admin-integrity-severity"
          >
            {SEVERITY_OPTIONS.map((item) => (
              <NativeSelectOption key={item.value} value={item.value}>
                {item.label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </FilterField>
        <FilterField className="w-40" htmlFor="admin-integrity-provider-filter" label="provider">
          <Input
            id="admin-integrity-provider-filter"
            value={provider}
            onChange={(event) => {
              setProvider(event.target.value);
              resetIssueCursor();
            }}
            placeholder="provider"
            data-testid="admin-integrity-provider"
          />
        </FilterField>
        {/* 이 컨트롤만 Issues가 아니라 아래 Reports 표를 거른다 — 라벨에 그 대상을 드러낸다. */}
        <FilterField htmlFor="admin-integrity-report-severity-filter" label="report severity">
          <NativeSelect
            id="admin-integrity-report-severity-filter"
            value={reportSeverity}
            onChange={(event) => setReportSeverity(event.target.value as typeof reportSeverity)}
            data-testid="admin-integrity-report-severity"
          >
            {REPORT_SEVERITY_OPTIONS.map((item) => (
              <NativeSelectOption key={item.value} value={item.value}>
                {item.label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </FilterField>
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

      <Section
        title="Issues"
        actions={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={resetIssueCursor}
              disabled={!issueCursor}
              className="inline-flex items-center gap-1 rounded-sm border border-hairline px-2 py-1 text-xs disabled:opacity-50"
              data-testid="admin-integrity-issues-first"
            >
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
              처음
            </button>
            <button
              type="button"
              onClick={() => setIssueCursor(issuesQuery.data?.next_cursor ?? null)}
              disabled={!issuesQuery.data?.next_cursor}
              className="inline-flex items-center gap-1 rounded-sm border border-hairline px-2 py-1 text-xs disabled:opacity-50"
              data-testid="admin-integrity-issues-next"
            >
              다음
              <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
        }
      >
        <AdminTable
          columns={issueColumns}
          rows={issuesQuery.data?.items ?? []}
          loading={issuesQuery.isLoading}
          rowKey={(item) => item.issue_id}
          rowTestId={(item) => `admin-integrity-issue-row-${item.issue_id}`}
          empty="정합성 issue가 없습니다."
        />
      </Section>

      {reportsError && <ErrorBox message={reportsError} />}

      <Section title="Reports">
        <AdminTable
          columns={reportColumns}
          rows={reportsQuery.data?.items ?? []}
          loading={reportsQuery.isLoading}
          rowKey={(item) => item.report_id}
          rowTestId={(item) => `admin-integrity-report-row-${item.report_id}`}
          empty="정합성 report가 없습니다."
        />
      </Section>

      {/* 다이얼로그를 조건부로 **마운트**한다(`open`은 상수 true) — `selectedIssue`가 null이 되는
          즉시 사라지던 기존 동작·상태를 그대로 유지하기 위해서다(닫힘 트랜지션 동안 본문이
          selectedIssue를 잃고 깨지는 문제도 함께 없앤다). */}
      {selectedIssue && (
        <Dialog
          // 을 쓰지 않는다 — 이 모달은 **전환 전에도** Escape로 닫혔고
          // (), 이 그 동작을
          // 단언한다. 여기에 보호를 걸면 그게 오히려 새 회귀다.
          open
          onOpenChange={(open) => {
            // Escape·scrim 클릭·닫기 버튼 전부 이 한 경로로 모인다(기존 closeIssueActionDialog 그대로).
            if (!open) closeIssueActionDialog();
          }}
        >
          <DialogContent
            data-testid="admin-integrity-action-dialog"
            initialFocus={accessReasonRef}
            viewportProps={{ 'data-testid': 'admin-integrity-action-overlay' }}
          >
            <form onSubmit={submitIssueAction}>
              <DialogHeader>
                <div className="min-w-0">
                  <DialogTitle>정합성 issue {ACTION_LABEL[selectedAction]}</DialogTitle>
                  <p className="font-mono text-xs text-muted">{selectedIssue.issue_id}</p>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  onClick={closeIssueActionDialog}
                  aria-label="닫기"
                  data-testid="admin-integrity-action-close"
                >
                  <X aria-hidden="true" />
                </Button>
              </DialogHeader>
              <div className="flex flex-col gap-3 p-4">
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-sm">
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
                <label className="block text-xs text-muted">
                  운영 사유 (Pinvi audit)
                  <textarea
                    ref={accessReasonRef}
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
              </div>
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={closeIssueActionDialog}
                  data-testid="admin-integrity-action-cancel"
                >
                  취소
                </Button>
                <Button
                  type="submit"
                  disabled={actionMutation.isPending}
                  data-testid="admin-integrity-action-submit"
                >
                  <IssueActionIcon action={selectedAction} />
                  반영
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      )}
    </AdminPage>
  );
}
