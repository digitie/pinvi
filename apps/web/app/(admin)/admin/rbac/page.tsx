'use client';

import { useQuery } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type { AdminPermissionMatrixEntry } from '@pinvi/schemas';
import { AdminPage, Section } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const columns: AdminTableColumn<AdminPermissionMatrixEntry>[] = [
  {
    key: 'resource',
    header: 'Resource',
    sortable: true,
    sortValue: (row) => row.resource,
    cell: (row) => <span className="font-mono text-xs">{row.resource}</span>,
  },
  {
    key: 'action',
    header: 'Action',
    sortable: true,
    sortValue: (row) => row.action,
    cell: (row) => <span className="font-mono text-xs">{row.action}</span>,
  },
  {
    key: 'route',
    header: 'Route',
    cell: (row) => <span className="font-mono text-xs">{row.route}</span>,
  },
  {
    key: 'roles',
    header: 'Roles',
    cell: (row) => row.roles.join(', '),
  },
  {
    key: 'audit',
    header: 'Audit',
    cell: (row) => (row.audit_required ? '필수' : '없음'),
  },
  {
    key: 'reason',
    header: '사유',
    cell: (row) => (row.access_reason_required ? '필수' : '없음'),
  },
  {
    key: 'notes',
    header: '비고',
    cell: (row) => row.notes ?? '—',
  },
];

export default function AdminRbacPage() {
  const matrixQuery = useQuery({
    queryKey: queryKeys.admin.rbacPermissionMatrix(),
    queryFn: () => adminApi(apiClient).getRbacPermissionMatrix(),
  });

  const error = matrixQuery.isError
    ? matrixQuery.error instanceof ApiError
      ? matrixQuery.error.message
      : '조회 실패'
    : null;
  const matrix = matrixQuery.data ?? null;

  return (
    <AdminPage title="RBAC" description="역할별 Admin 권한 매트릭스">
      {error && (
        <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text">
          {error}
        </p>
      )}

      <Section title="역할">
        <div className="grid gap-2 md:grid-cols-4" data-testid="admin-rbac-roles">
          {Object.entries(matrix?.roles ?? {}).map(([role, description]) => (
            <div key={role} className="rounded-sm border border-hairline bg-white px-3 py-2">
              <p className="font-mono text-xs font-semibold text-ink">{role}</p>
              <p className="mt-1 text-xs text-muted">{description}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section title="권한 매트릭스">
        <AdminTable
          columns={columns}
          rows={matrix?.entries ?? []}
          loading={matrixQuery.isLoading}
          rowKey={(row) => `${row.resource}:${row.action}`}
          rowTestId={(row) => `admin-rbac-row-${row.resource}-${row.action}`}
          empty="권한 매트릭스가 없습니다."
        />
      </Section>
    </AdminPage>
  );
}
