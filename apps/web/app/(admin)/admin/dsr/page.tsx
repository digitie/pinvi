'use client';

import { useMemo, useState, type FormEvent } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  CheckCircle2,
  ClipboardCheck,
  FileCheck2,
  Loader2,
  RefreshCw,
  Send,
  XCircle,
} from 'lucide-react';
import { ApiError, adminApi, queryKeys, type AdminDsrRequestListParams } from '@pinvi/api-client';
import type { AdminDsrRequestRecord } from '@pinvi/schemas';
import { AdminPage, FilterBar, Section } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { apiClient } from '@/lib/api';

const STATUS_OPTIONS = [
  { value: '', label: '상태 전체' },
  { value: 'received', label: 'received' },
  { value: 'identity_check', label: 'identity_check' },
  { value: 'processing', label: 'processing' },
  { value: 'completed', label: 'completed' },
  { value: 'rejected', label: 'rejected' },
  { value: 'withdrawn', label: 'withdrawn' },
] as const;

const TYPE_OPTIONS = [
  { value: '', label: '유형 전체' },
  { value: 'access', label: 'access' },
  { value: 'correction', label: 'correction' },
  { value: 'delete', label: 'delete' },
  { value: 'suspend', label: 'suspend' },
] as const;

const OVERDUE_OPTIONS = [
  { value: '', label: '마감 전체' },
  { value: 'true', label: 'overdue' },
  { value: 'false', label: 'not overdue' },
] as const;

const ACTION_LABEL = {
  identity_check: '본인 확인',
  process: '처리 시작',
  complete: '완료',
  reject: '거절',
} as const;

type StatusFilter = Exclude<(typeof STATUS_OPTIONS)[number]['value'], ''>;
type TypeFilter = Exclude<(typeof TYPE_OPTIONS)[number]['value'], ''>;
type OverdueFilter = (typeof OVERDUE_OPTIONS)[number]['value'];
type DsrAction = keyof typeof ACTION_LABEL;

const inputClass =
  'h-10 rounded-sm border border-hairline px-3 text-sm outline-none focus:border-primary';
const textareaClass =
  'min-h-24 rounded-sm border border-hairline px-3 py-2 text-sm outline-none focus:border-primary';

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('ko-KR') : '-';
}

function actionsForRequest(item: AdminDsrRequestRecord): DsrAction[] {
  if (item.status === 'received') return ['identity_check'];
  if (item.status === 'identity_check') return ['process', 'reject'];
  if (item.status === 'processing') return ['complete', 'reject'];
  return [];
}

function actionIcon(action: DsrAction) {
  if (action === 'identity_check') return <ClipboardCheck className="h-3.5 w-3.5" />;
  if (action === 'process') return <FileCheck2 className="h-3.5 w-3.5" />;
  if (action === 'complete') return <CheckCircle2 className="h-3.5 w-3.5" />;
  return <XCircle className="h-3.5 w-3.5" />;
}

function ErrorBox({ message }: { message: string }) {
  return (
    <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">
      {message}
    </p>
  );
}

function parseJsonObject(value: string): Record<string, unknown> {
  const parsed = JSON.parse(value) as unknown;
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('export_manifest는 JSON object여야 합니다.');
  }
  return parsed as Record<string, unknown>;
}

export default function AdminDsrPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_OPTIONS)[number]['value']>('');
  const [typeFilter, setTypeFilter] = useState<(typeof TYPE_OPTIONS)[number]['value']>('');
  const [overdueFilter, setOverdueFilter] = useState<OverdueFilter>('');
  const [selectedRequest, setSelectedRequest] = useState<AdminDsrRequestRecord | null>(null);
  const [selectedAction, setSelectedAction] = useState<DsrAction>('identity_check');
  const [accessReason, setAccessReason] = useState('');
  const [identityVerified, setIdentityVerified] = useState(true);
  const [identityNote, setIdentityNote] = useState('');
  const [processingNote, setProcessingNote] = useState('');
  const [resultSummary, setResultSummary] = useState('');
  const [exportManifest, setExportManifest] = useState('{"files":[],"masked_fields":[]}');
  const [partialResponse, setPartialResponse] = useState(false);
  const [rejectionReason, setRejectionReason] = useState('');
  const [notice, setNotice] = useState<string | null>(null);

  const params = useMemo<AdminDsrRequestListParams>(
    () => ({
      status: statusFilter ? (statusFilter as StatusFilter) : undefined,
      requestType: typeFilter ? (typeFilter as TypeFilter) : undefined,
      overdue: overdueFilter === '' ? undefined : overdueFilter === 'true',
      pageSize: 100,
    }),
    [overdueFilter, statusFilter, typeFilter],
  );

  const dsrQuery = useQuery({
    queryKey: queryKeys.admin.dsrRequests(params),
    queryFn: () => adminApi(apiClient).listDsrRequests(params),
    placeholderData: keepPreviousData,
  });

  const actionMutation = useMutation({
    mutationFn: async () => {
      if (!selectedRequest) throw new Error('DSR 요청이 선택되지 않았습니다.');
      const reason = accessReason.trim();
      if (selectedAction === 'identity_check') {
        return adminApi(apiClient).identityCheckDsrRequest(selectedRequest.request_id, {
          access_reason: reason,
          identity_verified: identityVerified,
          identity_note: identityNote.trim() || undefined,
        });
      }
      if (selectedAction === 'process') {
        return adminApi(apiClient).processDsrRequest(selectedRequest.request_id, {
          access_reason: reason,
          processing_note: processingNote.trim() || undefined,
        });
      }
      if (selectedAction === 'complete') {
        return adminApi(apiClient).completeDsrRequest(selectedRequest.request_id, {
          access_reason: reason,
          result_summary: resultSummary.trim(),
          export_manifest: parseJsonObject(exportManifest),
          partial_response: partialResponse,
        });
      }
      return adminApi(apiClient).rejectDsrRequest(selectedRequest.request_id, {
        access_reason: reason,
        rejection_reason: rejectionReason.trim(),
      });
    },
    onSuccess: (request) => {
      setNotice(`${request.request_id} DSR 요청을 ${ACTION_LABEL[selectedAction]} 처리했습니다.`);
      setSelectedRequest(null);
      setAccessReason('');
      setIdentityVerified(true);
      setIdentityNote('');
      setProcessingNote('');
      setResultSummary('');
      setExportManifest('{"files":[],"masked_fields":[]}');
      setPartialResponse(false);
      setRejectionReason('');
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.dsrRequestsAll() });
    },
  });

  const error =
    (dsrQuery.isError &&
      (dsrQuery.error instanceof ApiError
        ? dsrQuery.error.message
        : 'DSR 목록 조회에 실패했습니다.')) ||
    (actionMutation.isError &&
      (actionMutation.error instanceof ApiError
        ? actionMutation.error.message
        : actionMutation.error instanceof Error
          ? actionMutation.error.message
          : 'DSR 조치에 실패했습니다.')) ||
    null;

  const selectAction = (request: AdminDsrRequestRecord, action: DsrAction) => {
    setSelectedRequest(request);
    setSelectedAction(action);
    setAccessReason('');
    setIdentityVerified(true);
    setIdentityNote('');
    setProcessingNote('');
    setResultSummary(request.result_summary ?? '');
    setExportManifest(JSON.stringify(request.export_manifest ?? { files: [], masked_fields: [] }));
    setPartialResponse(request.partial_response);
    setRejectionReason(request.rejection_reason ?? '');
    setNotice(null);
  };

  const columns: AdminTableColumn<AdminDsrRequestRecord>[] = [
    {
      key: 'request',
      header: 'request',
      sortable: true,
      sortValue: (item) => item.request_id,
      cell: (item) => (
        <div>
          <div className="font-mono text-xs">{item.request_id}</div>
          <div className="max-w-xl truncate text-xs text-muted">{item.request_summary}</div>
        </div>
      ),
    },
    {
      key: 'requester',
      header: '요청자',
      sortable: true,
      sortValue: (item) => item.requester_email_masked,
      cell: (item) => <span className="font-mono text-xs">{item.requester_email_masked}</span>,
    },
    {
      key: 'type',
      header: '유형',
      sortable: true,
      sortValue: (item) => item.request_type,
      cell: (item) => item.request_type,
    },
    {
      key: 'status',
      header: '상태',
      sortable: true,
      sortValue: (item) => item.status,
      cell: (item) => item.status,
    },
    {
      key: 'due',
      header: '마감',
      sortable: true,
      sortValue: (item) => new Date(item.due_at).getTime(),
      cell: (item) => (
        <div>
          <div className={item.response_overdue ? 'text-error-text' : undefined}>
            {formatDateTime(item.due_at)}
          </div>
          <div className="text-xs text-muted">
            {item.response_overdue ? 'overdue' : '10일 기준'}
          </div>
        </div>
      ),
    },
    {
      key: 'owner',
      header: 'owner',
      sortable: true,
      sortValue: (item) => item.assigned_cpo_user_id ?? '',
      cell: (item) => <span className="font-mono text-xs">{item.assigned_cpo_user_id ?? '-'}</span>,
    },
    {
      key: 'next',
      header: 'next',
      sortable: true,
      sortValue: (item) => item.next_action,
      cell: (item) => item.next_action,
    },
    {
      key: 'actions',
      header: '조치',
      cell: (item) => {
        const actions = actionsForRequest(item);
        return (
          <div className="flex items-center gap-1">
            {actions.length === 0 && <span className="text-xs text-muted">-</span>}
            {actions.map((action) => (
              <button
                key={action}
                type="button"
                onClick={() => selectAction(item, action)}
                className="inline-flex h-8 items-center gap-1 rounded-sm border border-hairline px-2 text-xs hover:bg-surface-soft"
                data-testid={`admin-dsr-action-${action}-${item.request_id}`}
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
      title="DSR"
      description="개인정보 열람, 정정, 삭제, 처리정지 권리행사 접수와 CPO 처리 큐."
      actions={
        <button
          type="button"
          onClick={() => void dsrQuery.refetch()}
          disabled={dsrQuery.isFetching}
          className="inline-flex h-10 items-center gap-2 rounded-sm border border-hairline bg-white px-3 text-sm font-semibold text-ink hover:bg-surface-soft disabled:opacity-50"
        >
          {dsrQuery.isFetching ? (
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
          data-testid="admin-dsr-status-filter"
        >
          {STATUS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <select
          value={typeFilter}
          onChange={(event) =>
            setTypeFilter(event.target.value as (typeof TYPE_OPTIONS)[number]['value'])
          }
          className="rounded-sm border border-hairline px-2 py-1 text-sm"
        >
          {TYPE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <select
          value={overdueFilter}
          onChange={(event) => setOverdueFilter(event.target.value as OverdueFilter)}
          className="rounded-sm border border-hairline px-2 py-1 text-sm"
        >
          {OVERDUE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </FilterBar>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <AdminTable
          columns={columns}
          rows={dsrQuery.data?.items ?? []}
          loading={dsrQuery.isLoading}
          rowKey={(row) => row.request_id}
          rowTestId={(row) => `admin-dsr-row-${row.request_id}`}
        />

        {selectedRequest && (
          <Section title="상태 조치">
            <form className="grid gap-3" onSubmit={submitAction}>
              <div className="font-mono text-xs text-muted">{selectedRequest.request_id}</div>
              <label className="grid gap-1 text-sm font-semibold text-ink">
                Action
                <select
                  value={selectedAction}
                  onChange={(event) => setSelectedAction(event.target.value as DsrAction)}
                  className={inputClass}
                >
                  {actionsForRequest(selectedRequest).map((action) => (
                    <option key={action} value={action}>
                      {ACTION_LABEL[action]}
                    </option>
                  ))}
                </select>
              </label>
              {selectedAction === 'identity_check' && (
                <>
                  <label className="flex items-center gap-2 text-sm font-semibold text-ink">
                    <input
                      type="checkbox"
                      checked={identityVerified}
                      onChange={(event) => setIdentityVerified(event.target.checked)}
                    />
                    본인 확인 완료
                  </label>
                  <label className="grid gap-1 text-sm font-semibold text-ink">
                    확인 메모
                    <textarea
                      value={identityNote}
                      onChange={(event) => setIdentityNote(event.target.value)}
                      className={textareaClass}
                      maxLength={1000}
                    />
                  </label>
                </>
              )}
              {selectedAction === 'process' && (
                <label className="grid gap-1 text-sm font-semibold text-ink">
                  처리 메모
                  <textarea
                    value={processingNote}
                    onChange={(event) => setProcessingNote(event.target.value)}
                    className={textareaClass}
                    maxLength={1000}
                  />
                </label>
              )}
              {selectedAction === 'complete' && (
                <>
                  <label className="grid gap-1 text-sm font-semibold text-ink">
                    결과 요약
                    <textarea
                      value={resultSummary}
                      onChange={(event) => setResultSummary(event.target.value)}
                      className={textareaClass}
                      maxLength={4000}
                      required
                    />
                  </label>
                  <label className="grid gap-1 text-sm font-semibold text-ink">
                    Export manifest
                    <textarea
                      value={exportManifest}
                      onChange={(event) => setExportManifest(event.target.value)}
                      className={textareaClass}
                      required
                    />
                  </label>
                  <label className="flex items-center gap-2 text-sm font-semibold text-ink">
                    <input
                      type="checkbox"
                      checked={partialResponse}
                      onChange={(event) => setPartialResponse(event.target.checked)}
                    />
                    부분 제공
                  </label>
                </>
              )}
              {selectedAction === 'reject' && (
                <label className="grid gap-1 text-sm font-semibold text-ink">
                  거절 사유
                  <textarea
                    value={rejectionReason}
                    onChange={(event) => setRejectionReason(event.target.value)}
                    className={textareaClass}
                    maxLength={4000}
                    required
                  />
                </label>
              )}
              <label className="grid gap-1 text-sm font-semibold text-ink">
                사유
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
                  data-testid="admin-dsr-action-submit"
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
                  onClick={() => setSelectedRequest(null)}
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
