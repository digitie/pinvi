import { z } from "zod";

import { fetchApi } from "../shared/api-base";

export const registerUserInputSchema = z.object({
  email: z.string().trim().email("이메일 형식을 확인해 주세요."),
  password: z.string().min(8, "비밀번호는 8자 이상이어야 합니다.").max(128),
  nickname: z.string().trim().min(1, "닉네임을 입력해 주세요.").max(80),
  name: z.string().trim().min(1, "이름을 입력해 주세요.").max(80),
  birth_year_month: z.string().regex(/^[0-9]{6}$/).nullable(),
  gender: z.enum(["female", "male", "non_binary", "no_answer"]).nullable(),
  residence_sigungu_code: z.string().regex(/^[0-9]{10}$/).nullable(),
  tos_agreed: z.boolean(),
  privacy_agreed: z.boolean(),
  demographic_use_agreed: z.boolean(),
  location_use_agreed: z.boolean(),
  marketing_agreed: z.boolean(),
  consent_version: z.string().min(1).max(80),
});

const registeredUserSchema = z.object({
  id: z.string(),
  email: z.string(),
  nickname: z.string(),
  name: z.string(),
  account_status: z.string(),
  status: z.string(),
  system_role: z.string(),
  email_verification_required: z.boolean(),
  verification_email_dispatched: z.boolean(),
});

const registerUserResponseSchema = z.object({
  user: registeredUserSchema,
});

export type RegisterUserInput = z.infer<typeof registerUserInputSchema>;
export type RegisteredUser = z.infer<typeof registeredUserSchema>;
export type RegisterUserResponse = z.infer<typeof registerUserResponseSchema>;

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
  const requestInput = registerUserInputSchema.parse(input);
  const response = await fetchApi("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(requestInput),
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
  const result = registerUserResponseSchema.safeParse(payload);
  if (result.success) {
    return result.data;
  }
  const issue = result.error.issues[0];
  const path = issue?.path.length ? ` (${issue.path.join(".")})` : "";
  throw new SignupResponseShapeError(`가입 응답 형식이 올바르지 않다${path}.`);
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
