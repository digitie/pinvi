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
  token_type: string;
  access_token_expires_at: string;
  refresh_token_expires_at: string;
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

export type AdminEntityKind = "users" | "features" | "trips" | "pois";

export type AdminEntityLink = {
  entity: AdminEntityKind;
  relation: string;
  id: string | null;
  label: string;
  query: Record<string, string>;
};

export type AdminEntityMapPoint = {
  latitude: number;
  longitude: number;
};

export type AdminEntityItem = {
  entity: AdminEntityKind;
  id: string;
  label: string;
  subtitle: string | null;
  status: string | null;
  fields: Record<string, AdminJsonValue>;
  links: AdminEntityLink[];
  map: AdminEntityMapPoint | null;
};

export type AdminEntityListResponse = {
  entity: AdminEntityKind;
  items: AdminEntityItem[];
  page: number;
  limit: number;
  total: number;
};

export type AdminEntityRelatedGroup = {
  label: string;
  entity: AdminEntityKind;
  query: Record<string, string>;
  count: number;
  sample: AdminEntityItem[];
};

export type AdminEntityDetailResponse = {
  entity: AdminEntityKind;
  item: AdminEntityItem;
  related: AdminEntityRelatedGroup[];
};

export type AdminEntityDeleteResponse = {
  entity: AdminEntityKind;
  id: string;
  status: string;
};

export type AdminEntityListQuery = {
  page: number;
  limit: number;
  search: string;
  filters: Record<string, string>;
};

export type AdminEntityUpsertInput = Record<string, AdminJsonValue>;

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

export async function fetchAdminEntityList(
  entity: AdminEntityKind,
  query: AdminEntityListQuery,
): Promise<AdminEntityListResponse> {
  const params = new URLSearchParams({
    page: String(query.page),
    limit: String(query.limit),
  });
  if (query.search.trim()) {
    params.set("search", query.search.trim());
  }
  for (const [key, value] of Object.entries(query.filters)) {
    if (value.trim()) {
      params.set(key, value.trim());
    }
  }
  return parseAdminEntityListResponse(
    await adminFetch(`/admin/entities/${entity}?${params.toString()}`),
  );
}

export async function fetchAdminEntityDetail(
  entity: AdminEntityKind,
  itemId: string,
): Promise<AdminEntityDetailResponse> {
  return parseAdminEntityDetailResponse(
    await adminFetch(`/admin/entities/${entity}/${encodeURIComponent(itemId)}`),
  );
}

export async function createAdminEntity(
  entity: AdminEntityKind,
  values: AdminEntityUpsertInput,
): Promise<AdminEntityDetailResponse> {
  return parseAdminEntityDetailResponse(
    await adminFetch(`/admin/entities/${entity}`, {
      method: "POST",
      body: JSON.stringify({ values }),
    }),
  );
}

export async function updateAdminEntity(
  entity: AdminEntityKind,
  itemId: string,
  values: AdminEntityUpsertInput,
): Promise<AdminEntityDetailResponse> {
  return parseAdminEntityDetailResponse(
    await adminFetch(`/admin/entities/${entity}/${encodeURIComponent(itemId)}`, {
      method: "PATCH",
      body: JSON.stringify({ values }),
    }),
  );
}

export async function deleteAdminEntity(
  entity: AdminEntityKind,
  itemId: string,
): Promise<AdminEntityDeleteResponse> {
  return parseAdminEntityDeleteResponse(
    await adminFetch(`/admin/entities/${entity}/${encodeURIComponent(itemId)}`, {
      method: "DELETE",
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
  return {
    user: parseAdminUser(record.user),
    token_type: requireString(record.token_type, "token_type"),
    access_token_expires_at: requireString(
      record.access_token_expires_at,
      "access_token_expires_at",
    ),
    refresh_token_expires_at: requireString(
      record.refresh_token_expires_at,
      "refresh_token_expires_at",
    ),
  };
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

function parseAdminEntityListResponse(payload: unknown): AdminEntityListResponse {
  const record = requireRecord(payload, "관리자 엔티티 목록 응답");
  return {
    entity: parseAdminEntityKind(record.entity),
    items: requireArray(record.items, "items").map(parseAdminEntityItem),
    page: requireNumber(record.page, "page"),
    limit: requireNumber(record.limit, "limit"),
    total: requireNumber(record.total, "total"),
  };
}

function parseAdminEntityDetailResponse(payload: unknown): AdminEntityDetailResponse {
  const record = requireRecord(payload, "관리자 엔티티 상세 응답");
  return {
    entity: parseAdminEntityKind(record.entity),
    item: parseAdminEntityItem(record.item),
    related: requireArray(record.related, "related").map(parseAdminEntityRelatedGroup),
  };
}

function parseAdminEntityDeleteResponse(payload: unknown): AdminEntityDeleteResponse {
  const record = requireRecord(payload, "관리자 엔티티 삭제 응답");
  return {
    entity: parseAdminEntityKind(record.entity),
    id: requireString(record.id, "id"),
    status: requireString(record.status, "status"),
  };
}

function parseAdminEntityRelatedGroup(payload: unknown): AdminEntityRelatedGroup {
  const record = requireRecord(payload, "관리자 엔티티 연관 응답");
  return {
    label: requireString(record.label, "label"),
    entity: parseAdminEntityKind(record.entity),
    query: parseStringRecord(record.query, "query"),
    count: requireNumber(record.count, "count"),
    sample: requireArray(record.sample, "sample").map(parseAdminEntityItem),
  };
}

function parseAdminEntityItem(payload: unknown): AdminEntityItem {
  const record = requireRecord(payload, "관리자 엔티티 항목 응답");
  const mapValue = record.map;
  return {
    entity: parseAdminEntityKind(record.entity),
    id: requireString(record.id, "id"),
    label: requireString(record.label, "label"),
    subtitle: optionalString(record.subtitle, "subtitle"),
    status: optionalString(record.status, "status"),
    fields: parseJsonRecord(record.fields, "fields"),
    links: requireArray(record.links, "links").map(parseAdminEntityLink),
    map: mapValue === null ? null : parseAdminEntityMapPoint(mapValue),
  };
}

function parseAdminEntityLink(payload: unknown): AdminEntityLink {
  const record = requireRecord(payload, "관리자 엔티티 링크 응답");
  return {
    entity: parseAdminEntityKind(record.entity),
    relation: requireString(record.relation, "relation"),
    id: optionalString(record.id, "id"),
    label: requireString(record.label, "label"),
    query: parseStringRecord(record.query, "query"),
  };
}

function parseAdminEntityMapPoint(payload: unknown): AdminEntityMapPoint {
  const record = requireRecord(payload, "관리자 엔티티 지도 좌표 응답");
  return {
    latitude: requireNumber(record.latitude, "latitude"),
    longitude: requireNumber(record.longitude, "longitude"),
  };
}

function parseAdminEntityKind(payload: unknown): AdminEntityKind {
  const value = requireString(payload, "entity");
  if (value === "users" || value === "features" || value === "trips" || value === "pois") {
    return value;
  }
  throw new AdminResponseShapeError(`지원하지 않는 관리자 엔티티다: ${value}`);
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

function parseJsonRecord(value: unknown, fieldName: string): Record<string, AdminJsonValue> {
  const record = requireRecord(value, fieldName);
  const parsed: Record<string, AdminJsonValue> = {};
  for (const [key, item] of Object.entries(record)) {
    if (!isAdminJsonValue(item)) {
      throw new AdminResponseShapeError(`${fieldName}.${key} 값이 JSON 형태가 아니다.`);
    }
    parsed[key] = item;
  }
  return parsed;
}

function parseStringRecord(value: unknown, fieldName: string): Record<string, string> {
  const record = requireRecord(value, fieldName);
  const parsed: Record<string, string> = {};
  for (const [key, item] of Object.entries(record)) {
    parsed[key] = requireString(item, `${fieldName}.${key}`);
  }
  return parsed;
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
