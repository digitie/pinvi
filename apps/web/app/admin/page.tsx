"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AdminApiError,
  fetchAdminDatasetRows,
  fetchAdminDatasets,
  fetchAdminMe,
  logoutAdmin,
  type AdminDatasetRow,
  type AdminJsonValue,
} from "./api";
import { getDagsterAdminUrl } from "./config";
import { queryKeys } from "../shared/query-keys";
import { useAdminDataBrowserStore } from "../shared/stores";

const dagsterAdminUrl = getDagsterAdminUrl();

export default function AdminDataBrowserPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const {
    applySearchAndFilter: applySearchAndFilterState,
    changeSort,
    datasetSearch,
    filterColumn,
    filterValue,
    initializeDatasetSelection,
    limit,
    page,
    search,
    selectDataset: selectDatasetState,
    selectedTable,
    setDatasetSearch,
    setFilterColumn,
    setFilterValue,
    setLimit,
    setPage,
    setSearch,
    setSortBy,
    setSortDir,
    sortBy,
    sortDir,
    submittedFilter,
    submittedSearch,
  } = useAdminDataBrowserStore();

  const adminMeQuery = useQuery({
    queryKey: queryKeys.admin.me(),
    queryFn: fetchAdminMe,
    retry: false,
  });
  const datasetsQuery = useQuery({
    queryKey: queryKeys.admin.datasets(),
    queryFn: fetchAdminDatasets,
    retry: false,
  });

  const user = adminMeQuery.data ?? null;
  const datasets = useMemo(
    () => datasetsQuery.data?.datasets ?? [],
    [datasetsQuery.data?.datasets],
  );
  const pageSizeOptions = datasetsQuery.data?.page_size_options ?? [50, 100, 200, 500];

  const rowsQueryInput = useMemo(
    () => ({
      page,
      limit,
      search: submittedSearch,
      sortBy,
      sortDir,
      filter: submittedFilter,
    }),
    [limit, page, sortBy, sortDir, submittedFilter, submittedSearch],
  );

  const rowsQuery = useQuery({
    queryKey: queryKeys.admin.datasetRows(selectedTable, rowsQueryInput),
    queryFn: () => fetchAdminDatasetRows(selectedTable, rowsQueryInput),
    enabled: Boolean(selectedTable),
    retry: false,
  });

  const logoutMutation = useMutation({
    mutationFn: logoutAdmin,
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: queryKeys.admin.root() });
      router.replace("/admin/login");
    },
  });

  const selectedDataset = useMemo(
    () => datasets.find((dataset) => dataset.table_name === selectedTable) ?? null,
    [datasets, selectedTable],
  );
  const rowsPayload = rowsQuery.data ?? null;
  const visibleDatasets = useMemo(() => {
    const normalized = datasetSearch.trim().toLowerCase();
    if (!normalized) {
      return datasets;
    }
    return datasets.filter((dataset) => dataset.table_name.toLowerCase().includes(normalized));
  }, [datasets, datasetSearch]);
  const displayColumns = rowsPayload?.columns ?? selectedDataset?.columns ?? [];
  const pageCount = rowsPayload ? Math.max(1, Math.ceil(rowsPayload.total / rowsPayload.limit)) : 1;

  useEffect(() => {
    if (datasetsQuery.data) {
      initializeDatasetSelection(
        datasetsQuery.data.datasets[0] ?? null,
        datasetsQuery.data.default_page_size,
      );
    }
  }, [datasetsQuery.data, initializeDatasetSelection]);

  useEffect(() => {
    if (
      isUnauthorized(adminMeQuery.error) ||
      isUnauthorized(datasetsQuery.error) ||
      isUnauthorized(rowsQuery.error)
    ) {
      router.replace("/admin/login");
    }
  }, [adminMeQuery.error, datasetsQuery.error, router, rowsQuery.error]);

  const isLoading = adminMeQuery.isPending || datasetsQuery.isPending;
  const isRowsLoading = rowsQuery.isFetching;
  const queryError = adminMeQuery.error ?? datasetsQuery.error ?? rowsQuery.error ?? logoutMutation.error;
  const errorMessage = queryError && !isUnauthorized(queryError) ? getErrorMessage(queryError) : null;

  function handleSearchAndFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    applySearchAndFilterState();
  }

  function handleLogout() {
    logoutMutation.mutate();
  }

  function selectDataset(tableName: string) {
    selectDatasetState(datasets.find((dataset) => dataset.table_name === tableName) ?? null);
  }

  if (isLoading) {
    return (
      <main className="flex min-h-svh items-center justify-center bg-stone-100 text-stone-950">
        <div className="rounded-md border border-stone-200 bg-white px-5 py-4 text-sm font-bold text-stone-700 shadow-sm">
          관리자 데이터를 불러오는 중
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-svh bg-stone-100 text-stone-950">
      <header className="border-b border-stone-200 bg-white">
        <div className="mx-auto flex max-w-[1720px] flex-col gap-4 px-4 py-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm font-black text-teal-800">TripMate Admin</p>
            <h1 className="mt-1 text-2xl font-black tracking-normal text-stone-950">
              ETL 데이터 브라우저
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link
              className="inline-flex h-10 items-center gap-2 rounded-md border border-stone-300 bg-white px-3 text-sm font-bold text-stone-800 transition hover:border-stone-500"
              href="/admin/users"
            >
              <UsersIcon />
              사용자
            </Link>
            <a
              className="inline-flex h-10 items-center gap-2 rounded-md border border-stone-300 bg-white px-3 text-sm font-bold text-stone-800 transition hover:border-stone-500"
              href={dagsterAdminUrl}
              rel="noreferrer"
              target="_blank"
            >
              <WorkflowIcon />
              Dagster
              <ExternalLinkIcon />
            </a>
            <span className="rounded-md border border-stone-200 bg-stone-50 px-3 py-2 text-sm font-semibold text-stone-700">
              {user?.email}
            </span>
            <button
              className="inline-flex h-10 items-center gap-2 rounded-md border border-stone-300 bg-white px-3 text-sm font-bold text-stone-800 transition hover:border-stone-500"
              type="button"
              onClick={() => void handleLogout()}
            >
              <LogoutIcon />
              로그아웃
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1720px] grid-cols-1 gap-4 px-4 py-4 sm:px-6 lg:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="min-h-[calc(100svh-120px)] border border-stone-200 bg-white">
          <div className="border-b border-stone-200 p-4">
            <label className="block text-sm font-black text-stone-800" htmlFor="dataset-search">
              데이터셋
            </label>
            <div className="mt-3 flex h-10 items-center gap-2 rounded-md border border-stone-300 px-3">
              <SearchIcon />
              <input
                id="dataset-search"
                className="min-w-0 flex-1 bg-transparent text-sm outline-none"
                value={datasetSearch}
                onChange={(event) => setDatasetSearch(event.target.value)}
                placeholder="테이블명 검색"
              />
            </div>
          </div>
          <div className="max-h-[calc(100svh-220px)] overflow-y-auto p-2">
            {visibleDatasets.map((dataset) => (
              <button
                className={`mb-1 flex w-full items-center justify-between gap-3 rounded-md px-3 py-3 text-left text-sm transition ${
                  dataset.table_name === selectedTable
                    ? "bg-teal-800 text-white"
                    : "text-stone-700 hover:bg-stone-100"
                }`}
                key={dataset.table_name}
                type="button"
                onClick={() => selectDataset(dataset.table_name)}
              >
                <span className="min-w-0 truncate font-bold">{dataset.table_name}</span>
                <span
                  className={`shrink-0 rounded px-2 py-1 text-xs font-black ${
                    dataset.table_name === selectedTable
                      ? "bg-white/15 text-white"
                      : "bg-stone-100 text-stone-500"
                  }`}
                >
                  {dataset.row_count.toLocaleString("ko-KR")}
                </span>
              </button>
            ))}
          </div>
        </aside>

        <section className="min-w-0 border border-stone-200 bg-white">
          <div className="border-b border-stone-200 p-4">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
              <div>
                <p className="text-xs font-black uppercase text-amber-700">selected table</p>
                <h2 className="mt-1 break-all text-xl font-black text-stone-950">
                  {selectedTable || "데이터셋 없음"}
                </h2>
                <p className="mt-1 text-sm text-stone-500">
                  {rowsPayload
                    ? `총 ${rowsPayload.total.toLocaleString("ko-KR")}건`
                    : "조회 가능한 행 정보를 준비 중입니다."}
                </p>
              </div>

              <form className="grid gap-2 md:grid-cols-[minmax(180px,1fr)_180px_minmax(160px,1fr)_88px]" onSubmit={handleSearchAndFilter}>
                <label className="block">
                  <span className="mb-1 block text-xs font-black text-stone-600">전체 검색</span>
                  <input
                    className="h-10 w-full rounded-md border border-stone-300 px-3 text-sm outline-none focus:border-teal-700 focus:ring-4 focus:ring-teal-700/10"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="문자 컬럼 검색"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-black text-stone-600">필터 컬럼</span>
                  <select
                    className="h-10 w-full rounded-md border border-stone-300 bg-white px-2 text-sm outline-none focus:border-teal-700 focus:ring-4 focus:ring-teal-700/10"
                    value={filterColumn}
                    onChange={(event) => setFilterColumn(event.target.value)}
                  >
                    {selectedDataset?.columns
                      .filter((column) => column.filterable)
                      .map((column) => (
                        <option key={column.name} value={column.name}>
                          {column.name}
                        </option>
                      ))}
                  </select>
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-black text-stone-600">필터 값</span>
                  <input
                    className="h-10 w-full rounded-md border border-stone-300 px-3 text-sm outline-none focus:border-teal-700 focus:ring-4 focus:ring-teal-700/10"
                    value={filterValue}
                    onChange={(event) => setFilterValue(event.target.value)}
                    placeholder="부분 일치"
                  />
                </label>
                <button
                  className="mt-5 inline-flex h-10 items-center justify-center gap-2 rounded-md bg-stone-950 px-3 text-sm font-black text-white transition hover:bg-stone-800"
                  type="submit"
                >
                  <SearchIcon />
                  조회
                </button>
              </form>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-2 text-sm font-bold text-stone-700">
                정렬
                <select
                  className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm outline-none"
                  value={sortBy}
                  onChange={(event) => {
                    setSortBy(event.target.value);
                  }}
                >
                  {selectedDataset?.columns
                    .filter((column) => column.sortable)
                    .map((column) => (
                      <option key={column.name} value={column.name}>
                        {column.name}
                      </option>
                    ))}
                </select>
              </label>
              <div className="inline-flex overflow-hidden rounded-md border border-stone-300">
                <button
                  className={`h-9 px-3 text-sm font-black ${
                    sortDir === "asc" ? "bg-teal-800 text-white" : "bg-white text-stone-700"
                  }`}
                  type="button"
                  onClick={() => {
                    setSortDir("asc");
                  }}
                >
                  오름차순
                </button>
                <button
                  className={`h-9 border-l border-stone-300 px-3 text-sm font-black ${
                    sortDir === "desc" ? "bg-teal-800 text-white" : "bg-white text-stone-700"
                  }`}
                  type="button"
                  onClick={() => {
                    setSortDir("desc");
                  }}
                >
                  내림차순
                </button>
              </div>
              <label className="flex items-center gap-2 text-sm font-bold text-stone-700">
                페이지
                <select
                  className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm outline-none"
                  value={limit}
                  onChange={(event) => {
                    setLimit(Number(event.target.value));
                  }}
                >
                  {pageSizeOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="inline-flex h-9 items-center gap-2 rounded-md border border-stone-300 bg-white px-3 text-sm font-bold text-stone-700 transition hover:border-stone-500"
                type="button"
                onClick={() => {
                  applySearchAndFilterState();
                  void queryClient.invalidateQueries({ queryKey: queryKeys.admin.datasetRowsRoot() });
                }}
              >
                <RefreshIcon />
                새로고침
              </button>
            </div>
          </div>

          {errorMessage ? (
            <div className="border-b border-red-200 bg-red-50 px-4 py-3 text-sm font-bold text-red-800">
              {errorMessage}
            </div>
          ) : null}

          <div className="min-h-[520px] overflow-auto">
            {isRowsLoading ? (
              <div className="flex h-[520px] items-center justify-center text-sm font-bold text-stone-500">
                행 데이터를 불러오는 중
              </div>
            ) : rowsPayload && rowsPayload.rows.length > 0 ? (
              <table className="min-w-full border-separate border-spacing-0 text-left text-sm">
                <thead className="sticky top-0 z-10 bg-stone-50">
                  <tr>
                    {displayColumns.map((column) => (
                      <th
                        className="whitespace-nowrap border-b border-r border-stone-200 px-3 py-2 text-xs font-black text-stone-600 last:border-r-0"
                        key={column.name}
                      >
                        <button
                          className={`inline-flex items-center gap-1 ${
                            column.sortable ? "text-stone-800 hover:text-teal-800" : "cursor-default"
                          }`}
                          type="button"
                          onClick={() => changeSort(column)}
                        >
                          {column.name}
                          {sortBy === column.name ? <SortIcon direction={sortDir} /> : null}
                        </button>
                        <span className="mt-1 block text-[11px] font-semibold text-stone-400">
                          {column.type}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rowsPayload.rows.map((row, rowIndex) => (
                    <tr className="odd:bg-white even:bg-stone-50/60" key={stableRowKey(row, rowIndex)}>
                      {displayColumns.map((column) => (
                        <td
                          className="max-w-[320px] border-b border-r border-stone-200 px-3 py-2 align-top text-stone-700 last:border-r-0"
                          key={column.name}
                        >
                          <span className="block max-h-28 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-5">
                            {formatCell(row[column.name])}
                          </span>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="flex h-[520px] flex-col items-center justify-center gap-2 px-4 text-center">
                <p className="text-base font-black text-stone-800">조회된 행이 없습니다.</p>
                <p className="max-w-md text-sm leading-6 text-stone-500">
                  검색어나 필터를 지우거나 다른 데이터셋을 선택해 확인할 수 있습니다.
                </p>
              </div>
            )}
          </div>

          <div className="flex flex-col gap-3 border-t border-stone-200 p-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm font-semibold text-stone-600">
              {rowsPayload
                ? `${rowsPayload.page.toLocaleString("ko-KR")} / ${pageCount.toLocaleString("ko-KR")} 페이지`
                : "페이지 정보 없음"}
            </p>
            <div className="flex items-center gap-2">
              <button
                className="inline-flex h-10 items-center gap-2 rounded-md border border-stone-300 bg-white px-3 text-sm font-bold text-stone-700 disabled:cursor-not-allowed disabled:opacity-40"
                type="button"
                disabled={page <= 1 || isRowsLoading}
                onClick={() => setPage(Math.max(1, page - 1))}
              >
                <ChevronLeftIcon />
                이전
              </button>
              <button
                className="inline-flex h-10 items-center gap-2 rounded-md border border-stone-300 bg-white px-3 text-sm font-bold text-stone-700 disabled:cursor-not-allowed disabled:opacity-40"
                type="button"
                disabled={page >= pageCount || isRowsLoading}
                onClick={() => setPage(Math.min(pageCount, page + 1))}
              >
                다음
                <ChevronRightIcon />
              </button>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}

function formatCell(value: AdminJsonValue | undefined): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value, null, 2);
}

function stableRowKey(row: AdminDatasetRow, rowIndex: number): string {
  const id = row.id;
  if (typeof id === "string" || typeof id === "number") {
    return String(id);
  }
  return `row-${rowIndex}`;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return "관리자 데이터를 불러오지 못했다.";
}

function isUnauthorized(error: unknown): boolean {
  return error instanceof AdminApiError && error.status === 401;
}

function SearchIcon() {
  return (
    <svg aria-hidden="true" className="size-4 shrink-0" fill="none" viewBox="0 0 24 24">
      <path
        d="m21 21-4.3-4.3M10.8 18a7.2 7.2 0 1 1 0-14.4 7.2 7.2 0 0 1 0 14.4Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="2"
      />
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 24 24">
      <path
        d="M20 12a8 8 0 0 1-13.66 5.66M4 12A8 8 0 0 1 17.66 6.34M18 3v4h-4M6 21v-4h4"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

function LogoutIcon() {
  return (
    <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 24 24">
      <path
        d="M15 17l5-5-5-5M20 12H9M12 21H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h7"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

function UsersIcon() {
  return (
    <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 24 24">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" stroke="currentColor" strokeWidth="2" />
      <path d="M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z" stroke="currentColor" strokeWidth="2" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

function WorkflowIcon() {
  return (
    <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 24 24">
      <path
        d="M6 6h4v4H6V6ZM14 14h4v4h-4v-4ZM10 8h2a4 4 0 0 1 4 4v2M8 10v2a4 4 0 0 0 4 4h2"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

function ExternalLinkIcon() {
  return (
    <svg aria-hidden="true" className="size-3" fill="none" viewBox="0 0 24 24">
      <path
        d="M14 4h6v6M20 4l-9 9M20 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

function ChevronLeftIcon() {
  return (
    <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 24 24">
      <path d="m15 18-6-6 6-6" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
    </svg>
  );
}

function ChevronRightIcon() {
  return (
    <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 24 24">
      <path d="m9 18 6-6-6-6" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
    </svg>
  );
}

function SortIcon({ direction }: { direction: "asc" | "desc" }) {
  return (
    <svg aria-hidden="true" className="size-3" fill="none" viewBox="0 0 24 24">
      {direction === "asc" ? (
        <path d="m7 14 5-5 5 5" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
      ) : (
        <path d="m7 10 5 5 5-5" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
      )}
    </svg>
  );
}
