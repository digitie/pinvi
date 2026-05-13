import { z } from "zod";

import { fetchApi } from "../shared/api-base";

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

const verifyEmailResponseSchema = z.object({
  status: z.string(),
  user: authenticatedUserSchema,
});

export type VerifyEmailResponse = z.infer<typeof verifyEmailResponseSchema>;

export class VerifyEmailApiError extends Error {
  status: number;
  payload: unknown;

  constructor(status: number, payload: unknown) {
    super(extractErrorMessage(payload) ?? `이메일 인증 실패 (${status})`);
    this.name = "VerifyEmailApiError";
    this.status = status;
    this.payload = payload;
  }
}

export class VerifyEmailShapeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "VerifyEmailShapeError";
  }
}

export async function verifyEmail(token: string): Promise<VerifyEmailResponse> {
  const response = await fetchApi("/auth/verify-email", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
  const payload = await readJsonPayload(response);
  if (!response.ok) {
    throw new VerifyEmailApiError(response.status, payload);
  }

  const result = verifyEmailResponseSchema.safeParse(payload);
  if (result.success) {
    return result.data;
  }
  const issue = result.error.issues[0];
  const path = issue?.path.length ? ` (${issue.path.join(".")})` : "";
  throw new VerifyEmailShapeError(`이메일 인증 응답 형식이 올바르지 않다${path}.`);
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
