'use client';

import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { ClipboardCheck, Loader2, RefreshCw, Send, XCircle } from 'lucide-react';
import { ApiError, userApi } from '@pinvi/api-client';
import type { DsrRequestRecord, DsrRequestType } from '@pinvi/schemas';
import { Section } from '@/components/admin/AdminPage';
import { DataTable, type DataTableColumn } from '@/components/admin/DataTable';
import { FormField } from '@/components/forms/FormField';
import { FormSelect } from '@/components/forms/FormSelect';
import { apiClient } from '@/lib/api';

const REQUEST_TYPE_OPTIONS: { value: DsrRequestType; label: string }[] = [
  { value: 'access', label: '열람' },
  { value: 'correction', label: '정정' },
  { value: 'delete', label: '삭제' },
  { value: 'suspend', label: '처리정지' },
];

const OPEN_STATUSES = new Set(['received', 'identity_check', 'processing']);
const textareaClass =
  'min-h-24 rounded-sm border border-hairline px-3 py-2 text-sm outline-none focus:border-primary';

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('ko-KR') : '-';
}

function parseJsonObject(value: string): Record<string, unknown> {
  const parsed = JSON.parse(value) as unknown;
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('상세 내용은 JSON object여야 합니다.');
  }
  return parsed as Record<string, unknown>;
}

export default function DsrSettingsPage() {
  const [requests, setRequests] = useState<DsrRequestRecord[]>([]);
  const [requestType, setRequestType] = useState<DsrRequestType>('access');
  const [summary, setSummary] = useState('');
  const [details, setDetails] = useState('{"scope":"profile"}');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [pendingWithdraw, setPendingWithdraw] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await userApi(apiClient).listDsrRequests(100);
      setRequests(result.items);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'DSR 요청을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setNotice(null);
    setError(null);
    try {
      const created = await userApi(apiClient).createDsrRequest({
        request_type: requestType,
        request_summary: summary.trim(),
        request_details: parseJsonObject(details),
      });
      setNotice(`${created.request_id} 요청을 접수했습니다.`);
      setSummary('');
      setDetails('{"scope":"profile"}');
      await load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : '접수 실패',
      );
    } finally {
      setSaving(false);
    }
  };

  const onWithdraw = useCallback(
    async (requestId: string) => {
      setPendingWithdraw(requestId);
      setNotice(null);
      setError(null);
      try {
        await userApi(apiClient).withdrawDsrRequest(requestId, {
          reason: '사용자 self-service 철회',
        });
        setNotice(`${requestId} 요청을 철회했습니다.`);
        await load();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : '철회 실패');
      } finally {
        setPendingWithdraw(null);
      }
    },
    [load],
  );

  const columns = useMemo<DataTableColumn<DsrRequestRecord>[]>(
    () => [
      {
        key: 'request',
        header: '요청',
        cell: (row) => (
          <div>
            <div className="font-mono text-xs">{row.request_id}</div>
            <div className="max-w-xl truncate text-xs text-muted">{row.request_summary}</div>
          </div>
        ),
      },
      { key: 'type', header: '유형', cell: (row) => row.request_type },
      { key: 'status', header: '상태', cell: (row) => row.status },
      {
        key: 'due',
        header: '마감',
        cell: (row) => (
          <span className={row.response_overdue ? 'text-error-text' : undefined}>
            {formatDateTime(row.due_at)}
          </span>
        ),
      },
      {
        key: 'result',
        header: '결과',
        cell: (row) => row.result_summary ?? row.rejection_reason ?? '-',
      },
      {
        key: 'actions',
        header: '',
        width: '80px',
        cell: (row) =>
          OPEN_STATUSES.has(row.status) ? (
            <button
              type="button"
              title="철회"
              aria-label={`${row.request_id} 요청 철회`}
              disabled={pendingWithdraw === row.request_id}
              onClick={() => void onWithdraw(row.request_id)}
              className="inline-flex h-8 w-8 items-center justify-center rounded-sm border border-hairline text-error-text disabled:opacity-40"
            >
              {pendingWithdraw === row.request_id ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <XCircle className="h-4 w-4" aria-hidden="true" />
              )}
            </button>
          ) : (
            '-'
          ),
      },
    ],
    [onWithdraw, pendingWithdraw],
  );

  return (
    <div className="space-y-6">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-ink">
          <ClipboardCheck className="h-6 w-6 text-primary" aria-hidden="true" />
          개인정보 요청
        </h1>
      </header>

      {notice && (
        <p className="rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text">{notice}</p>
      )}
      {error && (
        <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">
          {error}
        </p>
      )}

      <Section title="새 요청">
        <form onSubmit={onCreate} className="grid gap-3 lg:grid-cols-[180px_minmax(0,1fr)]">
          <FormSelect
            id="settings-dsr-type"
            label="유형"
            value={requestType}
            onChange={(event) => setRequestType(event.target.value as DsrRequestType)}
          >
            {REQUEST_TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </FormSelect>
          <FormField
            id="settings-dsr-summary"
            label="요약"
            type="text"
            value={summary}
            onChange={(event) => setSummary(event.target.value)}
            minLength={1}
            maxLength={500}
            required
          />
          <label className="grid gap-1 text-sm font-semibold text-ink lg:col-span-2">
            상세 내용
            <textarea
              value={details}
              onChange={(event) => setDetails(event.target.value)}
              className={textareaClass}
              required
            />
          </label>
          <button
            type="submit"
            disabled={saving}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-sm bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50 lg:col-start-2 lg:justify-self-start"
            data-testid="settings-dsr-submit"
          >
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Send className="h-4 w-4" aria-hidden="true" />
            )}
            접수
          </button>
        </form>
      </Section>

      <Section title="요청 목록">
        <div className="mb-3 flex justify-end">
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="inline-flex h-9 items-center gap-2 rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
            )}
            새로고침
          </button>
        </div>
        <DataTable
          columns={columns}
          rows={requests}
          loading={loading}
          rowKey={(row) => row.request_id}
          rowTestId={(row) => `settings-dsr-row-${row.request_id}`}
        />
      </Section>
    </div>
  );
}
