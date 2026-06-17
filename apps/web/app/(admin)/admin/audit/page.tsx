'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type { AdminAuditEntry, AdminChainVerify } from '@pinvi/schemas';
import { AdminPage, Section } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const columns: AdminTableColumn<AdminAuditEntry>[] = [
  {
    key: 'log_id',
    header: '#',
    width: '80px',
    sortable: true,
    sortValue: (r) => r.log_id,
    cell: (r) => r.log_id,
  },
  { key: 'action', header: 'Action', sortable: true, sortValue: (r) => r.action, cell: (r) => r.action },
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
    sortable: true,
    sortValue: (r) => new Date(r.occurred_at).getTime(),
    cell: (r) => new Date(r.occurred_at).toLocaleString('ko-KR'),
  },
];

export default function AdminAuditPage() {
  const [verify, setVerify] = useState<AdminChainVerify | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  const auditQuery = useQuery({
    queryKey: queryKeys.admin.audit({ limit: 100 }),
    queryFn: () => adminApi(apiClient).listAudit(100),
  });

  const rows = auditQuery.data ?? [];
  const listError = auditQuery.isError
    ? auditQuery.error instanceof ApiError
      ? auditQuery.error.message
      : '조회 실패'
    : null;
  const error = verifyError ?? listError;

  const onVerify = async () => {
    setVerifying(true);
    setVerifyError(null);
    try {
      const res = await adminApi(apiClient).verifyChain();
      setVerify(res);
    } catch (err) {
      setVerifyError(err instanceof ApiError ? err.message : '검증 실패');
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

      <AdminTable
        columns={columns}
        rows={rows}
        loading={auditQuery.isLoading}
        rowKey={(r) => String(r.log_id)}
        rowTestId={(r) => `admin-audit-row-${r.log_id}`}
        virtualized
        maxHeight="70vh"
      />
    </AdminPage>
  );
}
