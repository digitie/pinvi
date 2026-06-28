'use client';

import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { Gavel, Loader2, RefreshCw, RotateCcw, Send } from 'lucide-react';
import { ApiError, userApi } from '@pinvi/api-client';
import type {
  ContentReportReasonCode,
  ContentReportRecord,
  ContentReportTargetType,
} from '@pinvi/schemas';
import { Section } from '@/components/admin/AdminPage';
import { DataTable, type DataTableColumn } from '@/components/admin/DataTable';
import { FormField } from '@/components/forms/FormField';
import { FormSelect } from '@/components/forms/FormSelect';
import { apiClient } from '@/lib/api';

const TARGET_OPTIONS: { value: ContentReportTargetType; label: string }[] = [
  { value: 'trip', label: '여행' },
  { value: 'comment', label: '댓글' },
  { value: 'attachment', label: '첨부' },
  { value: 'share_link', label: '공유 링크' },
];

const REASON_OPTIONS: { value: ContentReportReasonCode; label: string }[] = [
  { value: 'spam', label: '스팸' },
  { value: 'harassment', label: '괴롭힘' },
  { value: 'privacy', label: '개인정보' },
  { value: 'illegal', label: '불법 콘텐츠' },
  { value: 'safety', label: '안전 위험' },
  { value: 'other', label: '기타' },
];

const APPEALABLE = new Set(['hidden', 'taken_down', 'rejected']);
const textareaClass =
  'min-h-24 rounded-sm border border-hairline px-3 py-2 text-sm outline-none focus:border-primary';

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('ko-KR') : '-';
}

function parseJsonObject(value: string): Record<string, unknown> {
  const parsed = JSON.parse(value) as unknown;
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('증빙 정보는 JSON object여야 합니다.');
  }
  return parsed as Record<string, unknown>;
}

export default function ModerationSettingsPage() {
  const [reports, setReports] = useState<ContentReportRecord[]>([]);
  const [targetType, setTargetType] = useState<ContentReportTargetType>('trip');
  const [targetId, setTargetId] = useState('');
  const [reasonCode, setReasonCode] = useState<ContentReportReasonCode>('privacy');
  const [reasonText, setReasonText] = useState('');
  const [evidence, setEvidence] = useState('{}');
  const [appealReportId, setAppealReportId] = useState<string | null>(null);
  const [appealReason, setAppealReason] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [appealing, setAppealing] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await userApi(apiClient).listContentReports(100);
      setReports(result.items);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '신고 목록을 불러오지 못했습니다.');
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
      const created = await userApi(apiClient).createContentReport({
        target_type: targetType,
        target_id: targetId.trim(),
        reason_code: reasonCode,
        reason_text: reasonText.trim(),
        evidence: parseJsonObject(evidence),
      });
      setNotice(`${created.report_id} 신고를 접수했습니다.`);
      setTargetId('');
      setReasonText('');
      setEvidence('{}');
      await load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : '신고 실패',
      );
    } finally {
      setSaving(false);
    }
  };

  const onAppeal = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!appealReportId) return;
    setAppealing(true);
    setNotice(null);
    setError(null);
    try {
      const appealed = await userApi(apiClient).appealContentReport(appealReportId, {
        appeal_reason: appealReason.trim(),
      });
      setNotice(`${appealed.report_id} 신고에 이의제기를 제출했습니다.`);
      setAppealReportId(null);
      setAppealReason('');
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '이의제기 실패');
    } finally {
      setAppealing(false);
    }
  };

  const columns = useMemo<DataTableColumn<ContentReportRecord>[]>(
    () => [
      {
        key: 'target',
        header: '대상',
        cell: (row) => (
          <div>
            <div className="font-mono text-xs">{row.target_id}</div>
            <div className="text-xs text-muted">{row.target_type}</div>
          </div>
        ),
      },
      { key: 'reason', header: '사유', cell: (row) => row.reason_code },
      { key: 'status', header: '상태', cell: (row) => row.status },
      { key: 'created', header: '접수', cell: (row) => formatDateTime(row.created_at) },
      {
        key: 'summary',
        header: '처리',
        cell: (row) => row.resolution_summary ?? row.appeal_summary ?? '-',
      },
      {
        key: 'actions',
        header: '',
        width: '80px',
        cell: (row) =>
          APPEALABLE.has(row.status) ? (
            <button
              type="button"
              title="이의제기"
              aria-label={`${row.report_id} 신고 이의제기`}
              onClick={() => {
                setAppealReportId(row.report_id);
                setAppealReason(row.appeal_summary ?? '');
              }}
              className="inline-flex h-8 w-8 items-center justify-center rounded-sm border border-hairline text-ink hover:bg-surface-soft"
            >
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
            </button>
          ) : (
            '-'
          ),
      },
    ],
    [],
  );

  return (
    <div className="space-y-6">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-ink">
          <Gavel className="h-6 w-6 text-primary" aria-hidden="true" />
          신고/이의제기
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

      <Section title="새 신고">
        <form onSubmit={onCreate} className="grid gap-3 lg:grid-cols-[180px_minmax(0,1fr)]">
          <FormSelect
            id="settings-moderation-target-type"
            label="대상"
            value={targetType}
            onChange={(event) => setTargetType(event.target.value as ContentReportTargetType)}
          >
            {TARGET_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </FormSelect>
          <FormField
            id="settings-moderation-target-id"
            label="대상 ID"
            type="text"
            value={targetId}
            onChange={(event) => setTargetId(event.target.value)}
            required
          />
          <FormSelect
            id="settings-moderation-reason"
            label="사유"
            value={reasonCode}
            onChange={(event) => setReasonCode(event.target.value as ContentReportReasonCode)}
          >
            {REASON_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </FormSelect>
          <label className="grid gap-1 text-sm font-semibold text-ink">
            신고 내용
            <textarea
              value={reasonText}
              onChange={(event) => setReasonText(event.target.value)}
              className={textareaClass}
              maxLength={2000}
              required
            />
          </label>
          <label className="grid gap-1 text-sm font-semibold text-ink lg:col-span-2">
            증빙 정보
            <textarea
              value={evidence}
              onChange={(event) => setEvidence(event.target.value)}
              className={textareaClass}
              required
            />
          </label>
          <button
            type="submit"
            disabled={saving}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-sm bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50 lg:col-start-2 lg:justify-self-start"
            data-testid="settings-moderation-submit"
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

      {appealReportId && (
        <Section title="이의제기">
          <form onSubmit={onAppeal} className="grid gap-3">
            <div className="font-mono text-xs text-muted">{appealReportId}</div>
            <label className="grid gap-1 text-sm font-semibold text-ink">
              이의제기 사유
              <textarea
                value={appealReason}
                onChange={(event) => setAppealReason(event.target.value)}
                className={textareaClass}
                maxLength={2000}
                required
              />
            </label>
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={appealing}
                className="inline-flex h-10 items-center justify-center gap-2 rounded-sm bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50"
                data-testid="settings-moderation-appeal-submit"
              >
                {appealing ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <RotateCcw className="h-4 w-4" aria-hidden="true" />
                )}
                제출
              </button>
              <button
                type="button"
                onClick={() => setAppealReportId(null)}
                className="h-10 rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
              >
                취소
              </button>
            </div>
          </form>
        </Section>
      )}

      <Section title="신고 목록">
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
          rows={reports}
          loading={loading}
          rowKey={(row) => row.report_id}
          rowTestId={(row) => `settings-moderation-row-${row.report_id}`}
        />
      </Section>
    </div>
  );
}
