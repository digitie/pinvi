'use client';

import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Copy, KeyRound, Trash2 } from 'lucide-react';
import { ApiClient, ApiError, adminApi } from '@pinvi/api-client';
import type { McpToken } from '@pinvi/schemas';
import { AdminPage, FilterBar, Section } from '@/components/admin/AdminPage';
import { DataTable, type DataTableColumn } from '@/components/admin/DataTable';
import { FormField } from '@/components/forms/FormField';
import { FormSelect } from '@/components/forms/FormSelect';

type IssueFieldErrors = { userId?: string; reason?: string };

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12501',
});

const EXPIRY_OPTIONS = [
  { value: '30', label: '30일' },
  { value: '7', label: '7일' },
  { value: '90', label: '90일' },
  { value: 'never', label: '무기한' },
] as const;

function addDays(days: number): string {
  const expires = new Date();
  expires.setDate(expires.getDate() + days);
  return expires.toISOString();
}

function tokenStatus(token: McpToken): string {
  if (token.revoked_at) return 'revoked';
  if (token.expires_at && new Date(token.expires_at).getTime() <= Date.now()) return 'expired';
  return 'active';
}

export default function AdminMcpTokensPage() {
  const [tokens, setTokens] = useState<McpToken[]>([]);
  const [statusFilter, setStatusFilter] = useState<'active' | 'expired' | 'revoked' | ''>('active');
  const [query, setQuery] = useState('');
  const [userId, setUserId] = useState('');
  const [name, setName] = useState('관리자 대리 발급');
  const [expiry, setExpiry] = useState<(typeof EXPIRY_OPTIONS)[number]['value']>('30');
  const [reason, setReason] = useState('');
  const [revokeReason, setRevokeReason] = useState('');
  const [issued, setIssued] = useState<string | null>(null);
  const [issueErrors, setIssueErrors] = useState<IssueFieldErrors>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const userIdRef = useRef<HTMLInputElement>(null);
  const reasonRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setTokens(
        await adminApi(apiClient).listMcpTokens({
          status: statusFilter || undefined,
          q: query.trim() || undefined,
          limit: 100,
        }),
      );
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '조회 실패');
    } finally {
      setLoading(false);
    }
  }, [query, statusFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  const onSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void load();
  };

  const onIssue = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextErrors: IssueFieldErrors = {};
    if (!userId.trim()) nextErrors.userId = '대상 user_id를 입력하세요.';
    if (!reason.trim()) nextErrors.reason = '발급 사유를 입력하세요.';
    setIssueErrors(nextErrors);
    if (nextErrors.userId) {
      userIdRef.current?.focus();
      return;
    }
    if (nextErrors.reason) {
      reasonRef.current?.focus();
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const expires_at = expiry === 'never' ? null : addDays(Number(expiry));
      const created = await adminApi(apiClient).issueMcpToken({
        user_id: userId,
        name,
        expires_at,
        access_reason: reason,
      });
      setIssued(created.token);
      setTokens((prev) => [created, ...prev]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '발급 실패');
    } finally {
      setSaving(false);
    }
  };

  const onRevoke = useCallback(
    async (tokenId: string) => {
      if (!revokeReason.trim()) {
        setError('회수 사유를 입력하세요.');
        return;
      }
      setError(null);
      try {
        await adminApi(apiClient).revokeMcpToken(tokenId, { access_reason: revokeReason });
        await load();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : '회수 실패');
      }
    },
    [load, revokeReason],
  );

  const columns = useMemo<DataTableColumn<McpToken>[]>(
    () => [
      {
        key: 'user_id',
        header: 'User',
        cell: (t) => <span className="font-mono text-xs">{t.user_id ?? '—'}</span>,
      },
      { key: 'name', header: '이름', cell: (t) => t.name },
      {
        key: 'masked',
        header: '토큰',
        cell: (t) => <span className="font-mono">{t.masked_token}</span>,
      },
      { key: 'status', header: '상태', cell: (t) => tokenStatus(t) },
      {
        key: 'expires',
        header: '만료',
        cell: (t) => (t.expires_at ? new Date(t.expires_at).toLocaleString('ko-KR') : '무기한'),
      },
      {
        key: 'last_used',
        header: '마지막 사용',
        cell: (t) => (t.last_used_at ? new Date(t.last_used_at).toLocaleString('ko-KR') : '—'),
      },
      {
        key: 'actions',
        header: '',
        width: '64px',
        cell: (t) => (
          <button
            type="button"
            title="회수"
            aria-label={`${t.name} 토큰 회수`}
            disabled={Boolean(t.revoked_at)}
            onClick={() => void onRevoke(t.token_id)}
            className="inline-flex h-8 w-8 items-center justify-center rounded-sm border border-hairline text-error-text disabled:opacity-40"
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </button>
        ),
      },
    ],
    [onRevoke],
  );

  const onCopy = async () => {
    if (!issued || !navigator.clipboard) return;
    await navigator.clipboard.writeText(issued);
  };

  return (
    <AdminPage title="MCP 토큰" description="외부 agent read-only 토큰 관리">
      <FilterBar>
        <form onSubmit={onSearch} className="flex min-w-0 flex-1 flex-wrap items-end gap-2">
          <FormField
            id="admin-mcp-search"
            label="검색"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="이름 또는 token_id"
            className="min-w-64 px-2 py-1"
            data-testid="admin-mcp-search"
          />
          <button type="submit" className="h-9 rounded-sm border border-hairline px-3 text-sm">
            조회
          </button>
        </form>
        <FormSelect
          id="admin-mcp-status"
          label="상태"
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}
          className="px-2 py-1"
          data-testid="admin-mcp-status"
        >
          <option value="">전체</option>
          <option value="active">active</option>
          <option value="expired">expired</option>
          <option value="revoked">revoked</option>
        </FormSelect>
      </FilterBar>

      {error && (
        <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">
          {error}
        </p>
      )}

      <Section title="대리 발급">
        <form onSubmit={onIssue} className="grid items-start gap-3 lg:grid-cols-[1.2fr_1fr_120px_1.2fr_auto]">
          <FormField
            ref={userIdRef}
            id="admin-mcp-user"
            label="대상 user_id"
            type="text"
            value={userId}
            onChange={(event) => setUserId(event.target.value)}
            placeholder="user_id"
            error={issueErrors.userId}
            data-testid="admin-mcp-user"
          />
          <FormField
            id="admin-mcp-name"
            label="토큰 이름"
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            minLength={1}
            maxLength={120}
            data-testid="admin-mcp-name"
          />
          <FormSelect
            id="admin-mcp-expiry"
            label="만료"
            value={expiry}
            onChange={(event) =>
              setExpiry(event.target.value as (typeof EXPIRY_OPTIONS)[number]['value'])
            }
          >
            {EXPIRY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </FormSelect>
          <FormField
            ref={reasonRef}
            id="admin-mcp-reason"
            label="발급 사유"
            type="text"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="발급 사유"
            error={issueErrors.reason}
            data-testid="admin-mcp-reason"
          />
          <button
            type="submit"
            disabled={saving}
            className="mt-7 inline-flex h-9 items-center justify-center gap-2 rounded-sm bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50"
          >
            <KeyRound className="h-4 w-4" aria-hidden="true" />
            {saving ? '발급 중...' : '발급'}
          </button>
        </form>
      </Section>

      {issued && (
        <Section title="발급 원문">
          <div className="flex min-w-0 items-end gap-2">
            <FormField
              id="admin-mcp-issued"
              label="발급된 MCP 토큰"
              readOnly
              value={issued}
              className="min-w-0 flex-1 font-mono text-xs"
              data-testid="admin-mcp-issued"
            />
            <button
              type="button"
              onClick={onCopy}
              title="복사"
              aria-label="토큰 복사"
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-sm border border-hairline"
            >
              <Copy className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </Section>
      )}

      <Section title="회수 사유">
        <FormField
          id="admin-mcp-revoke-reason"
          label="회수 사유"
          type="text"
          value={revokeReason}
          onChange={(event) => setRevokeReason(event.target.value)}
          placeholder="토큰 유출 의심"
          data-testid="admin-mcp-revoke-reason"
        />
      </Section>

      <DataTable columns={columns} rows={tokens} loading={loading} rowKey={(t) => t.token_id} />
    </AdminPage>
  );
}
