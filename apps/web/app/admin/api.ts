import { fetchApi } from "../shared/api-base";

export type AdminJsonValue =
  | string
  | number
  | boolean
  | null
  | AdminJsonValue[]
  | { [key: string]: AdminJsonValue };

export type AdminUser = {
  id: string;
  email: string;
  display_name: string | null;
  is_admin: boolean;
  is_privileged: boolean;
};

export type AdminLoginResponse = {
  user: AdminUser;
};

export type AdminLogoutResponse = {
  status: string;
};

export type AdminDatasetColumn = {
  name: string;
  type: string;
  nullable: boolean;
  searchable: boolean;
  filterable: boolean;
  sortable: boolean;
};

export type AdminDatasetSummary = {
  table_name: string;
  row_count: number;
  columns: AdminDatasetColumn[];
};

export type AdminDatasetListResponse = {
  datasets: AdminDatasetSummary[];
  page_size_options: number[];
  default_page_size: number;
};

export type AdminDatasetRow = Record<string, AdminJsonValue>;

export type AdminDatasetRowsResponse = {
  table_name: string;
  page: number;
  limit: number;
  total: number;
  columns: AdminDatasetColumn[];
  rows: AdminDatasetRow[];
};

export type AdminDatasetRowsQuery = {
  page: number;
  limit: number;
  search: string;
  sortBy: string;
  sortDir: "asc" | "desc";
  filter: {
    column: string;
    value: string;
  };
};

export type AdminManagedUser = {
  id: string;
  email: string;
  display_name: string | null;
  nickname: string | null;
  name: string | null;
  account_status: string;
  system_role: string;
  birth_year_month: string | null;
  gender: string | null;
  residence_sigungu_code: string | null;
  email_verified_at: string | null;
  is_active: boolean;
  is_admin: boolean;
  is_privileged: boolean;
  created_at: string;
  updated_at: string;
};

export type AdminUserListResponse = {
  users: AdminManagedUser[];
  page: number;
  limit: number;
  total: number;
};

export type AdminUserListQuery = {
  page: number;
  limit: number;
  search: string;
  accountStatus: string;
  systemRole: string;
};

export type AdminUpdateUserInput = {
  account_status?: string;
  system_role?: string;
  nickname?: string;
  name?: string;
  email_verified?: boolean;
};

export class AdminApiError extends Error {
  status: number;
  payload: unknown;

  constructor(status: number, payload: unknown) {
    super(extractErrorMessage(payload) ?? `관리자 API 요청 실패 (${status})`);
    this.name = "AdminApiError";
    this.status = status;
    this.payload = payload;
  }
}

export class AdminResponseShapeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AdminResponseShapeError";
  }
}

export async function loginAdmin(
  email: string,
  password: string,
): Promise<AdminLoginResponse> {
  return parseAdminLoginResponse(
    await adminFetch("/admin/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  );
}

export async function logoutAdmin(): Promise<AdminLogoutResponse> {
  return parseAdminLogoutResponse(await adminFetch("/admin/auth/logout", { method: "POST" }));
}

export async function fetchAdminMe(): Promise<AdminUser> {
  return parseAdminUser(await adminFetch("/admin/auth/me"));
}

export async function fetchAdminDatasets(): Promise<AdminDatasetListResponse> {
  return parseAdminDatasetListResponse(await adminFetch("/admin/datasets"));
}

export async function fetchAdminDatasetRows(
  tableName: string,
  query: AdminDatasetRowsQuery,
): Promise<AdminDatasetRowsResponse> {
  const params = new URLSearchParams({
    page: String(query.page),
    limit: String(query.limit),
    sort_dir: query.sortDir,
  });
  if (query.search.trim()) {
    params.set("search", query.search.trim());
  }
  if (query.sortBy) {
    params.set("sort_by", query.sortBy);
  }
  if (query.filter.column && query.filter.value.trim()) {
    params.set(`filter.${query.filter.column}`, query.filter.value.trim());
  }

  return parseAdminDatasetRowsResponse(
    await adminFetch(`/admin/datasets/${encodeURIComponent(tableName)}/rows?${params.toString()}`),
  );
}

export async function fetchAdminUsers(query: AdminUserListQuery): Promise<AdminUserListResponse> {
  const params = new URLSearchParams({
    page: String(query.page),
    limit: String(query.limit),
  });
  if (query.search.trim()) {
    params.set("search", query.search.trim());
  }
  if (query.accountStatus) {
    params.set("account_status", query.accountStatus);
  }
  if (query.systemRole) {
    params.set("system_role", query.systemRole);
  }

  return parseAdminUserListResponse(await adminFetch(`/admin/users?${params.toString()}`));
}

export async function updateAdminUser(
  userId: string,
  input: AdminUpdateUserInput,
): Promise<AdminManagedUser> {
  return parseAdminManagedUser(
    await adminFetch(`/admin/users/${encodeURIComponent(userId)}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    }),
  );
}

async function adminFetch(path: string, init: RequestInit = {}): Promise<unknown> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetchApi(path, {
    ...init,
    headers,
    credentials: "include",
  });
  const payload = await readJsonPayload(response);

  if (!response.ok) {
    throw new AdminApiError(response.status, payload);
  }

  return payload;
}

async function readJsonPayload(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

function parseAdminLoginResponse(payload: unknown): AdminLoginResponse {
  const record = requireRecord(payload, "관리자 로그인 응답");
  return { user: parseAdminUser(record.user) };
}

function parseAdminLogoutResponse(payload: unknown): AdminLogoutResponse {
  const record = requireRecord(payload, "관리자 로그아웃 응답");
  return { status: requireString(record.status, "status") };
}

function parseAdminUser(payload: unknown): AdminUser {
  const record = requireRecord(payload, "관리자 사용자 응답");
  const displayName = record.display_name;
  return {
    id: requireString(record.id, "id"),
    email: requireString(record.email, "email"),
    display_name: displayName === null ? null : requireString(displayName, "display_name"),
    is_admin: requireBoolean(record.is_admin, "is_admin"),
    is_privileged: requireBoolean(record.is_privileged, "is_privileged"),
  };
}

function parseAdminDatasetListResponse(payload: unknown): AdminDatasetListResponse {
  const record = requireRecord(payload, "관리자 데이터셋 목록 응답");
  return {
    datasets: requireArray(record.datasets, "datasets").map(parseAdminDatasetSummary),
    page_size_options: requireArray(record.page_size_options, "page_size_options").map(
      (value) => requireNumber(value, "page_size_options[]"),
    ),
    default_page_size: requireNumber(record.default_page_size, "default_page_size"),
  };
}

function parseAdminDatasetSummary(payload: unknown): AdminDatasetSummary {
  const record = requireRecord(payload, "관리자 데이터셋 응답");
  return {
    table_name: requireString(record.table_name, "table_name"),
    row_count: requireNumber(record.row_count, "row_count"),
    columns: requireArray(record.columns, "columns").map(parseAdminDatasetColumn),
  };
}

function parseAdminDatasetRowsResponse(payload: unknown): AdminDatasetRowsResponse {
  const record = requireRecord(payload, "관리자 데이터셋 행 응답");
  return {
    table_name: requireString(record.table_name, "table_name"),
    page: requireNumber(record.page, "page"),
    limit: requireNumber(record.limit, "limit"),
    total: requireNumber(record.total, "total"),
    columns: requireArray(record.columns, "columns").map(parseAdminDatasetColumn),
    rows: requireArray(record.rows, "rows").map(parseAdminDatasetRow),
  };
}

function parseAdminUserListResponse(payload: unknown): AdminUserListResponse {
  const record = requireRecord(payload, "관리자 사용자 목록 응답");
  return {
    users: requireArray(record.users, "users").map(parseAdminManagedUser),
    page: requireNumber(record.page, "page"),
    limit: requireNumber(record.limit, "limit"),
    total: requireNumber(record.total, "total"),
  };
}

function parseAdminManagedUser(payload: unknown): AdminManagedUser {
  const record = requireRecord(payload, "관리자 사용자 응답");
  return {
    id: requireString(record.id, "id"),
    email: requireString(record.email, "email"),
    display_name: optionalString(record.display_name, "display_name"),
    nickname: optionalString(record.nickname, "nickname"),
    name: optionalString(record.name, "name"),
    account_status: requireString(record.account_status, "account_status"),
    system_role: requireString(record.system_role, "system_role"),
    birth_year_month: optionalString(record.birth_year_month, "birth_year_month"),
    gender: optionalString(record.gender, "gender"),
    residence_sigungu_code: optionalString(record.residence_sigungu_code, "residence_sigungu_code"),
    email_verified_at: optionalString(record.email_verified_at, "email_verified_at"),
    is_active: requireBoolean(record.is_active, "is_active"),
    is_admin: requireBoolean(record.is_admin, "is_admin"),
    is_privileged: requireBoolean(record.is_privileged, "is_privileged"),
    created_at: requireString(record.created_at, "created_at"),
    updated_at: requireString(record.updated_at, "updated_at"),
  };
}

function parseAdminDatasetColumn(payload: unknown): AdminDatasetColumn {
  const record = requireRecord(payload, "관리자 데이터셋 컬럼 응답");
  return {
    name: requireString(record.name, "name"),
    type: requireString(record.type, "type"),
    nullable: requireBoolean(record.nullable, "nullable"),
    searchable: requireBoolean(record.searchable, "searchable"),
    filterable: requireBoolean(record.filterable, "filterable"),
    sortable: requireBoolean(record.sortable, "sortable"),
  };
}

function parseAdminDatasetRow(payload: unknown): AdminDatasetRow {
  const record = requireRecord(payload, "관리자 데이터셋 행");
  const row: AdminDatasetRow = {};
  for (const [key, value] of Object.entries(record)) {
    if (!isAdminJsonValue(value)) {
      throw new AdminResponseShapeError(`행 값이 JSON 형태가 아니다: ${key}`);
    }
    row[key] = value;
  }
  return row;
}

function requireRecord(value: unknown, context: string): Record<string, unknown> {
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  throw new AdminResponseShapeError(`${context} 형식이 객체가 아니다.`);
}

function requireArray(value: unknown, fieldName: string): unknown[] {
  if (Array.isArray(value)) {
    return value;
  }
  throw new AdminResponseShapeError(`${fieldName} 형식이 배열이 아니다.`);
}

function requireString(value: unknown, fieldName: string): string {
  if (typeof value === "string") {
    return value;
  }
  throw new AdminResponseShapeError(`${fieldName} 형식이 문자열이 아니다.`);
}

function optionalString(value: unknown, fieldName: string): string | null {
  if (value === null) {
    return null;
  }
  return requireString(value, fieldName);
}

function requireNumber(value: unknown, fieldName: string): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  throw new AdminResponseShapeError(`${fieldName} 형식이 숫자가 아니다.`);
}

function requireBoolean(value: unknown, fieldName: string): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  throw new AdminResponseShapeError(`${fieldName} 형식이 boolean이 아니다.`);
}

function isAdminJsonValue(value: unknown): value is AdminJsonValue {
  if (
    value === null ||
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return true;
  }
  if (Array.isArray(value)) {
    return value.every(isAdminJsonValue);
  }
  if (value !== null && typeof value === "object") {
    return Object.values(value).every(isAdminJsonValue);
  }
  return false;
}

function extractErrorMessage(payload: unknown): string | null {
  if (
    payload !== null &&
    typeof payload === "object" &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  return null;
}
