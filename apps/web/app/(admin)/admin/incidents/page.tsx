'use client';

import { useMemo, useState, type FormEvent } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Bell,
  CheckCircle2,
  ClipboardCheck,
  FileCheck2,
  Loader2,
  RefreshCw,
  Send,
  ShieldAlert,
} from 'lucide-react';
import {
  ApiError,
  adminApi,
  queryKeys,
  type AdminSecurityIncidentListParams,
} from '@pinvi/api-client';
import type { AdminSecurityIncidentRecord } from '@pinvi/schemas';
import { AdminPage, FilterBar, Section } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { apiClient } from '@/lib/api';

const STATUS_OPTIONS = [
  { value: '', label: '상태 전체' },
  { value: 'detected', label: 'detected' },
  { value: 'triage', label: 'triage' },
  { value: 'notification_decision', label: 'notification_decision' },
  { value: 'reported', label: 'reported' },
  { value: 'closed', label: 'closed' },
] as const;

const SEVERITY_OPTIONS = [
  { value: '', label: 'severity 전체' },
  { value: 'low', label: 'low' },
  { value: 'medium', label: 'medium' },
  { value: 'high', label: 'high' },
  { value: 'critical', label: 'critical' },
] as const;

const OVERDUE_OPTIONS = [
  { value: '', label: 'SLA 전체' },
  { value: 'cpo_review', label: 'CPO review overdue' },
  { value: 'external_report', label: '72h report overdue' },
] as const;

const ACTION_LABEL = {
  triage: 'Triage',
  decision: '판정',
  notify: '통지',
  report: '신고',
  close: '종결',
} as const;

type IncidentAction = keyof typeof ACTION_LABEL;
type StatusFilter = Exclude<(typeof STATUS_OPTIONS)[number]['value'], ''>;
type SeverityFilter = Exclude<(typeof SEVERITY_OPTIONS)[number]['value'], ''>;
type OverdueFilter = Exclude<(typeof OVERDUE_OPTIONS)[number]['value'], ''>;

const inputClass =
  'h-10 rounded-sm border border-hairline px-3 text-sm outline-none focus:border-primary';
const textareaClass =
  'min-h-24 rounded-sm border border-hairline px-3 py-2 text-sm outline-none focus:border-primary';

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('ko-KR') : '-';
}

function actionsForIncident(item: AdminSecurityIncidentRecord): IncidentAction[] {
  if (item.status === 'detected') return ['triage'];
  if (item.status === 'triage') return ['decision'];
  if (item.status === 'notification_decision') {
    const actions: IncidentAction[] = [];
    if (item.notification_required && !item.notified_at) actions.push('notify');
    if (!item.notification_required || item.notified_at) actions.push('report');
    if (!item.notification_required) actions.push('close');
    return actions;
  }
  if (item.status === 'reported') return ['close'];
  return [];
}

function ActionIcon({ action }: { action: IncidentAction }) {
  if (action === 'triage') return <ClipboardCheck className="h-3.5 w-3.5" aria-hidden="true" />;
  if (action === 'decision') return <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />;
  if (action === 'notify') return <Bell className="h-3.5 w-3.5" aria-hidden="true" />;
  if (action === 'report') return <FileCheck2 className="h-3.5 w-3.5" aria-hidden="true" />;
  return <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />;
}

function ErrorBox({ message }: { message: string }) {
  return (
    <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">
      {message}
    </p>
  );
}

export default function AdminIncidentsPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_OPTIONS)[number]['value']>('');
  const [severityFilter, setSeverityFilter] =
    useState<(typeof SEVERITY_OPTIONS)[number]['value']>('');
  const [overdueFilter, setOverdueFilter] = useState<(typeof OVERDUE_OPTIONS)[number]['value']>('');
  const [incidentType, setIncidentType] = useState('admin_export_anomaly');
  const [createSeverity, setCreateSeverity] = useState<SeverityFilter>('high');
  const [source, setSource] = useState('admin_audit_log');
  const [summary, setSummary] = useState('');
  const [affectedCount, setAffectedCount] = useState('0');
  const [createReason, setCreateReason] = useState('');
  const [selectedIncident, setSelectedIncident] = useState<AdminSecurityIncidentRecord | null>(
    null,
  );
  const [selectedAction, setSelectedAction] = useState<IncidentAction>('triage');
  const [actionReason, setActionReason] = useState('');
  const [decisionRequired, setDecisionRequired] = useState(true);
  const [decisionReason, setDecisionReason] = useState('');
  const [notifyEmail, setNotifyEmail] = useState('');
  const [notifyMessage, setNotifyMessage] = useState('');
  const [receiptRef, setReceiptRef] = useState('');
  const [closureNote, setClosureNote] = useState('');
  const [notice, setNotice] = useState<string | null>(null);

  const params = useMemo<AdminSecurityIncidentListParams>(
    () => ({
      status: statusFilter ? (statusFilter as StatusFilter) : undefined,
      severity: severityFilter ? (severityFilter as SeverityFilter) : undefined,
      overdue: overdueFilter ? (overdueFilter as OverdueFilter) : undefined,
      pageSize: 100,
    }),
    [overdueFilter, severityFilter, statusFilter],
  );

  const incidentsQuery = useQuery({
    queryKey: queryKeys.admin.securityIncidents(params),
    queryFn: () => adminApi(apiClient).listSecurityIncidents(params),
    placeholderData: keepPreviousData,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      adminApi(apiClient).createSecurityIncident({
        incident_type: incidentType.trim(),
        severity: createSeverity,
        source: source.trim() || undefined,
        summary: summary.trim(),
        details: {},
        affected_user_count: Number.parseInt(affectedCount, 10) || 0,
        access_reason: createReason.trim(),
      }),
    onSuccess: (incident) => {
      setNotice(`${incident.incident_id} incident를 등록했습니다.`);
      setSummary('');
      setCreateReason('');
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.securityIncidentsAll() });
    },
  });

  const actionMutation = useMutation({
    mutationFn: async () => {
      if (!selectedIncident) throw new Error('incident가 선택되지 않았습니다.');
      const reason = actionReason.trim();
      if (selectedAction === 'triage') {
        return adminApi(apiClient).triageSecurityIncident(selectedIncident.incident_id, {
          access_reason: reason,
        });
      }
      if (selectedAction === 'decision') {
        return adminApi(apiClient).decideSecurityIncidentNotification(
          selectedIncident.incident_id,
          {
            notification_required: decisionRequired,
            decision_reason: decisionReason.trim(),
            access_reason: reason,
          },
        );
      }
      if (selectedAction === 'notify') {
        return adminApi(apiClient).notifySecurityIncidentSubjects(selectedIncident.incident_id, {
          recipient_email: notifyEmail.trim() || undefined,
          subject: 'Pinvi 개인정보 보호 알림',
          message: notifyMessage.trim(),
          access_reason: reason,
        });
      }
      if (selectedAction === 'report') {
        return adminApi(apiClient).reportSecurityIncidentExternal(selectedIncident.incident_id, {
          receipt_ref: receiptRef.trim(),
          access_reason: reason,
        });
      }
      return adminApi(apiClient).closeSecurityIncident(selectedIncident.incident_id, {
        closure_note: closureNote.trim(),
        access_reason: reason,
      });
    },
    onSuccess: (incident) => {
      setNotice(`${incident.incident_id} incident를 ${ACTION_LABEL[selectedAction]} 처리했습니다.`);
      setSelectedIncident(null);
      setActionReason('');
      setDecisionReason('');
      setNotifyEmail('');
      setNotifyMessage('');
      setReceiptRef('');
      setClosureNote('');
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.securityIncidentsAll() });
    },
  });

  const error =
    (incidentsQuery.isError &&
      (incidentsQuery.error instanceof ApiError
        ? incidentsQuery.error.message
        : 'incident 목록 조회에 실패했습니다.')) ||
    (createMutation.isError &&
      (createMutation.error instanceof ApiError
        ? createMutation.error.message
        : 'incident 등록에 실패했습니다.')) ||
    (actionMutation.isError &&
      (actionMutation.error instanceof ApiError
        ? actionMutation.error.message
        : 'incident 조치에 실패했습니다.')) ||
    null;

  const selectAction = (incident: AdminSecurityIncidentRecord, action: IncidentAction) => {
    setSelectedIncident(incident);
    setSelectedAction(action);
    setActionReason('');
    setDecisionRequired(action === 'decision' ? true : incident.notification_required);
    setDecisionReason('');
    setNotifyEmail('');
    setNotifyMessage('');
    setReceiptRef(incident.external_report_receipt_ref ?? '');
    setClosureNote('');
    setNotice(null);
  };

  const columns: AdminTableColumn<AdminSecurityIncidentRecord>[] = [
    {
      key: 'incident',
      header: 'incident',
      sortable: true,
      sortValue: (item) => item.incident_id,
      cell: (item) => (
        <div>
          <div className="font-mono text-xs">{item.incident_id}</div>
          <div className="max-w-xl truncate text-xs text-muted">{item.summary}</div>
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
      key: 'affected',
      header: '영향',
      sortable: true,
      sortValue: (item) => item.affected_user_count,
      cell: (item) => item.affected_user_count.toLocaleString('ko-KR'),
      align: 'right',
    },
    {
      key: 'due',
      header: 'due',
      sortable: true,
      sortValue: (item) => new Date(item.external_report_due_at).getTime(),
      cell: (item) => (
        <div>
          <div className={item.cpo_review_overdue ? 'text-error-text' : undefined}>
            CPO {formatDateTime(item.cpo_review_due_at)}
          </div>
          <div className={item.external_report_overdue ? 'text-error-text' : 'text-muted'}>
            72h {formatDateTime(item.external_report_due_at)}
          </div>
        </div>
      ),
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
        const actions = actionsForIncident(item);
        return (
          <div className="flex items-center gap-1">
            {actions.length === 0 && <span className="text-xs text-muted">-</span>}
            {actions.map((action) => (
              <button
                key={action}
                type="button"
                onClick={() => selectAction(item, action)}
                className="inline-flex h-8 items-center gap-1 rounded-sm border border-hairline px-2 text-xs hover:bg-surface-soft"
                data-testid={`admin-incident-action-${action}-${item.incident_id}`}
              >
                <ActionIcon action={action} />
                {ACTION_LABEL[action]}
              </button>
            ))}
          </div>
        );
      },
    },
  ];

  const submitCreate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setNotice(null);
    createMutation.mutate();
  };

  const submitAction = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setNotice(null);
    actionMutation.mutate();
  };

  return (
    <AdminPage
      title="Security incidents"
      description="PIPA incident CPO review, subject notification, KISA/PIPC report workflow."
      actions={
        <button
          type="button"
          onClick={() => void incidentsQuery.refetch()}
          disabled={incidentsQuery.isFetching}
          className="inline-flex h-10 items-center gap-2 rounded-sm border border-hairline bg-white px-3 text-sm font-semibold text-ink hover:bg-surface-soft disabled:opacity-50"
        >
          {incidentsQuery.isFetching ? (
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
          data-testid="admin-incidents-status-filter"
        >
          {STATUS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <select
          value={severityFilter}
          onChange={(event) =>
            setSeverityFilter(event.target.value as (typeof SEVERITY_OPTIONS)[number]['value'])
          }
          className="rounded-sm border border-hairline px-2 py-1 text-sm"
        >
          {SEVERITY_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <select
          value={overdueFilter}
          onChange={(event) =>
            setOverdueFilter(event.target.value as (typeof OVERDUE_OPTIONS)[number]['value'])
          }
          className="rounded-sm border border-hairline px-2 py-1 text-sm"
        >
          {OVERDUE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </FilterBar>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          <AdminTable
            columns={columns}
            rows={incidentsQuery.data?.items ?? []}
            loading={incidentsQuery.isLoading}
            rowKey={(row) => row.incident_id}
            rowTestId={(row) => `admin-incidents-row-${row.incident_id}`}
          />
        </div>

        <div className="space-y-4">
          <Section title="새 incident">
            <form className="grid gap-3" onSubmit={submitCreate}>
              <label className="grid gap-1 text-sm font-semibold text-ink">
                유형
                <input
                  value={incidentType}
                  onChange={(event) => setIncidentType(event.target.value)}
                  className={inputClass}
                  maxLength={64}
                />
              </label>
              <label className="grid gap-1 text-sm font-semibold text-ink">
                Severity
                <select
                  value={createSeverity}
                  onChange={(event) => setCreateSeverity(event.target.value as SeverityFilter)}
                  className={inputClass}
                >
                  {SEVERITY_OPTIONS.filter((option) => option.value).map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="grid gap-1 text-sm font-semibold text-ink">
                Source
                <input
                  value={source}
                  onChange={(event) => setSource(event.target.value)}
                  className={inputClass}
                  maxLength={64}
                />
              </label>
              <label className="grid gap-1 text-sm font-semibold text-ink">
                Summary
                <input
                  value={summary}
                  onChange={(event) => setSummary(event.target.value)}
                  className={inputClass}
                  maxLength={240}
                  required
                />
              </label>
              <label className="grid gap-1 text-sm font-semibold text-ink">
                영향 사용자
                <input
                  type="number"
                  min={0}
                  value={affectedCount}
                  onChange={(event) => setAffectedCount(event.target.value)}
                  className={inputClass}
                />
              </label>
              <label className="grid gap-1 text-sm font-semibold text-ink">
                사유
                <textarea
                  value={createReason}
                  onChange={(event) => setCreateReason(event.target.value)}
                  className={textareaClass}
                  maxLength={500}
                  required
                />
              </label>
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="inline-flex h-10 items-center justify-center gap-2 rounded-sm bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50"
                data-testid="admin-incidents-create"
              >
                {createMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <ShieldAlert className="h-4 w-4" aria-hidden="true" />
                )}
                등록
              </button>
            </form>
          </Section>

          {selectedIncident && (
            <Section title="상태 조치">
              <form className="grid gap-3" onSubmit={submitAction}>
                <div className="font-mono text-xs text-muted">{selectedIncident.incident_id}</div>
                <label className="grid gap-1 text-sm font-semibold text-ink">
                  Action
                  <select
                    value={selectedAction}
                    onChange={(event) => setSelectedAction(event.target.value as IncidentAction)}
                    className={inputClass}
                  >
                    {actionsForIncident(selectedIncident).map((action) => (
                      <option key={action} value={action}>
                        {ACTION_LABEL[action]}
                      </option>
                    ))}
                  </select>
                </label>
                {selectedAction === 'decision' && (
                  <>
                    <label className="flex items-center gap-2 text-sm font-semibold text-ink">
                      <input
                        type="checkbox"
                        checked={decisionRequired}
                        onChange={(event) => setDecisionRequired(event.target.checked)}
                      />
                      정보주체 통지 필요
                    </label>
                    <label className="grid gap-1 text-sm font-semibold text-ink">
                      판정 사유
                      <textarea
                        value={decisionReason}
                        onChange={(event) => setDecisionReason(event.target.value)}
                        className={textareaClass}
                        maxLength={1000}
                        required
                      />
                    </label>
                  </>
                )}
                {selectedAction === 'notify' && (
                  <>
                    <label className="grid gap-1 text-sm font-semibold text-ink">
                      수신 이메일
                      <input
                        value={notifyEmail}
                        onChange={(event) => setNotifyEmail(event.target.value)}
                        className={inputClass}
                        maxLength={320}
                      />
                    </label>
                    <label className="grid gap-1 text-sm font-semibold text-ink">
                      통지 내용
                      <textarea
                        value={notifyMessage}
                        onChange={(event) => setNotifyMessage(event.target.value)}
                        className={textareaClass}
                        maxLength={4000}
                        required
                      />
                    </label>
                  </>
                )}
                {selectedAction === 'report' && (
                  <label className="grid gap-1 text-sm font-semibold text-ink">
                    접수번호
                    <input
                      value={receiptRef}
                      onChange={(event) => setReceiptRef(event.target.value)}
                      className={inputClass}
                      maxLength={160}
                      required
                    />
                  </label>
                )}
                {selectedAction === 'close' && (
                  <label className="grid gap-1 text-sm font-semibold text-ink">
                    종결 메모
                    <textarea
                      value={closureNote}
                      onChange={(event) => setClosureNote(event.target.value)}
                      className={textareaClass}
                      maxLength={1000}
                      required
                    />
                  </label>
                )}
                <label className="grid gap-1 text-sm font-semibold text-ink">
                  사유
                  <textarea
                    value={actionReason}
                    onChange={(event) => setActionReason(event.target.value)}
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
                    data-testid="admin-incidents-action-submit"
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
                    onClick={() => setSelectedIncident(null)}
                    className="h-10 rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
                  >
                    취소
                  </button>
                </div>
              </form>
            </Section>
          )}
        </div>
      </div>
    </AdminPage>
  );
}
