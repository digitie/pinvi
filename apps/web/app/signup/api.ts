import { fetchApi } from "../shared/api-base";

export type RegisterUserInput = {
  email: string;
  password: string;
  nickname: string;
  name: string;
  birth_year_month: string | null;
  gender: string | null;
  residence_sigungu_code: string | null;
};

export type RegisteredUser = {
  id: string;
  email: string;
  nickname: string;
  name: string;
  account_status: string;
  system_role: string;
  email_verification_required: boolean;
  verification_email_dispatched: boolean;
};

export type RegisterUserResponse = {
  user: RegisteredUser;
};

export class SignupApiError extends Error {
  status: number;
  payload: unknown;

  constructor(status: number, payload: unknown) {
    super(extractErrorMessage(payload) ?? `가입 요청 실패 (${status})`);
    this.name = "SignupApiError";
    this.status = status;
    this.payload = payload;
  }
}

export class SignupResponseShapeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SignupResponseShapeError";
  }
}

export async function registerUser(input: RegisterUserInput): Promise<RegisterUserResponse> {
  const response = await fetchApi("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  const payload = await readJsonPayload(response);

  if (!response.ok) {
    throw new SignupApiError(response.status, payload);
  }

  return parseRegisterUserResponse(payload);
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

function parseRegisterUserResponse(payload: unknown): RegisterUserResponse {
  const record = requireRecord(payload, "가입 응답");
  return { user: parseRegisteredUser(record.user) };
}

function parseRegisteredUser(payload: unknown): RegisteredUser {
  const record = requireRecord(payload, "가입 사용자 응답");
  return {
    id: requireString(record.id, "id"),
    email: requireString(record.email, "email"),
    nickname: requireString(record.nickname, "nickname"),
    name: requireString(record.name, "name"),
    account_status: requireString(record.account_status, "account_status"),
    system_role: requireString(record.system_role, "system_role"),
    email_verification_required: requireBoolean(
      record.email_verification_required,
      "email_verification_required",
    ),
    verification_email_dispatched: requireBoolean(
      record.verification_email_dispatched,
      "verification_email_dispatched",
    ),
  };
}

function requireRecord(value: unknown, context: string): Record<string, unknown> {
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  throw new SignupResponseShapeError(`${context} 형식이 객체가 아니다.`);
}

function requireString(value: unknown, fieldName: string): string {
  if (typeof value === "string") {
    return value;
  }
  throw new SignupResponseShapeError(`${fieldName} 형식이 문자열이 아니다.`);
}

function requireBoolean(value: unknown, fieldName: string): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  throw new SignupResponseShapeError(`${fieldName} 형식이 boolean이 아니다.`);
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
