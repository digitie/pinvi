'use client';

import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { Copy, KeyRound, Trash2 } from 'lucide-react';
import { ApiError, userApi } from '@tripmate/api-client';
import type { McpToken } from '@tripmate/schemas';
import { apiClient } from '@/lib/api';
import { Section } from '@/components/admin/AdminPage';
import { DataTable, type DataTableColumn } from '@/components/admin/DataTable';

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

export default function McpTokensSettingsPage() {
  const [tokens, setTokens] = useState<McpToken[]>([]);
  const [name, setName] = useState('Claude Desktop');
  const [expiry, setExpiry] = useState<(typeof EXPIRY_OPTIONS)[number]['value']>('30');
  const [issued, setIssued] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setTokens(await userApi(apiClient).listMcpTokens());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '조회 실패');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onIssue = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const body =
        expiry === 'never'
          ? { name, expires_at: null }
          : { name, expires_at: addDays(Number(expiry)) };
      const created = await userApi(apiClient).issueMcpToken(body);
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
      setError(null);
      try {
        await userApi(apiClient).revokeMcpToken(tokenId);
        await load();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : '회수 실패');
      }
    },
    [load],
  );

  const columns = useMemo<DataTableColumn<McpToken>[]>(
    () => [
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
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-ink">MCP 토큰</h1>
      </header>

      {error && <p className="rounded-sm bg-error-bg p-3 text-sm text-error-text">{error}</p>}

      <Section title="새 토큰">
        <form onSubmit={onIssue} className="grid gap-3 md:grid-cols-[minmax(0,1fr)_140px_auto]">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            minLength={1}
            maxLength={120}
            className="rounded-sm border border-hairline px-3 py-2 text-sm"
            aria-label="토큰 이름"
          />
          <select
            value={expiry}
            onChange={(e) => setExpiry(e.target.value as (typeof EXPIRY_OPTIONS)[number]['value'])}
            className="rounded-sm border border-hairline px-3 py-2 text-sm"
            aria-label="만료"
          >
            {EXPIRY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center justify-center gap-2 rounded-sm bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            <KeyRound className="h-4 w-4" aria-hidden="true" />
            {saving ? '발급 중...' : '발급'}
          </button>
        </form>
      </Section>

      {issued && (
        <Section title="발급 원문">
          <div className="flex min-w-0 gap-2">
            <input
              readOnly
              value={issued}
              className="min-w-0 flex-1 rounded-sm border border-hairline px-3 py-2 font-mono text-xs"
              aria-label="발급된 MCP 토큰"
            />
            <button
              type="button"
              onClick={onCopy}
              title="복사"
              aria-label="토큰 복사"
              className="inline-flex h-10 w-10 items-center justify-center rounded-sm border border-hairline"
            >
              <Copy className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </Section>
      )}

      <Section title="토큰 목록">
        <DataTable
          columns={columns}
          rows={tokens}
          loading={loading}
          rowKey={(token) => token.token_id}
        />
      </Section>
    </div>
  );
}
