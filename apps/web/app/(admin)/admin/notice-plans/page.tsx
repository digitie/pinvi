'use client';

import Link from 'next/link';
import { useMemo, useState, type FormEvent } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import {
  ApiClient,
  ApiError,
  adminApi,
  queryKeys,
  type AdminNoticePlanListParams,
} from '@pinvi/api-client';
import type { NoticePlan } from '@pinvi/schemas';
import { Edit3, Plus, RefreshCw, Search } from 'lucide-react';
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const inputClass = 'rounded-sm border border-hairline px-2 py-1 text-sm';

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleDateString('ko-KR') : '—';
}

export default function AdminNoticePlansPage() {
  const [q, setQ] = useState('');
  const [submittedQ, setSubmittedQ] = useState('');
  const [category, setCategory] = useState('');
  const [published, setPublished] = useState<'all' | 'true' | 'false'>('all');

  const params = useMemo<AdminNoticePlanListParams>(
    () => ({
      q: submittedQ || undefined,
      category: category || undefined,
      isPublished: published === 'all' ? undefined : published === 'true',
      limit: 100,
    }),
    [category, published, submittedQ],
  );

  const plansQuery = useQuery({
    queryKey: queryKeys.admin.noticePlans(params),
    queryFn: () => adminApi(apiClient).listNoticePlans(params),
    placeholderData: keepPreviousData,
  });

  const rows = plansQuery.data ?? [];
  const columns: AdminTableColumn<NoticePlan>[] = [
    {
      key: 'title',
      header: '제목',
      sortable: true,
      sortValue: (row) => row.title,
      cell: (row) => (
        <div>
          <div className="font-medium">{row.title}</div>
          <div className="font-mono text-xs text-muted">{row.slug}</div>
        </div>
      ),
    },
    {
      key: 'category',
      header: 'category',
      sortable: true,
      sortValue: (row) => row.category,
      cell: (row) => row.category,
    },
    {
      key: 'destination',
      header: '목적지',
      cell: (row) => row.destination ?? '—',
    },
    {
      key: 'published',
      header: '공개',
      sortable: true,
      sortValue: (row) => (row.is_published ? 1 : 0),
      cell: (row) => (row.is_published ? 'published' : 'draft'),
    },
    {
      key: 'period',
      header: '기간',
      cell: (row) => `${formatDate(row.starts_on)} - ${formatDate(row.ends_on)}`,
    },
    {
      key: 'action',
      header: '작업',
      cell: (row) => (
        <Link
          href={`/admin/notice-plans/${row.notice_plan_id}`}
          className="inline-flex h-8 items-center gap-1 rounded-sm border border-hairline px-2 text-xs font-semibold"
          data-testid={`admin-notice-edit-${row.notice_plan_id}`}
        >
          <Edit3 className="h-3.5 w-3.5" aria-hidden="true" />
          편집
        </Link>
      ),
    },
  ];

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmittedQ(q.trim());
  };

  return (
    <AdminPage
      title="추천 여행"
      description="Admin이 작성하거나 kor-travel-map에서 가져온 추천 여행을 관리합니다."
      actions={
        <Link
          href="/admin/notice-plans/new"
          className="inline-flex h-9 items-center gap-1 rounded-sm bg-primary px-3 text-sm font-semibold text-white"
          data-testid="admin-notice-new"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />새 추천 여행
        </Link>
      }
    >
      <form onSubmit={submit}>
        <FilterBar>
          <input
            value={q}
            onChange={(event) => setQ(event.target.value)}
            className={inputClass}
            placeholder="제목 / slug / 목적지"
            data-testid="admin-notice-search"
          />
          <input
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            className={inputClass}
            placeholder="category"
            data-testid="admin-notice-category-filter"
          />
          <select
            value={published}
            onChange={(event) => setPublished(event.target.value as typeof published)}
            className={inputClass}
            data-testid="admin-notice-published-filter"
          >
            <option value="all">전체</option>
            <option value="true">공개</option>
            <option value="false">초안</option>
          </select>
          <button
            type="submit"
            className="inline-flex h-8 items-center gap-1 rounded-sm border border-hairline px-3 text-sm font-semibold"
            data-testid="admin-notice-submit"
          >
            <Search className="h-4 w-4" aria-hidden="true" />
            검색
          </button>
          <button
            type="button"
            onClick={() => void plansQuery.refetch()}
            className="inline-flex h-8 items-center gap-1 rounded-sm border border-hairline px-3 text-sm font-semibold"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            새로고침
          </button>
        </FilterBar>
      </form>

      {plansQuery.isError && (
        <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text">
          {plansQuery.error instanceof ApiError
            ? plansQuery.error.message
            : '추천 여행 목록을 불러오지 못했습니다.'}
        </p>
      )}

      <AdminTable
        rows={rows}
        columns={columns}
        rowKey={(row) => row.notice_plan_id}
        loading={plansQuery.isLoading}
        empty="추천 여행이 없습니다."
        rowTestId={(row) => `admin-notice-row-${row.notice_plan_id}`}
      />
    </AdminPage>
  );
}
