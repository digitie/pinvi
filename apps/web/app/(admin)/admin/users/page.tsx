'use client';

import Link from 'next/link';
import { useState, type FormEvent } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type { AdminUserSummary } from '@pinvi/schemas';
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const STATUSES = [
  { value: '', label: '전체' },
  { value: 'pending_verification', label: '인증 대기' },
  { value: 'pending_profile', label: '프로필 대기' },
  { value: 'active', label: '활성' },
  { value: 'disabled', label: '비활성' },
];

const columns: AdminTableColumn<AdminUserSummary>[] = [
  {
    key: 'email',
    header: '이메일 (마스킹)',
    sortable: true,
    sortValue: (u) => u.email_masked,
    cell: (u) => (
      <Link href={`/admin/users/${u.user_id}`} className="text-primary underline">
        {u.email_masked}
      </Link>
    ),
  },
  {
    key: 'nickname',
    header: '닉네임',
    sortable: true,
    sortValue: (u) => u.nickname ?? '',
    cell: (u) => u.nickname ?? '—',
  },
  { key: 'status', header: '상태', sortable: true, sortValue: (u) => u.status, cell: (u) => u.status },
  {
    key: 'roles',
    header: '역할',
    cell: (u) => u.roles.join(', '),
  },
  {
    key: 'created_at',
    header: '가입',
    sortable: true,
    sortValue: (u) => new Date(u.created_at).getTime(),
    cell: (u) => new Date(u.created_at).toLocaleDateString('ko-KR'),
  },
];

export default function AdminUsersPage() {
  const [statusFilter, setStatusFilter] = useState('');
  const [queryInput, setQueryInput] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [page, setPage] = useState(1);

  const usersQuery = useQuery({
    queryKey: queryKeys.admin.users({ page, status: statusFilter, q: submittedQuery }),
    queryFn: () =>
      adminApi(apiClient).listUsers({
        page,
        limit: 50,
        status: statusFilter || undefined,
        q: submittedQuery || undefined,
      }),
    placeholderData: keepPreviousData,
  });

  const data = usersQuery.data ?? null;
  const error = usersQuery.isError
    ? usersQuery.error instanceof ApiError
      ? usersQuery.error.message
      : '조회 실패'
    : null;

  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / 50));

  const onSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmittedQuery(queryInput.trim());
    setPage(1);
  };

  return (
    <AdminPage title="사용자" description="운영 계정 조회와 상태 관리">
      <FilterBar>
        <form onSubmit={onSearch} className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <label htmlFor="admin-users-search" className="text-xs text-muted">
            검색
          </label>
          <input
            id="admin-users-search"
            type="search"
            value={queryInput}
            onChange={(e) => setQueryInput(e.target.value)}
            className="min-w-48 rounded-sm border border-hairline px-2 py-1 text-sm"
            placeholder="이메일, 닉네임, user_id"
            data-testid="admin-users-search"
          />
          <button
            type="submit"
            className="rounded-sm border border-hairline px-3 py-1 text-sm"
            data-testid="admin-users-search-submit"
          >
            조회
          </button>
        </form>
        <label htmlFor="admin-users-status-filter" className="text-xs text-muted">상태</label>
        <select
          id="admin-users-status-filter"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="rounded-sm border border-hairline px-2 py-1 text-sm"
          data-testid="admin-users-status-filter"
        >
          {STATUSES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <span className="ml-auto text-xs text-muted">총 {total}명</span>
      </FilterBar>

      {error && (
        <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text" data-testid="admin-users-error">
          {error}
        </p>
      )}

      <AdminTable
        columns={columns}
        rows={data?.items ?? []}
        loading={usersQuery.isLoading}
        rowKey={(u) => u.user_id}
        rowTestId={(u) => `admin-users-row-${u.user_id}`}
      />

      <div className="flex items-center justify-between text-sm">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          className="rounded-sm border border-hairline px-3 py-1 disabled:opacity-50"
        >
          이전
        </button>
        <span className="text-muted">
          {page} / {totalPages}
        </span>
        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => setPage((p) => p + 1)}
          className="rounded-sm border border-hairline px-3 py-1 disabled:opacity-50"
        >
          다음
        </button>
      </div>
    </AdminPage>
  );
}
