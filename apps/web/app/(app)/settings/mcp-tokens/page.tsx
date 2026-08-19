'use client';

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Copy, KeyRound, Trash2 } from 'lucide-react';
import { ApiError, userApi } from '@pinvi/api-client';
import type { McpToken } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { SettingsList, SettingsSection } from '@/components/app/SettingsSurface';
import { FormField } from '@/components/forms/FormField';
import { FormSelect } from '@/components/forms/FormSelect';
import { buttonClassName } from '@/components/ui/Button';

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

  const onCopy = async () => {
    if (!issued || !navigator.clipboard) return;
    await navigator.clipboard.writeText(issued);
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-ink">MCP 토큰</h1>
      </header>

      {error && (
        <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">
          {error}
        </p>
      )}

      <SettingsSection title="새 토큰">
        <form
          onSubmit={onIssue}
          className="grid items-start gap-3 md:grid-cols-[minmax(0,1fr)_140px_auto]"
        >
          <FormField
            id="settings-mcp-name"
            label="토큰 이름"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            minLength={1}
            maxLength={120}
            data-testid="settings-mcp-name"
          />
          <FormSelect
            id="settings-mcp-expiry"
            label="만료"
            value={expiry}
            onChange={(e) => setExpiry(e.target.value as (typeof EXPIRY_OPTIONS)[number]['value'])}
          >
            {EXPIRY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </FormSelect>
          <button
            type="submit"
            disabled={saving}
            className={buttonClassName({ className: 'mt-7' })}
          >
            <KeyRound className="h-4 w-4" aria-hidden="true" />
            {saving ? '발급 중…' : '발급'}
          </button>
        </form>
      </SettingsSection>

      {issued && (
        <SettingsSection title="발급 원문">
          <div className="flex min-w-0 items-end gap-2">
            <FormField
              id="settings-mcp-issued"
              label="발급된 MCP 토큰"
              readOnly
              value={issued}
              className="min-w-0 flex-1 font-mono text-xs"
              data-testid="settings-mcp-issued"
            />
            <button
              type="button"
              onClick={onCopy}
              title="복사"
              aria-label="토큰 복사"
              className="inline-flex size-11 shrink-0 items-center justify-center rounded-sm border border-hairline"
            >
              <Copy className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </SettingsSection>
      )}

      <SettingsSection title="토큰 목록">
        <SettingsList
          items={tokens}
          loading={loading}
          aria-label="MCP 토큰 목록"
          rowKey={(t) => t.token_id}
          empty="발급한 토큰이 없습니다. 위에서 이름을 입력해 새 토큰을 만들 수 있습니다."
          renderRow={(t) => (
            <>
              <p className="text-base font-semibold text-ink">{t.name}</p>
              <p className="mt-1 font-mono text-sm text-muted">{t.masked_token}</p>
              <p className="mt-1 text-sm text-muted">
                {tokenStatus(t)} · 만료{' '}
                {t.expires_at ? new Date(t.expires_at).toLocaleString('ko-KR') : '무기한'} · 마지막
                사용 {t.last_used_at ? new Date(t.last_used_at).toLocaleString('ko-KR') : '—'}
              </p>
            </>
          )}
          renderActions={(t) => (
            <button
              type="button"
              title="회수"
              aria-label={`${t.name} 토큰 회수`}
              disabled={Boolean(t.revoked_at)}
              onClick={() => void onRevoke(t.token_id)}
              className="focus-ring inline-flex size-11 items-center justify-center rounded-sm text-error-text hover:bg-error-bg disabled:opacity-40"
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
        />
      </SettingsSection>
    </div>
  );
}
