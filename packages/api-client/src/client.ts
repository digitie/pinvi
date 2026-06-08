import { z } from 'zod';
import { ErrorEnvelopeSchema, SuccessEnvelopeSchema } from '@tripmate/schemas';

/** API 클라이언트 옵션 — Next.js / Expo가 어댑터 주입. */
export interface ApiClientOptions {
  baseUrl: string;
  /** 인증 토큰 fetch (cookie 기반이면 null 반환). */
  getAuthToken?: () => Promise<string | null>;
  onUnauthorized?: () => void;
  /** fetch override (테스트 / SSR 용도). */
  fetcher?: typeof fetch;
}

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
    public details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export interface ApiResponseMeta {
  cursor?: string | null;
  has_more?: boolean;
  total?: number;
  page?: number;
  limit?: number;
  version?: number;
}

export interface ApiEnvelope<T> {
  data: T;
  meta?: ApiResponseMeta;
}

export class ApiClient {
  constructor(private readonly opts: ApiClientOptions) {}

  private async fetch(path: string, init: RequestInit): Promise<Response> {
    const token = (await this.opts.getAuthToken?.()) ?? null;
    const fetcher = this.opts.fetcher ?? fetch;
    return fetcher(this.opts.baseUrl + path, {
      ...init,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init.headers,
      },
    });
  }

  async request<T>(
    path: string,
    init: RequestInit & { schema: z.ZodType<T> },
  ): Promise<T> {
    const envelope = await this.requestEnvelope(path, init);
    return envelope.data;
  }

  async requestEnvelope<T>(
    path: string,
    init: RequestInit & { schema: z.ZodType<T> },
  ): Promise<ApiEnvelope<T>> {
    const res = await this.fetch(path, init);

    if (res.status === 401) {
      this.opts.onUnauthorized?.();
    }

    const text = await res.text();
    const json: unknown = text ? JSON.parse(text) : {};

    if (!res.ok) {
      const parsed = ErrorEnvelopeSchema.safeParse(json);
      if (parsed.success) {
        throw new ApiError(
          parsed.data.error.code,
          parsed.data.error.message,
          res.status,
          parsed.data.error.details,
        );
      }
      throw new ApiError('INTERNAL_ERROR', `HTTP ${res.status}`, res.status);
    }

    // `data` 필드와 선택적 `meta` 필드 파싱
    const envelope = SuccessEnvelopeSchema(init.schema).safeParse(json);
    if (!envelope.success) {
      throw new ApiError(
        'RESPONSE_SHAPE_INVALID',
        `Response shape mismatch: ${envelope.error.message}`,
        res.status,
      );
    }
    return envelope.data;
  }

  async requestNoContent(path: string, init: RequestInit): Promise<void> {
    const res = await this.fetch(path, init);

    if (res.status === 401) {
      this.opts.onUnauthorized?.();
    }

    if (res.ok) {
      return;
    }

    const text = await res.text();
    const json: unknown = text ? JSON.parse(text) : {};
    const parsed = ErrorEnvelopeSchema.safeParse(json);
    if (parsed.success) {
      throw new ApiError(
        parsed.data.error.code,
        parsed.data.error.message,
        res.status,
        parsed.data.error.details,
      );
    }
    throw new ApiError('INTERNAL_ERROR', `HTTP ${res.status}`, res.status);
  }
}
