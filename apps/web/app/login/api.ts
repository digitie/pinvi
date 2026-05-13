import { z } from "zod";

import { fetchApi } from "../shared/api-base";

const nullableStringSchema = z.union([z.string(), z.number().transform(String)]).nullable();

const festivalMonthSummarySchema = z.object({
  month: z.number(),
  count: z.number(),
});

const festivalSummarySchema = z.object({
  id: z.string(),
  source_record_id: z.string(),
  festival_name: z.string(),
  venue_name: nullableStringSchema,
  event_start_date: nullableStringSchema,
  event_end_date: nullableStringSchema,
  event_status: z.string(),
  road_address: nullableStringSchema,
  jibun_address: nullableStringSchema,
  sigungu_code: nullableStringSchema,
  sido_code: nullableStringSchema,
  longitude: nullableStringSchema,
  latitude: nullableStringSchema,
  homepage_url: nullableStringSchema,
});

const festivalMonthlyResponseSchema = z.object({
  year: z.number(),
  month: z.number(),
  months: z.array(festivalMonthSummarySchema),
  festivals: z.array(festivalSummarySchema),
});

const authenticatedUserSchema = z.object({
  id: z.string(),
  email: z.string(),
  display_name: z.string().nullable(),
  nickname: z.string().nullable(),
  name: z.string().nullable(),
  account_status: z.string(),
  status: z.string(),
  system_role: z.string(),
  email_verified_at: z.string().nullable(),
  is_admin: z.boolean(),
  is_privileged: z.boolean(),
});

const userLoginResponseSchema = z.object({
  user: authenticatedUserSchema,
  token_type: z.string(),
  access_token_expires_at: z.string(),
  refresh_token_expires_at: z.string(),
});

export type FestivalMonthSummary = z.infer<typeof festivalMonthSummarySchema>;
export type FestivalSummary = z.infer<typeof festivalSummarySchema>;
export type FestivalMonthlyResponse = z.infer<typeof festivalMonthlyResponseSchema>;
export type AuthenticatedUser = z.infer<typeof authenticatedUserSchema>;
export type UserLoginResponse = z.infer<typeof userLoginResponseSchema>;

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
  return parseWithSchema(
    festivalMonthlyResponseSchema,
    payload,
    "월별 축제 응답",
    PublicFestivalShapeError,
  );
}

export async function loginUser(email: string, password: string): Promise<UserLoginResponse> {
  const response = await fetchApi("/auth/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ email, password }),
  });
  const payload = await readJsonPayload(response);
  if (!response.ok) {
    throw new AuthApiError(response.status, payload);
  }
  return parseWithSchema(userLoginResponseSchema, payload, "로그인 응답", AuthShapeError);
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

function parseWithSchema<T>(
  schema: z.ZodType<T>,
  payload: unknown,
  context: string,
  ErrorClass: new (message: string) => Error,
): T {
  const result = schema.safeParse(payload);
  if (result.success) {
    return result.data;
  }
  const issue = result.error.issues[0];
  const path = issue?.path.length ? ` (${issue.path.join(".")})` : "";
  throw new ErrorClass(`${context} 형식이 올바르지 않다${path}.`);
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
