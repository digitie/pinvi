"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { FormEvent, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import {
  AdminApiError,
  fetchAdminMe,
  fetchAdminUsers,
  logoutAdmin,
  updateAdminUser,
  type AdminUpdateUserInput,
  type AdminUserListResponse,
} from "../api";
import { getDagsterAdminUrl } from "../config";
import { queryKeys } from "../../shared/query-keys";
import { useAdminUsersStore } from "../../shared/stores";

const accountStatusOptions = [
  { value: "", label: "전체 상태" },
  { value: "pending_email_verification", label: "이메일 인증 대기" },
  { value: "invited", label: "초대됨" },
  { value: "active", label: "활성" },
  { value: "disabled", label: "비활성" },
  { value: "deleted", label: "삭제됨" },
];

const roleOptions = [
  { value: "", label: "전체 역할" },
  { value: "admin", label: "관리자" },
  { value: "planner", label: "여행계획 작성자" },
  { value: "participant", label: "참여자" },
];

const dagsterAdminUrl = getDagsterAdminUrl();

export default function AdminUsersPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const {
    accountStatus,
    applyFilters: applyFiltersState,
    limit,
    page,
    search,
    setAccountStatus,
    setLimit,
    setPage,
    setSearch,
    setSystemRole,
    submittedAccountStatus,
    submittedSearch,
    submittedSystemRole,
    systemRole,
  } = useAdminUsersStore();

  const adminMeQuery = useQuery({
    queryKey: queryKeys.admin.me(),
    queryFn: fetchAdminMe,
    retry: false,
  });

  const usersQueryInput = useMemo(
    () => ({
      page,
      limit,
      search: submittedSearch,
      accountStatus: submittedAccountStatus,
      systemRole: submittedSystemRole,
    }),
    [limit, page, submittedAccountStatus, submittedSearch, submittedSystemRole],
  );

  const usersQuery = useQuery({
    queryKey: queryKeys.admin.users(usersQueryInput),
    queryFn: () => fetchAdminUsers(usersQueryInput),
    retry: false,
  });

  const logoutMutation = useMutation({
    mutationFn: logoutAdmin,
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: queryKeys.admin.root() });
      router.replace("/admin/login");
    },
  });

  const updateUserMutation = useMutation({
    mutationFn: ({ mode, userId }: { mode: "activate" | "disable" | "verify"; userId: string }) =>
      updateAdminUser(userId, buildUpdateUserInput(mode)),
    onSuccess: (updatedUser) => {
      queryClient.setQueryData<AdminUserListResponse>(
        queryKeys.admin.users(usersQueryInput),
        (current) =>
          current
            ? {
                ...current,
                users: current.users.map((user) =>
                  user.id === updatedUser.id ? updatedUser : user,
                ),
              }
            : current,
      );
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.usersRoot() });
    },
  });

  const adminUser = adminMeQuery.data ?? null;
  const users = usersQuery.data?.users ?? [];
  const total = usersQuery.data?.total ?? 0;
  const pageCount = useMemo(() => Math.max(1, Math.ceil(total / limit)), [limit, total]);
  const isLoading = usersQuery.isPending;
  const isMutatingUserId = updateUserMutation.isPending
    ? updateUserMutation.variables?.userId ?? null
    : null;
  const queryError =
    adminMeQuery.error ?? usersQuery.error ?? logoutMutation.error ?? updateUserMutation.error;
  const errorMessage = queryError && !isUnauthorized(queryError) ? getErrorMessage(queryError) : null;

  useEffect(() => {
    if (isUnauthorized(adminMeQuery.error) || isUnauthorized(usersQuery.error)) {
      router.replace("/admin/login");
    }
  }, [adminMeQuery.error, router, usersQuery.error]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    applyFiltersState();
  }

  function handleLogout() {
    logoutMutation.mutate();
  }

  function mutateUser(userId: string, mode: "activate" | "disable" | "verify") {
    updateUserMutation.mutate({ mode, userId });
  }

  return (
    <main className="min-h-svh bg-stone-100 text-stone-950">
      <header className="border-b border-stone-200 bg-white">
        <div className="mx-auto flex max-w-[1480px] flex-col gap-4 px-4 py-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm font-black text-teal-800">TripMate Admin</p>
            <h1 className="mt-1 text-2xl font-black">사용자 관리</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link
              className="inline-flex h-10 items-center gap-2 rounded-md border border-stone-300 bg-white px-3 text-sm font-bold text-stone-800"
              href="/admin"
            >
              <TableIcon />
              데이터
            </Link>
            <Link
              className="inline-flex h-10 items-center gap-2 rounded-md border border-stone-300 bg-white px-3 text-sm font-bold text-stone-800"
              href="/admin/data"
            >
              <TableIcon />
              CRUD
            </Link>
            <Link
              className="inline-flex h-10 items-center gap-2 rounded-md border border-stone-300 bg-white px-3 text-sm font-bold text-stone-800"
              href="/admin/files"
            >
              <TableIcon />
              파일
            </Link>
            <a
              className="inline-flex h-10 items-center gap-2 rounded-md border border-stone-300 bg-white px-3 text-sm font-bold text-stone-800"
              href={dagsterAdminUrl}
              rel="noreferrer"
              target="_blank"
            >
              <WorkflowIcon />
              Dagster
              <ExternalLinkIcon />
            </a>
            <span className="rounded-md border border-stone-200 bg-stone-50 px-3 py-2 text-sm font-semibold text-stone-700">
              {adminUser?.email}
            </span>
            <button
              className="inline-flex h-10 items-center gap-2 rounded-md border border-stone-300 bg-white px-3 text-sm font-bold text-stone-800"
              type="button"
              onClick={() => void handleLogout()}
            >
              <LogoutIcon />
              로그아웃
            </button>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-[1480px] px-4 py-4 sm:px-6">
        <form
          className="grid gap-3 border border-stone-200 bg-white p-4 lg:grid-cols-[minmax(220px,1fr)_220px_180px_100px_120px]"
          onSubmit={applyFilters}
        >
          <label className="block">
            <span className="mb-1 block text-xs font-black text-stone-600">검색</span>
            <input
              className="h-10 w-full rounded-md border border-stone-300 px-3 text-sm outline-none focus:border-teal-700 focus:ring-4 focus:ring-teal-700/10"
              value={search}
              placeholder="이메일, 이름, 닉네임"
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-black text-stone-600">상태</span>
            <select
              className="h-10 w-full rounded-md border border-stone-300 bg-white px-2 text-sm outline-none"
              value={accountStatus}
              onChange={(event) => setAccountStatus(event.target.value)}
            >
              {accountStatusOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-black text-stone-600">역할</span>
            <select
              className="h-10 w-full rounded-md border border-stone-300 bg-white px-2 text-sm outline-none"
              value={systemRole}
              onChange={(event) => setSystemRole(event.target.value)}
            >
              {roleOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-black text-stone-600">페이지</span>
            <select
              className="h-10 w-full rounded-md border border-stone-300 bg-white px-2 text-sm outline-none"
              value={limit}
              onChange={(event) => {
                setLimit(Number(event.target.value));
              }}
            >
              {[50, 100, 200].map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <button
            className="mt-5 inline-flex h-10 items-center justify-center gap-2 rounded-md bg-stone-950 px-3 text-sm font-black text-white"
            type="submit"
          >
            <SearchIcon />
            조회
          </button>
        </form>

        {errorMessage ? (
          <div className="mt-3 border border-red-200 bg-red-50 px-4 py-3 text-sm font-bold text-red-800">
            {errorMessage}
          </div>
        ) : null}

        <div className="mt-4 overflow-hidden border border-stone-200 bg-white">
          <div className="flex items-center justify-between border-b border-stone-200 px-4 py-3">
            <p className="text-sm font-black text-stone-700">
              총 {total.toLocaleString("ko-KR")}명
            </p>
            <Link className="text-sm font-bold text-teal-800" href="/signup">
              가입 페이지 열기
            </Link>
          </div>

          <div className="overflow-auto">
            <table className="min-w-full border-separate border-spacing-0 text-left text-sm">
              <thead className="bg-stone-50">
                <tr>
                  {["이메일", "이름", "상태", "역할", "인증", "생성", "관리"].map((header) => (
                    <th
                      className="whitespace-nowrap border-b border-r border-stone-200 px-3 py-2 text-xs font-black text-stone-600 last:border-r-0"
                      key={header}
                    >
                      {header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td className="px-4 py-10 text-center font-bold text-stone-500" colSpan={7}>
                      사용자 목록을 불러오는 중
                    </td>
                  </tr>
                ) : users.length > 0 ? (
                  users.map((user) => (
                    <tr className="odd:bg-white even:bg-stone-50/60" key={user.id}>
                      <td className="border-b border-r border-stone-200 px-3 py-2 font-mono text-xs">
                        {user.email}
                      </td>
                      <td className="border-b border-r border-stone-200 px-3 py-2">
                        <strong className="block text-stone-900">{user.nickname ?? "-"}</strong>
                        <span className="text-xs text-stone-500">{user.name ?? "-"}</span>
                      </td>
                      <td className="border-b border-r border-stone-200 px-3 py-2">
                        <StatusBadge value={user.account_status} />
                      </td>
                      <td className="border-b border-r border-stone-200 px-3 py-2">
                        {roleLabel(user.system_role)}
                      </td>
                      <td className="border-b border-r border-stone-200 px-3 py-2">
                        {user.email_verified_at ? "완료" : "대기"}
                      </td>
                      <td className="border-b border-r border-stone-200 px-3 py-2 font-mono text-xs text-stone-500">
                        {formatDateTime(user.created_at)}
                      </td>
                      <td className="border-b border-stone-200 px-3 py-2">
                        <div className="flex flex-wrap gap-2">
                          <ActionButton
                            disabled={isMutatingUserId === user.id}
                            onClick={() => void mutateUser(user.id, "activate")}
                          >
                            활성화
                          </ActionButton>
                          <ActionButton
                            disabled={isMutatingUserId === user.id || Boolean(user.email_verified_at)}
                            onClick={() => void mutateUser(user.id, "verify")}
                          >
                            인증
                          </ActionButton>
                          <ActionButton
                            disabled={isMutatingUserId === user.id}
                            onClick={() => void mutateUser(user.id, "disable")}
                          >
                            비활성
                          </ActionButton>
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td className="px-4 py-10 text-center font-bold text-stone-500" colSpan={7}>
                      조회된 사용자가 없습니다.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between border-t border-stone-200 px-4 py-3">
            <p className="text-sm font-semibold text-stone-600">
              {page.toLocaleString("ko-KR")} / {pageCount.toLocaleString("ko-KR")} 페이지
            </p>
            <div className="flex gap-2">
              <button
                className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm font-bold disabled:opacity-40"
                type="button"
                disabled={page <= 1 || isLoading}
                onClick={() => setPage(Math.max(1, page - 1))}
              >
                이전
              </button>
              <button
                className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm font-bold disabled:opacity-40"
                type="button"
                disabled={page >= pageCount || isLoading}
                onClick={() => setPage(Math.min(pageCount, page + 1))}
              >
                다음
              </button>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}

function ActionButton({
  children,
  disabled,
  onClick,
}: {
  children: React.ReactNode;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className="inline-flex h-8 items-center rounded-md border border-stone-300 bg-white px-2 text-xs font-black text-stone-700 disabled:cursor-not-allowed disabled:opacity-40"
      type="button"
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function StatusBadge({ value }: { value: string }) {
  const isActive = value === "active";
  return (
    <span
      className={`inline-flex rounded px-2 py-1 text-xs font-black ${
        isActive ? "bg-teal-50 text-teal-800" : "bg-amber-50 text-amber-800"
      }`}
    >
      {statusLabel(value)}
    </span>
  );
}

function statusLabel(value: string): string {
  return accountStatusOptions.find((option) => option.value === value)?.label ?? value;
}

function roleLabel(value: string): string {
  return roleOptions.find((option) => option.value === value)?.label ?? value;
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("ko-KR", { hour12: false });
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return "사용자 정보를 불러오지 못했다.";
}

function buildUpdateUserInput(mode: "activate" | "disable" | "verify"): AdminUpdateUserInput {
  if (mode === "activate") {
    return { account_status: "active", email_verified: true };
  }
  if (mode === "disable") {
    return { account_status: "disabled" };
  }
  return { email_verified: true };
}

function isUnauthorized(error: unknown): boolean {
  return error instanceof AdminApiError && error.status === 401;
}

function SearchIcon() {
  return (
    <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 24 24">
      <path
        d="m21 21-4.3-4.3M10.8 18a7.2 7.2 0 1 1 0-14.4 7.2 7.2 0 0 1 0 14.4Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="2"
      />
    </svg>
  );
}

function TableIcon() {
  return (
    <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 24 24">
      <path d="M4 5h16M4 12h16M4 19h16M8 5v14" stroke="currentColor" strokeWidth="2" />
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
