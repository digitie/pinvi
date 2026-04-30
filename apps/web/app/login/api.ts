import { fetchApi } from "../shared/api-base";

export type FestivalMonthSummary = {
  month: number;
  count: number;
};

export type FestivalSummary = {
  id: string;
  source_record_id: string;
  festival_name: string;
  venue_name: string | null;
  event_start_date: string | null;
  event_end_date: string | null;
  event_status: string;
  road_address: string | null;
  jibun_address: string | null;
  sigungu_code: string | null;
  sido_code: string | null;
  longitude: string | null;
  latitude: string | null;
  homepage_url: string | null;
};

export type FestivalMonthlyResponse = {
  year: number;
  month: number;
  months: FestivalMonthSummary[];
  festivals: FestivalSummary[];
};

export type AuthenticatedUser = {
  id: string;
  email: string;
  display_name: string | null;
  nickname: string | null;
  name: string | null;
  account_status: string;
  system_role: string;
  email_verified_at: string | null;
  is_admin: boolean;
  is_privileged: boolean;
};

export type UserLoginResponse = {
  user: AuthenticatedUser;
};

export class PublicFestivalApiError extends Error {
  status: number;
  payload: unknown;

  constructor(status: number, payload: unknown) {
    super(extractErrorMessage(payload) ?? `축제 정보를 불러오지 못했다. (${status})`);
    this.name = "PublicFestivalApiError";
    this.status = status;
    this.payload = payload;
  }
}

export class PublicFestivalShapeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PublicFestivalShapeError";
  }
}

export class AuthApiError extends Error {
  status: number;
  payload: unknown;

  constructor(status: number, payload: unknown) {
    super(extractErrorMessage(payload) ?? `로그인 요청 실패 (${status})`);
    this.name = "AuthApiError";
    this.status = status;
    this.payload = payload;
  }
}

export class AuthShapeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AuthShapeError";
  }
}

export async function fetchFestivalMonthly(
  year: number,
  month: number,
): Promise<FestivalMonthlyResponse> {
  const params = new URLSearchParams({
    year: String(year),
    month: String(month),
    limit: "12",
  });

  const response = await fetchApi(`/public/festivals/monthly?${params.toString()}`);
  const payload = await readJsonPayload(response);
  if (!response.ok) {
    throw new PublicFestivalApiError(response.status, payload);
  }
  return parseFestivalMonthlyResponse(payload);
}

export async function loginUser(email: string, password: string): Promise<UserLoginResponse> {
  const response = await fetchApi("/auth/login", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ email, password }),
  });
  const payload = await readJsonPayload(response);
  if (!response.ok) {
    throw new AuthApiError(response.status, payload);
  }
  return parseUserLoginResponse(payload);
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

function parseFestivalMonthlyResponse(payload: unknown): FestivalMonthlyResponse {
  const record = requireRecord(payload, "월별 축제 응답");
  return {
    year: requireNumber(record.year, "year"),
    month: requireNumber(record.month, "month"),
    months: requireArray(record.months, "months").map(parseMonthSummary),
    festivals: requireArray(record.festivals, "festivals").map(parseFestivalSummary),
  };
}

function parseMonthSummary(payload: unknown): FestivalMonthSummary {
  const record = requireRecord(payload, "월 요약");
  return {
    month: requireNumber(record.month, "month"),
    count: requireNumber(record.count, "count"),
  };
}

function parseFestivalSummary(payload: unknown): FestivalSummary {
  const record = requireRecord(payload, "축제 요약");
  return {
    id: requireString(record.id, "id"),
    source_record_id: requireString(record.source_record_id, "source_record_id"),
    festival_name: requireString(record.festival_name, "festival_name"),
    venue_name: optionalString(record.venue_name, "venue_name"),
    event_start_date: optionalString(record.event_start_date, "event_start_date"),
    event_end_date: optionalString(record.event_end_date, "event_end_date"),
    event_status: requireString(record.event_status, "event_status"),
    road_address: optionalString(record.road_address, "road_address"),
    jibun_address: optionalString(record.jibun_address, "jibun_address"),
    sigungu_code: optionalString(record.sigungu_code, "sigungu_code"),
    sido_code: optionalString(record.sido_code, "sido_code"),
    longitude: optionalString(record.longitude, "longitude"),
    latitude: optionalString(record.latitude, "latitude"),
    homepage_url: optionalString(record.homepage_url, "homepage_url"),
  };
}

function parseUserLoginResponse(payload: unknown): UserLoginResponse {
  const record = requireRecord(payload, "로그인 응답");
  return { user: parseAuthenticatedUser(record.user) };
}

function parseAuthenticatedUser(payload: unknown): AuthenticatedUser {
  const record = requireRecord(payload, "로그인 사용자 응답");
  return {
    id: requireString(record.id, "id"),
    email: requireString(record.email, "email"),
    display_name: optionalString(record.display_name, "display_name"),
    nickname: optionalString(record.nickname, "nickname"),
    name: optionalString(record.name, "name"),
    account_status: requireString(record.account_status, "account_status"),
    system_role: requireString(record.system_role, "system_role"),
    email_verified_at: optionalString(record.email_verified_at, "email_verified_at"),
    is_admin: requireBoolean(record.is_admin, "is_admin"),
    is_privileged: requireBoolean(record.is_privileged, "is_privileged"),
  };
}

function requireRecord(value: unknown, context: string): Record<string, unknown> {
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  throw new PublicFestivalShapeError(`${context} 형식이 객체가 아니다.`);
}

function requireArray(value: unknown, fieldName: string): unknown[] {
  if (Array.isArray(value)) {
    return value;
  }
  throw new PublicFestivalShapeError(`${fieldName} 형식이 배열이 아니다.`);
}

function requireNumber(value: unknown, fieldName: string): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  throw new PublicFestivalShapeError(`${fieldName} 형식이 숫자가 아니다.`);
}

function requireBoolean(value: unknown, fieldName: string): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  throw new AuthShapeError(`${fieldName} 형식이 boolean이 아니다.`);
}

function requireString(value: unknown, fieldName: string): string {
  if (typeof value === "string") {
    return value;
  }
  throw new PublicFestivalShapeError(`${fieldName} 형식이 문자열이 아니다.`);
}

function optionalString(value: unknown, fieldName: string): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number") {
    return String(value);
  }
  throw new PublicFestivalShapeError(`${fieldName} 형식이 문자열이 아니다.`);
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
