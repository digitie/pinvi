"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AdminApiError,
  createAdminEntity,
  deleteAdminEntity,
  fetchAdminEntityDetail,
  fetchAdminEntityList,
  fetchAdminMe,
  logoutAdmin,
  updateAdminEntity,
  type AdminEntityItem,
  type AdminEntityKind,
  type AdminEntityLink,
  type AdminEntityListQuery,
  type AdminEntityMapPoint,
  type AdminEntityUpsertInput,
  type AdminJsonValue,
} from "../api";
import { getDagsterAdminUrl } from "../config";
import { queryKeys } from "../../shared/query-keys";

type FieldType = "text" | "select" | "date" | "number" | "json" | "boolean";

type EntityField = {
  key: string;
  label: string;
  type: FieldType;
  required?: boolean;
  createOnly?: boolean;
  options?: string[];
  placeholder?: string;
};

type EntityConfig = {
  label: string;
  description: string;
  searchPlaceholder: string;
  filters: Array<{ key: string; label: string; placeholder: string }>;
  columns: Array<{ key: string; label: string }>;
  fields: EntityField[];
};

type FormValue = string | boolean;

const dagsterAdminUrl = getDagsterAdminUrl();

const ENTITY_ORDER: AdminEntityKind[] = ["users", "features", "trips", "pois"];

const ENTITY_CONFIGS: Record<AdminEntityKind, EntityConfig> = {
  users: {
    label: "Users",
    description: "회원 계정, 권한, 이메일 인증 상태를 테스트용으로 생성하고 조정합니다.",
    searchPlaceholder: "이메일, 이름, UUID 검색",
    filters: [
      { key: "account_status", label: "계정 상태", placeholder: "active" },
      { key: "system_role", label: "역할", placeholder: "planner" },
    ],
    columns: [
      { key: "email", label: "이메일" },
      { key: "display_name", label: "표시명" },
      { key: "account_status", label: "상태" },
      { key: "system_role", label: "역할" },
      { key: "trip_count", label: "Trips" },
      { key: "poi_count", label: "POI" },
    ],
    fields: [
      { key: "email", label: "이메일", type: "text", required: true },
      { key: "password", label: "비밀번호", type: "text", createOnly: true },
      { key: "nickname", label: "닉네임", type: "text" },
      { key: "name", label: "이름", type: "text" },
      {
        key: "account_status",
        label: "계정 상태",
        type: "select",
        required: true,
        options: ["pending_email_verification", "invited", "active", "disabled", "deleted"],
      },
      {
        key: "system_role",
        label: "시스템 역할",
        type: "select",
        required: true,
        options: ["admin", "planner", "participant"],
      },
      { key: "email_verified", label: "이메일 인증", type: "boolean" },
      { key: "birth_year_month", label: "생년월", type: "text", placeholder: "YYYYMM" },
      { key: "gender", label: "성별", type: "text" },
      { key: "residence_sigungu_code", label: "거주 시군구 코드", type: "text" },
    ],
  },
  features: {
    label: "Features",
    description: "지도에 표시되는 feature DB를 직접 만들고 POI 연결을 확인합니다.",
    searchPlaceholder: "feature_id, 이름, 주소, 카테고리 검색",
    filters: [
      { key: "feature_id", label: "Feature ID", placeholder: "beach:..." },
      { key: "kind", label: "종류", placeholder: "place" },
      { key: "status", label: "상태", placeholder: "active" },
    ],
    columns: [
      { key: "feature_id", label: "Feature ID" },
      { key: "name", label: "이름" },
      { key: "kind", label: "종류" },
      { key: "category", label: "카테고리" },
      { key: "status", label: "상태" },
      { key: "poi_count", label: "POI" },
    ],
    fields: [
      { key: "feature_id", label: "Feature ID", type: "text", createOnly: true },
      {
        key: "kind",
        label: "종류",
        type: "select",
        required: true,
        options: ["place", "event", "notice", "price", "weather", "route", "area"],
      },
      { key: "name", label: "이름", type: "text", required: true },
      { key: "category", label: "카테고리", type: "text", required: true },
      {
        key: "status",
        label: "상태",
        type: "select",
        required: true,
        options: ["active", "hidden", "broken"],
      },
      { key: "longitude", label: "경도", type: "number", required: true },
      { key: "latitude", label: "위도", type: "number", required: true },
      { key: "address_road", label: "도로명 주소", type: "text" },
      { key: "address_jibun", label: "지번 주소", type: "text" },
      { key: "bjd_code", label: "법정동 코드", type: "text" },
      { key: "marker_color", label: "마커 색", type: "text", placeholder: "#0f766e" },
      { key: "marker_icon", label: "마커 아이콘", type: "text", placeholder: "pin" },
      { key: "urls", label: "URL JSON", type: "json", placeholder: "{}" },
      { key: "detail", label: "상세 JSON", type: "json", placeholder: "{}" },
      { key: "raw_refs", label: "Raw refs JSON", type: "json", placeholder: "[]" },
    ],
  },
  trips: {
    label: "Trips",
    description: "사용자와 연결된 여행, 날짜, POI 관계를 검증합니다.",
    searchPlaceholder: "여행명, 목적지, UUID 검색",
    filters: [
      { key: "user_id", label: "User ID", placeholder: "사용자 UUID" },
      { key: "planning_status", label: "상태", placeholder: "idea" },
    ],
    columns: [
      { key: "title", label: "여행명" },
      { key: "destination", label: "목적지" },
      { key: "owner_email", label: "소유자" },
      { key: "planning_status", label: "상태" },
      { key: "day_count", label: "일수" },
      { key: "poi_count", label: "POI" },
    ],
    fields: [
      { key: "user_id", label: "User ID", type: "text", required: true },
      { key: "leader_id", label: "Leader ID", type: "text" },
      { key: "title", label: "여행명", type: "text", required: true },
      { key: "name", label: "별칭", type: "text" },
      { key: "destination", label: "목적지", type: "text", required: true },
      { key: "start_date", label: "시작일", type: "date", required: true },
      { key: "end_date", label: "종료일", type: "date", required: true },
      {
        key: "planning_status",
        label: "계획 상태",
        type: "select",
        required: true,
        options: ["idea", "draft", "active", "completed", "archived"],
      },
      { key: "fuel_types", label: "유종", type: "text", placeholder: "gasoline,diesel" },
    ],
  },
  pois: {
    label: "POI",
    description: "여행 일정에 붙은 POI와 feature 링크, 예산, 메모를 검증합니다.",
    searchPlaceholder: "POI UUID, trip_id, feature_id, 메모 검색",
    filters: [
      { key: "trip_id", label: "Trip ID", placeholder: "여행 UUID" },
      { key: "feature_id", label: "Feature ID", placeholder: "feature_id" },
      { key: "user_id", label: "User ID", placeholder: "추가 사용자 UUID" },
    ],
    columns: [
      { key: "feature_name", label: "Feature" },
      { key: "trip_id", label: "Trip ID" },
      { key: "day_index", label: "Day" },
      { key: "sort_order", label: "순서" },
      { key: "memo", label: "메모" },
      { key: "currency", label: "통화" },
    ],
    fields: [
      { key: "trip_id", label: "Trip ID", type: "text", required: true },
      { key: "day_index", label: "Day", type: "number", required: true },
      { key: "sort_order", label: "정렬키", type: "text" },
      { key: "feature_id", label: "Feature ID", type: "text" },
      { key: "added_by_user_id", label: "추가 User ID", type: "text" },
      { key: "memo", label: "메모", type: "text" },
      { key: "budget", label: "예산", type: "number" },
      { key: "actual_spent", label: "실지출", type: "number" },
      { key: "currency", label: "통화", type: "text", placeholder: "KRW" },
      { key: "user_url", label: "사용자 URL", type: "text" },
      { key: "custom_marker_color", label: "마커 색", type: "text" },
      { key: "custom_marker_icon", label: "마커 아이콘", type: "text" },
      { key: "snapshot", label: "스냅샷 JSON", type: "json", placeholder: "{}" },
    ],
  },
};

export default function AdminDataCrudPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [entity, setEntity] = useState<AdminEntityKind>("users");
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [submittedSearch, setSubmittedSearch] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [submittedFilters, setSubmittedFilters] = useState<Record<string, string>>({});
  const [selectedId, setSelectedId] = useState("");
  const [mode, setMode] = useState<"create" | "edit">("create");
  const [feedback, setFeedback] = useState<string | null>(null);

  const config = ENTITY_CONFIGS[entity];
  const listQueryInput = useMemo<AdminEntityListQuery>(
    () => ({
      page,
      limit: 25,
      search: submittedSearch,
      filters: compactFilters(submittedFilters),
    }),
    [page, submittedFilters, submittedSearch],
  );

  const adminMeQuery = useQuery({
    queryKey: queryKeys.admin.me(),
    queryFn: fetchAdminMe,
    retry: false,
  });
  const listQuery = useQuery({
    queryKey: queryKeys.admin.entityList(entity, listQueryInput),
    queryFn: () => fetchAdminEntityList(entity, listQueryInput),
    retry: false,
  });
  const detailQuery = useQuery({
    queryKey: queryKeys.admin.entityDetail(entity, selectedId),
    queryFn: () => fetchAdminEntityDetail(entity, selectedId),
    enabled: mode === "edit" && Boolean(selectedId),
    retry: false,
  });

  const saveMutation = useMutation({
    mutationFn: (values: AdminEntityUpsertInput) =>
      mode === "create"
        ? createAdminEntity(entity, values)
        : updateAdminEntity(entity, selectedId, values),
    onSuccess: (result) => {
      setMode("edit");
      setSelectedId(result.item.id);
      setFeedback("저장했다.");
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.entitiesRoot() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.datasets() });
    },
    onError: (error) => setFeedback(getErrorMessage(error)),
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteAdminEntity(entity, selectedId),
    onSuccess: () => {
      setMode("create");
      setSelectedId("");
      setFeedback("삭제했다.");
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.entitiesRoot() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.datasets() });
    },
    onError: (error) => setFeedback(getErrorMessage(error)),
  });

  const logoutMutation = useMutation({
    mutationFn: logoutAdmin,
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: queryKeys.admin.root() });
      router.replace("/admin/login");
    },
  });

  useEffect(() => {
    if (
      isUnauthorized(adminMeQuery.error) ||
      isUnauthorized(listQuery.error) ||
      isUnauthorized(detailQuery.error)
    ) {
      router.replace("/admin/login");
    }
  }, [adminMeQuery.error, detailQuery.error, listQuery.error, router]);

  const pageCount = listQuery.data ? Math.max(1, Math.ceil(listQuery.data.total / 25)) : 1;
  const errorMessage =
    feedback ??
    getVisibleError(adminMeQuery.error) ??
    getVisibleError(listQuery.error) ??
    getVisibleError(detailQuery.error);

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPage(1);
    setSubmittedSearch(search);
    setSubmittedFilters(filters);
  }

  function startCreate() {
    setMode("create");
    setSelectedId("");
    setFeedback(null);
  }

  function selectItem(item: AdminEntityItem) {
    setMode("edit");
    setSelectedId(item.id);
    setFeedback(null);
  }

  function switchEntity(nextEntity: AdminEntityKind) {
    setEntity(nextEntity);
    setPage(1);
    setSearch("");
    setSubmittedSearch("");
    setFilters({});
    setSubmittedFilters({});
    setSelectedId("");
    setMode("create");
    setFeedback(null);
  }

  function followLink(link: AdminEntityLink) {
    setEntity(link.entity);
    setPage(1);
    setSubmittedSearch("");
    setSearch("");
    setFilters(link.query);
    setSubmittedFilters(link.query);
    setMode(link.id ? "edit" : "create");
    setSelectedId(link.id ?? "");
  }

  function requestDelete() {
    if (!selectedId || mode !== "edit") {
      return;
    }
    if (window.confirm(`${config.label} ${selectedId} 삭제를 진행할까요?`)) {
      deleteMutation.mutate();
    }
  }

  return (
    <main className="min-h-svh bg-stone-100 text-stone-950">
      <header className="border-b border-stone-200 bg-white">
        <div className="mx-auto flex max-w-[1760px] flex-col gap-4 px-4 py-4 sm:px-6 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <p className="text-sm font-black text-teal-800">TripMate Admin</p>
            <h1 className="mt-1 text-2xl font-black tracking-normal text-stone-950">
              엔티티 CRUD 콘솔
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link className="admin-top-button" href="/admin">
              <DatabaseIcon />
              Raw DB
            </Link>
            <Link className="admin-top-button" href="/admin/users">
              <UsersIcon />
              사용자 관리
            </Link>
            <Link className="admin-top-button" href="/admin/files">
              <DatabaseIcon />
              파일 관리
            </Link>
            <a className="admin-top-button" href={dagsterAdminUrl} rel="noreferrer" target="_blank">
              <WorkflowIcon />
              Dagster
            </a>
            <span className="rounded-md border border-stone-200 bg-stone-50 px-3 py-2 text-sm font-semibold text-stone-700">
              {adminMeQuery.data?.email ?? "admin"}
            </span>
            <button className="admin-top-button" type="button" onClick={() => logoutMutation.mutate()}>
              <LogoutIcon />
              로그아웃
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1760px] grid-cols-1 gap-4 px-4 py-4 sm:px-6 xl:grid-cols-[220px_minmax(0,1.1fr)_minmax(360px,0.9fr)]">
        <aside className="border border-stone-200 bg-white">
          <div className="border-b border-stone-200 p-4">
            <p className="text-xs font-black uppercase text-stone-500">entities</p>
            <p className="mt-1 text-sm font-semibold text-stone-700">데이터 CRUD와 연계 확인</p>
          </div>
          <nav className="p-2">
            {ENTITY_ORDER.map((item) => (
              <button
                className={`mb-1 flex h-11 w-full items-center justify-between rounded-md px-3 text-left text-sm font-black transition ${
                  entity === item
                    ? "bg-teal-800 text-white"
                    : "text-stone-700 hover:bg-stone-100"
                }`}
                key={item}
                type="button"
                onClick={() => switchEntity(item)}
              >
                <span>{ENTITY_CONFIGS[item].label}</span>
                <ChevronRightIcon />
              </button>
            ))}
          </nav>
        </aside>

        <section className="min-w-0 border border-stone-200 bg-white">
          <div className="border-b border-stone-200 p-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <p className="text-xs font-black uppercase text-amber-700">browse</p>
                <h2 className="mt-1 text-xl font-black text-stone-950">{config.label}</h2>
                <p className="mt-1 text-sm leading-6 text-stone-500">{config.description}</p>
              </div>
              <button
                className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-stone-950 px-3 text-sm font-black text-white transition hover:bg-stone-800"
                type="button"
                onClick={startCreate}
              >
                <PlusIcon />
                새로 만들기
              </button>
            </div>

            <form className="mt-4 grid gap-2 lg:grid-cols-[minmax(220px,1fr)_repeat(3,minmax(140px,180px))_88px]" onSubmit={submitSearch}>
              <label className="block">
                <span className="mb-1 block text-xs font-black text-stone-600">검색</span>
                <input
                  className="admin-input"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder={config.searchPlaceholder}
                />
              </label>
              {config.filters.map((filter) => (
                <label className="block" key={filter.key}>
                  <span className="mb-1 block text-xs font-black text-stone-600">
                    {filter.label}
                  </span>
                  <input
                    className="admin-input"
                    value={filters[filter.key] ?? ""}
                    onChange={(event) =>
                      setFilters((current) => ({ ...current, [filter.key]: event.target.value }))
                    }
                    placeholder={filter.placeholder}
                  />
                </label>
              ))}
              <button
                className="mt-5 inline-flex h-10 items-center justify-center gap-2 rounded-md bg-teal-800 px-3 text-sm font-black text-white transition hover:bg-teal-700"
                type="submit"
              >
                <SearchIcon />
                조회
              </button>
            </form>
          </div>

          {errorMessage ? (
            <div className="border-b border-red-200 bg-red-50 px-4 py-3 text-sm font-bold text-red-800">
              {errorMessage}
            </div>
          ) : null}

          <div className="min-h-[540px] overflow-auto">
            {listQuery.isPending ? (
              <div className="flex h-[540px] items-center justify-center text-sm font-bold text-stone-500">
                목록을 불러오는 중
              </div>
            ) : listQuery.data && listQuery.data.items.length > 0 ? (
              <table className="min-w-full border-separate border-spacing-0 text-left text-sm">
                <thead className="sticky top-0 z-10 bg-stone-50">
                  <tr>
                    <th className="admin-th">항목</th>
                    {config.columns.map((column) => (
                      <th className="admin-th" key={column.key}>
                        {column.label}
                      </th>
                    ))}
                    <th className="admin-th">상태</th>
                  </tr>
                </thead>
                <tbody>
                  {listQuery.data.items.map((item) => (
                    <tr
                      className={`cursor-pointer odd:bg-white even:bg-stone-50/60 ${
                        selectedId === item.id ? "outline outline-2 outline-teal-700" : ""
                      }`}
                      key={item.id}
                      onClick={() => selectItem(item)}
                    >
                      <td className="admin-td">
                        <span className="block max-w-[260px] truncate font-black text-stone-900">
                          {item.label}
                        </span>
                        <span className="mt-1 block max-w-[260px] truncate font-mono text-xs text-stone-500">
                          {item.id}
                        </span>
                      </td>
                      {config.columns.map((column) => (
                        <td className="admin-td" key={column.key}>
                          <span className="block max-w-[220px] truncate">
                            {formatValue(item.fields[column.key])}
                          </span>
                        </td>
                      ))}
                      <td className="admin-td">
                        <StatusBadge status={item.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="flex h-[540px] flex-col items-center justify-center gap-2 px-4 text-center">
                <p className="text-base font-black text-stone-800">조회된 데이터가 없습니다.</p>
                <p className="max-w-md text-sm leading-6 text-stone-500">
                  검색 조건을 바꾸거나 새 테스트 데이터를 만들 수 있습니다.
                </p>
              </div>
            )}
          </div>

          <div className="flex items-center justify-between border-t border-stone-200 p-4">
            <p className="text-sm font-semibold text-stone-600">
              {listQuery.data
                ? `${listQuery.data.page.toLocaleString("ko-KR")} / ${pageCount.toLocaleString("ko-KR")} 페이지, 총 ${listQuery.data.total.toLocaleString("ko-KR")}건`
                : "페이지 정보 없음"}
            </p>
            <div className="flex items-center gap-2">
              <button
                className="admin-page-button"
                disabled={page <= 1 || listQuery.isFetching}
                type="button"
                onClick={() => setPage(Math.max(1, page - 1))}
              >
                이전
              </button>
              <button
                className="admin-page-button"
                disabled={page >= pageCount || listQuery.isFetching}
                type="button"
                onClick={() => setPage(Math.min(pageCount, page + 1))}
              >
                다음
              </button>
            </div>
          </div>
        </section>

        <section className="min-w-0 border border-stone-200 bg-white">
          <div className="border-b border-stone-200 p-4">
            <p className="text-xs font-black uppercase text-amber-700">
              {mode === "create" ? "create" : "detail / edit"}
            </p>
            <h2 className="mt-1 truncate text-xl font-black text-stone-950">
              {mode === "create" ? `${config.label} 생성` : detailQuery.data?.item.label ?? "상세"}
            </h2>
          </div>

          <div className="max-h-[calc(100svh-170px)] overflow-y-auto">
            {mode === "edit" && detailQuery.data ? (
              <div className="border-b border-stone-200 p-4">
                <DetailPanel item={detailQuery.data.item} onFollowLink={followLink} />
                {detailQuery.data.related.length > 0 ? (
                  <div className="mt-4">
                    <p className="text-xs font-black uppercase text-stone-500">linked data</p>
                    <div className="mt-2 grid gap-2">
                      {detailQuery.data.related.map((group) => (
                        <div className="border border-stone-200 bg-stone-50 p-3" key={group.label}>
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-sm font-black text-stone-800">{group.label}</p>
                            <button
                              className="text-xs font-black text-teal-800 underline"
                              type="button"
                              onClick={() =>
                                followLink({
                                  entity: group.entity,
                                  relation: group.label,
                                  id: null,
                                  label: group.label,
                                  query: group.query,
                                })
                              }
                            >
                              전체 보기 {group.count.toLocaleString("ko-KR")}
                            </button>
                          </div>
                          <div className="mt-2 grid gap-1">
                            {group.sample.map((item) => (
                              <button
                                className="truncate text-left text-xs font-semibold text-stone-600 hover:text-teal-800"
                                key={item.id}
                                type="button"
                                onClick={() =>
                                  followLink({
                                    entity: item.entity,
                                    relation: group.label,
                                    id: item.id,
                                    label: item.label,
                                    query: {},
                                  })
                                }
                              >
                                {item.label}
                              </button>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}

            <EntityEditor
              config={config}
              isDeleting={deleteMutation.isPending}
              isSaving={saveMutation.isPending}
              item={detailQuery.data?.item ?? null}
              key={`${entity}-${mode}-${selectedId}-${String(detailQuery.data?.item.fields.updated_at ?? "")}`}
              mode={mode}
              onDelete={requestDelete}
              onReset={startCreate}
              onSubmit={(values) => {
                setFeedback(null);
                saveMutation.mutate(values);
              }}
              onValidationError={(message) => setFeedback(message)}
            />
          </div>
        </section>
      </div>
    </main>
  );
}

function EntityEditor({
  config,
  isDeleting,
  isSaving,
  item,
  mode,
  onDelete,
  onReset,
  onSubmit,
  onValidationError,
}: {
  config: EntityConfig;
  isDeleting: boolean;
  isSaving: boolean;
  item: AdminEntityItem | null;
  mode: "create" | "edit";
  onDelete: () => void;
  onReset: () => void;
  onSubmit: (values: AdminEntityUpsertInput) => void;
  onValidationError: (message: string) => void;
}) {
  const [formValues, setFormValues] = useState<Record<string, FormValue>>(() =>
    mode === "edit" && item ? itemToFormValues(config, item) : defaultFormValues(config),
  );

  function submitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      onSubmit(buildPayload(config, formValues, mode));
    } catch (error) {
      onValidationError(getErrorMessage(error));
    }
  }

  return (
    <form className="grid gap-3 p-4" onSubmit={submitForm}>
      <div className="grid gap-3 md:grid-cols-2">
        {config.fields
          .filter((field) => mode === "create" || !field.createOnly)
          .map((field) => (
            <FieldControl
              field={field}
              key={field.key}
              value={formValues[field.key] ?? defaultFieldValue(field)}
              onChange={(value) =>
                setFormValues((current) => ({ ...current, [field.key]: value }))
              }
            />
          ))}
      </div>
      <div className="flex flex-wrap items-center gap-2 border-t border-stone-200 pt-4">
        <button
          className="inline-flex h-10 items-center gap-2 rounded-md bg-stone-950 px-3 text-sm font-black text-white transition hover:bg-stone-800 disabled:opacity-40"
          disabled={isSaving}
          type="submit"
        >
          <SaveIcon />
          {mode === "create" ? "생성" : "저장"}
        </button>
        <button className="admin-page-button" type="button" onClick={onReset}>
          초기화
        </button>
        {mode === "edit" ? (
          <button
            className="inline-flex h-10 items-center gap-2 rounded-md border border-red-300 bg-white px-3 text-sm font-black text-red-700 transition hover:border-red-500 disabled:opacity-40"
            disabled={isDeleting}
            type="button"
            onClick={onDelete}
          >
            <TrashIcon />
            삭제
          </button>
        ) : null}
      </div>
    </form>
  );
}

function DetailPanel({
  item,
  onFollowLink,
}: {
  item: AdminEntityItem;
  onFollowLink: (link: AdminEntityLink) => void;
}) {
  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-lg font-black text-stone-950">{item.label}</p>
          <p className="mt-1 break-all font-mono text-xs text-stone-500">{item.id}</p>
        </div>
        <StatusBadge status={item.status} />
      </div>
      {item.map ? <MapPreview label={item.label} point={item.map} /> : null}
      {item.links.length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {item.links.map((link) => (
            <button
              className="inline-flex h-9 items-center gap-2 rounded-md border border-stone-300 bg-white px-3 text-xs font-black text-stone-700 transition hover:border-teal-700 hover:text-teal-800"
              key={`${link.entity}-${link.relation}-${link.id ?? JSON.stringify(link.query)}`}
              type="button"
              onClick={() => onFollowLink(link)}
            >
              <LinkIcon />
              {link.label}
            </button>
          ))}
        </div>
      ) : null}
      <div className="mt-4 grid grid-cols-1 border border-stone-200 text-sm sm:grid-cols-2">
        {Object.entries(item.fields).map(([key, value]) => (
          <div className="border-b border-stone-200 p-3 odd:border-r last:border-b-0" key={key}>
            <p className="text-xs font-black uppercase text-stone-500">{key}</p>
            <p className="mt-1 max-h-28 overflow-auto break-words font-mono text-xs leading-5 text-stone-800">
              {formatValue(value)}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

function FieldControl({
  field,
  value,
  onChange,
}: {
  field: EntityField;
  value: FormValue;
  onChange: (value: FormValue) => void;
}) {
  if (field.type === "boolean") {
    return (
      <label className="flex min-h-10 items-center gap-2 rounded-md border border-stone-300 px-3 text-sm font-bold text-stone-700">
        <input
          checked={Boolean(value)}
          className="size-4"
          type="checkbox"
          onChange={(event) => onChange(event.target.checked)}
        />
        {field.label}
      </label>
    );
  }
  if (field.type === "select") {
    return (
      <label className="block">
        <span className="mb-1 block text-xs font-black text-stone-600">{field.label}</span>
        <select
          className="admin-input"
          required={field.required}
          value={String(value)}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">선택</option>
          {field.options?.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
    );
  }
  if (field.type === "json") {
    return (
      <label className="block md:col-span-2">
        <span className="mb-1 block text-xs font-black text-stone-600">{field.label}</span>
        <textarea
          className="min-h-24 w-full rounded-md border border-stone-300 px-3 py-2 font-mono text-xs outline-none focus:border-teal-700 focus:ring-4 focus:ring-teal-700/10"
          required={field.required}
          value={String(value)}
          onChange={(event) => onChange(event.target.value)}
          placeholder={field.placeholder}
        />
      </label>
    );
  }
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-black text-stone-600">{field.label}</span>
      <input
        className="admin-input"
        required={field.required}
        type={field.type === "number" ? "number" : field.type}
        step={field.type === "number" ? "any" : undefined}
        value={String(value)}
        onChange={(event) => onChange(event.target.value)}
        placeholder={field.placeholder}
      />
    </label>
  );
}

function MapPreview({ label, point }: { label: string; point: AdminEntityMapPoint }) {
  const kakaoUrl = `https://map.kakao.com/link/map/${encodeURIComponent(label)},${point.latitude},${point.longitude}`;
  return (
    <div className="mt-4 overflow-hidden border border-stone-200">
      <div className="relative h-40 bg-[linear-gradient(90deg,#e7e5e4_1px,transparent_1px),linear-gradient(#e7e5e4_1px,transparent_1px)] bg-[size:24px_24px]">
        <div className="absolute inset-0 bg-teal-50/40" />
        <div className="absolute left-1/2 top-1/2 size-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-teal-800 shadow" />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-stone-200 p-3">
        <p className="font-mono text-xs text-stone-600">
          {point.latitude.toFixed(6)}, {point.longitude.toFixed(6)}
        </p>
        <a
          className="text-xs font-black text-teal-800 underline"
          href={kakaoUrl}
          rel="noreferrer"
          target="_blank"
        >
          Kakao 지도
        </a>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string | null }) {
  return (
    <span className="inline-flex h-7 items-center rounded-md border border-stone-200 bg-stone-50 px-2 text-xs font-black text-stone-700">
      {status ?? "none"}
    </span>
  );
}

function defaultFormValues(config: EntityConfig): Record<string, FormValue> {
  const values: Record<string, FormValue> = {};
  for (const field of config.fields) {
    values[field.key] = defaultFieldValue(field);
  }
  return values;
}

function defaultFieldValue(field: EntityField): FormValue {
  if (field.type === "boolean") {
    return false;
  }
  if (field.type === "json") {
    return field.placeholder ?? "{}";
  }
  if (field.type === "select") {
    return field.options?.[0] ?? "";
  }
  return "";
}

function itemToFormValues(config: EntityConfig, item: AdminEntityItem): Record<string, FormValue> {
  const values = defaultFormValues(config);
  for (const field of config.fields) {
    const rawValue = item.fields[field.key];
    if (rawValue === undefined || rawValue === null) {
      values[field.key] = defaultFieldValue(field);
      continue;
    }
    if (field.type === "boolean") {
      values[field.key] = Boolean(rawValue);
    } else if (field.type === "json") {
      values[field.key] = JSON.stringify(rawValue, null, 2);
    } else {
      values[field.key] = String(rawValue);
    }
  }
  return values;
}

function buildPayload(
  config: EntityConfig,
  formValues: Record<string, FormValue>,
  mode: "create" | "edit",
): AdminEntityUpsertInput {
  const payload: AdminEntityUpsertInput = {};
  for (const field of config.fields) {
    if (mode === "edit" && field.createOnly) {
      continue;
    }
    const rawValue = formValues[field.key] ?? defaultFieldValue(field);
    if (field.type === "boolean") {
      payload[field.key] = Boolean(rawValue);
      continue;
    }
    const textValue = String(rawValue).trim();
    if (!textValue) {
      if (field.required) {
        throw new Error(`${field.label} 값이 필요하다.`);
      }
      if (mode === "edit") {
        payload[field.key] = null;
      }
      continue;
    }
    if (field.type === "json") {
      payload[field.key] = parseJsonField(textValue, field.label);
    } else if (field.type === "number") {
      const numberValue = Number(textValue);
      if (!Number.isFinite(numberValue)) {
        throw new Error(`${field.label} 값은 숫자여야 한다.`);
      }
      payload[field.key] = numberValue;
    } else {
      payload[field.key] = textValue;
    }
  }
  return payload;
}

function parseJsonField(value: string, label: string): AdminJsonValue {
  try {
    return JSON.parse(value) as AdminJsonValue;
  } catch (error) {
    throw new Error(`${label} 값은 올바른 JSON이어야 한다.`, { cause: error });
  }
}

function compactFilters(filters: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(filters).filter(([, value]) => value.trim()));
}

function formatValue(value: AdminJsonValue | undefined): string {
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

function getVisibleError(error: unknown): string | null {
  if (!error || isUnauthorized(error)) {
    return null;
  }
  return getErrorMessage(error);
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return "관리자 CRUD 요청을 처리하지 못했다.";
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

function PlusIcon() {
  return (
    <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 24 24">
      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
    </svg>
  );
}

function SaveIcon() {
  return (
    <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 24 24">
      <path
        d="M5 4h11l3 3v13H5V4Zm3 0v6h8V4M8 20v-6h8v6"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 24 24">
      <path
        d="M4 7h16M9 7V5h6v2M8 10v9M12 10v9M16 10v9M6 7l1 14h10l1-14"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

function LinkIcon() {
  return (
    <svg aria-hidden="true" className="size-3" fill="none" viewBox="0 0 24 24">
      <path
        d="M10 13a5 5 0 0 0 7 0l2-2a5 5 0 0 0-7-7l-1 1M14 11a5 5 0 0 0-7 0l-2 2a5 5 0 0 0 7 7l1-1"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="2"
      />
    </svg>
  );
}

function DatabaseIcon() {
  return (
    <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 24 24">
      <path
        d="M5 6c0-1.7 3.1-3 7-3s7 1.3 7 3-3.1 3-7 3-7-1.3-7-3Zm0 0v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"
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

function ChevronRightIcon() {
  return (
    <svg aria-hidden="true" className="size-3" fill="none" viewBox="0 0 24 24">
      <path d="m9 18 6-6-6-6" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
    </svg>
  );
}
