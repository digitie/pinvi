'use client';

import Link from 'next/link';
import { useState, type FormEvent } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type { AdminUserSummary } from '@pinvi/schemas';
import { AdminPage } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { FilterActions, FilterBar, FilterField } from '@/components/admin/filter-bar';
import { Button } from '@/components/admin/ui/button';
import { Input } from '@/components/admin/ui/input';
import { NativeSelect } from '@/components/admin/ui/native-select';
import { NativeSelectOption } from '@/components/admin/ui/native-select-option';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const STATUSES = [
  { value: '', label: '전체' },
  { value: 'pending_verification', label: '인증 대기' },
  { value: 'pending_profile', label: '프로필 대기' },
  { value: 'active', label: '활성' },
  { value: 'disabled', label: '비활성' },
  { value: 'pending_delete', label: '삭제 대기' },
  { value: 'deleted', label: '삭제 완료' },
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
  {
    key: 'status',
    header: '상태',
    sortable: true,
    sortValue: (u) => u.status,
    cell: (u) => u.status,
  },
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
        {/* 검색만 제출로 적용된다(전환 전과 동일) — 상태 select는 form 밖에 두어 select 위
            Enter가 폼을 제출하지 않게 한다. form 자신이 툴바 행의 flex 아이템이라
            FilterBar와 같은 `items-end`/gap으로 안쪽 필드를 정렬한다. */}
        <form onSubmit={onSearch} className="flex min-w-0 flex-wrap items-end gap-x-3 gap-y-2">
          <FilterField className="w-56" htmlFor="admin-users-search" label="검색">
            <Input
              id="admin-users-search"
              type="search"
              value={queryInput}
              onChange={(e) => setQueryInput(e.target.value)}
              placeholder="이메일, 닉네임, user_id"
              data-testid="admin-users-search"
            />
          </FilterField>
          <FilterActions>
            <Button type="submit" variant="outline" data-testid="admin-users-search-submit">
              조회
            </Button>
          </FilterActions>
        </form>
        <FilterField htmlFor="admin-users-status-filter" label="상태">
          <NativeSelect
            id="admin-users-status-filter"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            data-testid="admin-users-status-filter"
          >
            {STATUSES.map((s) => (
              <NativeSelectOption key={s.value} value={s.value}>
                {s.label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </FilterField>
        <span className="ml-auto text-xs text-muted">총 {total}명</span>
      </FilterBar>

      {error && (
        <p
          role="alert"
          className="rounded-sm bg-error-bg p-3 text-sm text-error-text"
          data-testid="admin-users-error"
        >
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
