'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ApiClient, ApiError, adminApi } from '@tripmate/api-client';
import type { AdminAuditEntry, AdminChainVerify } from '@tripmate/schemas';
import { AdminPage, Section } from '@/components/admin/AdminPage';
import { DataTable, type DataTableColumn } from '@/components/admin/DataTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_TRIPMATE_API_URL ?? 'http://localhost:12501',
});

const columns: DataTableColumn<AdminAuditEntry>[] = [
  { key: 'log_id', header: '#', cell: (r) => r.log_id, width: '80px' },
  { key: 'action', header: 'Action', cell: (r) => r.action },
  { key: 'resource', header: 'Resource', cell: (r) => `${r.resource_type}/${r.resource_id ?? '—'}` },
  { key: 'reason', header: '사유', cell: (r) => r.access_reason ?? '—' },
  {
    key: 'hash',
    header: 'hash[:8]',
    cell: (r) => (
      <span className="font-mono text-xs" title={r.content_hash}>
        {r.content_hash.slice(0, 8)}
      </span>
    ),
  },
  {
    key: 'occurred_at',
    header: '발생',
    cell: (r) => new Date(r.occurred_at).toLocaleString('ko-KR'),
  },
];

export default function AdminAuditPage() {
  const [rows, setRows] = useState<AdminAuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [verify, setVerify] = useState<AdminChainVerify | null>(null);
  const [verifying, setVerifying] = useState(false);

  useEffect(() => {
    let cancelled = false;
    adminApi(apiClient)
      .listAudit(100)
      .then((res) => !cancelled && setRows(res))
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : '조회 실패');
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const onVerify = async () => {
    setVerifying(true);
    setError(null);
    try {
      const res = await adminApi(apiClient).verifyChain();
      setVerify(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '검증 실패');
    } finally {
      setVerifying(false);
    }
  };

  return (
    <AdminPage
      title="감사 로그"
      description="admin_audit_log read-only — SHA-256 chain. CPO 권한이 있어야 검증 가능."
      actions={
        <>
          <Link
            href="/admin/audit/location"
            className="rounded-sm border border-hairline bg-white px-3 py-2 text-sm font-semibold text-ink"
          >
            위치 감사
          </Link>
          <button
            type="button"
            onClick={onVerify}
            disabled={verifying}
            className="rounded-sm border border-primary px-3 py-2 text-sm text-primary disabled:opacity-50"
            data-testid="admin-audit-verify"
          >
            {verifying ? '검증 중...' : 'chain 검증'}
          </button>
        </>
      }
    >
      {verify && (
        <Section title="chain 검증 결과">
          <p
            className={
              verify.valid
                ? 'text-sm text-success-text'
                : 'text-sm font-bold text-error-text'
            }
            data-testid="admin-audit-verify-result"
          >
            {verify.valid
              ? `OK — ${verify.rows_checked}건 검증 완료`
              : `BROKEN — log_id ${verify.broken_at} 에서 chain 깨짐 (${verify.rows_checked}건 검사)`}
          </p>
        </Section>
      )}

      {error && (
        <p className="rounded-sm bg-error-bg p-3 text-sm text-error-text">{error}</p>
      )}

      <DataTable columns={columns} rows={rows} loading={loading} rowKey={(r) => String(r.log_id)} />
    </AdminPage>
  );
}
