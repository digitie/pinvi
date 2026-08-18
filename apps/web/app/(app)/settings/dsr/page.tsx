'use client';

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { ClipboardCheck, Loader2, RefreshCw, Send, XCircle } from 'lucide-react';
import { ApiError, userApi } from '@pinvi/api-client';
import type { DsrRequestRecord, DsrRequestType } from '@pinvi/schemas';
import { SettingsList, SettingsSection } from '@/components/app/SettingsSurface';
import { FormField } from '@/components/forms/FormField';
import { FormSelect } from '@/components/forms/FormSelect';
import { FormTextArea } from '@/components/forms/FormTextArea';
import { buttonClassName } from '@/components/ui/Button';
import { apiClient } from '@/lib/api';

const REQUEST_TYPE_OPTIONS: { value: DsrRequestType; label: string }[] = [
  { value: 'access', label: '열람' },
  { value: 'correction', label: '정정' },
  { value: 'delete', label: '삭제' },
  { value: 'suspend', label: '처리정지' },
];

const OPEN_STATUSES = new Set(['received', 'identity_check', 'processing']);

/**
 * 요청 대상 범위 — 서버 스키마(`request_details`)는 자유형 record라 프런트가 계약을 정한다.
 * 예약 키 `withdrawal`/`processing`은 서버가 같은 bag에 병합하므로 여기서 절대 쓰지 않는다.
 */
const DSR_SCOPES: { value: string; label: string }[] = [
  { value: 'profile', label: '프로필 정보' },
  { value: 'location_audit', label: '위치 접근 로그' },
  { value: 'trips', label: '여행 기록' },
  { value: 'attachments', label: '첨부 파일' },
  { value: 'all', label: '전체' },
];

/** 빈 값은 넣지 않는다 — 서버가 키 유무로 범위를 판단한다. */
export function buildDsrRequestDetails(input: {
  scope: string;
  periodFrom: string;
  periodTo: string;
  note: string;
}): Record<string, unknown> {
  return {
    scope: input.scope,
    ...(input.periodFrom ? { period_from: input.periodFrom } : {}),
    ...(input.periodTo ? { period_to: input.periodTo } : {}),
    ...(input.note.trim() ? { note: input.note.trim() } : {}),
  };
}

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('ko-KR') : '-';
}

export default function DsrSettingsPage() {
  const [requests, setRequests] = useState<DsrRequestRecord[]>([]);
  const [requestType, setRequestType] = useState<DsrRequestType>('access');
  const [summary, setSummary] = useState('');
  const [scope, setScope] = useState('profile');
  const [periodFrom, setPeriodFrom] = useState('');
  const [periodTo, setPeriodTo] = useState('');
  const [note, setNote] = useState('');
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
        request_details: buildDsrRequestDetails({ scope, periodFrom, periodTo, note }),
      });
      setNotice(`${created.request_id} 요청을 접수했습니다.`);
      setSummary('');
      setScope('profile');
      setPeriodFrom('');
      setPeriodTo('');
      setNote('');
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

      <SettingsSection title="새 요청">
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
          {/* raw JSON 입력을 일반 폼 필드로 — 사용자에게 JSON 문법을 요구하지 않는다(T-316). */}
          <FormSelect
            id="settings-dsr-scope"
            label="대상 범위"
            value={scope}
            onChange={(event) => setScope(event.target.value)}
            required
          >
            {DSR_SCOPES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </FormSelect>
          <div className="grid gap-3 sm:grid-cols-2 lg:col-span-2">
            <FormField
              id="settings-dsr-period-from"
              label="대상 기간 시작(선택)"
              type="date"
              value={periodFrom}
              onChange={(event) => setPeriodFrom(event.target.value)}
            />
            <FormField
              id="settings-dsr-period-to"
              label="대상 기간 종료(선택)"
              type="date"
              value={periodTo}
              onChange={(event) => setPeriodTo(event.target.value)}
            />
          </div>
          <div className="lg:col-span-2">
            <FormTextArea
              id="settings-dsr-note"
              label="추가 설명(선택)"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              maxLength={1000}
              rows={3}
            />
          </div>
          <button
            type="submit"
            disabled={saving}
            className={buttonClassName({ className: 'lg:col-start-2 lg:justify-self-start' })}
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
      </SettingsSection>

      <SettingsSection title="요청 목록">
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
        <SettingsList
          items={requests}
          loading={loading}
          aria-label="DSR 요청 목록"
          rowKey={(row) => row.request_id}
          rowTestId={(row) => `settings-dsr-row-${row.request_id}`}
          empty="접수한 요청이 없습니다. 위 폼에서 열람·정정·삭제를 요청할 수 있습니다."
          renderRow={(row) => (
            <>
              <p className="text-base font-semibold text-ink">{row.request_summary}</p>
              <p className="mt-1 font-mono text-xs text-muted">{row.request_id}</p>
              <p className="mt-1 text-sm text-muted">
                {row.request_type} · {row.status} · 마감{' '}
                <span className={row.response_overdue ? 'text-error-text' : undefined}>
                  {formatDateTime(row.due_at)}
                </span>
              </p>
              {(row.result_summary ?? row.rejection_reason) && (
                <p className="mt-1 text-sm text-body">
                  {row.result_summary ?? row.rejection_reason}
                </p>
              )}
            </>
          )}
          renderActions={(row) =>
            OPEN_STATUSES.has(row.status) ? (
              <button
                type="button"
                title="철회"
                aria-label={`${row.request_id} 요청 철회`}
                disabled={pendingWithdraw === row.request_id}
                onClick={() => void onWithdraw(row.request_id)}
                className="focus-ring inline-flex size-11 items-center justify-center rounded-sm text-muted hover:bg-error-bg hover:text-error-text disabled:opacity-50"
              >
                {pendingWithdraw === row.request_id ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <XCircle className="h-4 w-4" aria-hidden="true" />
                )}
              </button>
            ) : null
          }
        />
      </SettingsSection>
    </div>
  );
}
