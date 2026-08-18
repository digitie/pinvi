import { z } from 'zod';
import { ErrorEnvelopeSchema, SuccessEnvelopeSchema } from '@pinvi/schemas';

/** API 클라이언트 옵션 — Next.js / Expo가 어댑터 주입. */
export interface ApiClientOptions {
  baseUrl: string;
  /** 인증 토큰 fetch (cookie 기반이면 null 반환). */
  getAuthToken?: () => Promise<string | null>;
  onUnauthorized?: () => void;
  /** fetch override (테스트 / SSR 용도). */
  fetcher?: typeof fetch;
  /**
   * 요청 기본 타임아웃(ms). 0 이하면 끄고, 개별 호출은 `timeoutMs`로 덮어쓴다.
   * 응답이 오지 않는 요청이 UI를 영구 `저장 중`으로 잠그지 않게 하는 최후 방어선이다
   * (백업 복구처럼 분 단위인 호출은 호출부에서 늘린다).
   */
  timeoutMs?: number;
}

/** 기본 요청 타임아웃 — 사용자 대면 호출은 30초를 넘기면 실패로 본다. */
export const DEFAULT_REQUEST_TIMEOUT_MS = 30_000;

/** 개별 요청에서 기본 타임아웃을 덮어쓰는 옵션(0 이하 = 끄기). */
export interface RequestTimeoutOption {
  timeoutMs?: number;
}

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
    public details?: Record<string, unknown>,
    public retryAfterSeconds?: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export function isVersionConflictError(error: unknown): error is ApiError {
  return error instanceof ApiError && error.status === 409 && error.code === 'VERSION_CONFLICT';
}

function parseJson(text: string): unknown | null {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function nonJsonErrorMessage(text: string, status: number): string {
  const trimmed = text.trim();
  if (trimmed && !trimmed.startsWith('<')) return trimmed;
  return `요청에 실패했습니다. (HTTP ${status})`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function retryAfterSeconds(res: Response): number | undefined {
  const raw = res.headers.get('Retry-After');
  if (raw === null || !/^[0-9]+$/.test(raw)) return undefined;
  const value = Number(raw);
  return Number.isSafeInteger(value) && value >= 1 && value <= 300 ? value : undefined;
}

function fallbackApiError(
  json: unknown,
  text: string,
  status: number,
  retryAfter?: number,
): ApiError {
  const detail = isRecord(json) ? json.detail : null;

  if (typeof detail === 'string' && detail.trim()) {
    return new ApiError('HTTP_ERROR', detail.trim(), status, undefined, retryAfter);
  }

  if (isRecord(detail)) {
    const code = typeof detail.code === 'string' && detail.code ? detail.code : 'HTTP_ERROR';
    const message = typeof detail.message === 'string' ? detail.message.trim() : '';
    if (message) {
      return new ApiError(code, message, status, detail, retryAfter);
    }
  }

  return new ApiError(
    'HTTP_ERROR',
    nonJsonErrorMessage(text, status),
    status,
    undefined,
    retryAfter,
  );
}

export interface ApiResponseMeta {
  cursor?: string | null;
  has_more?: boolean | null;
  total?: number | null;
  page?: number | null;
  limit?: number | null;
  version?: number | null;
}

export interface ApiEnvelope<T> {
  data: T;
  meta?: ApiResponseMeta;
}

export class ApiClient {
  constructor(private readonly opts: ApiClientOptions) {}

  /**
   * 호출부 signal과 타임아웃을 합친다. `AbortSignal.any`/`AbortSignal.timeout`은 환경에 따라
   * 없을 수 있어 컨트롤러로 직접 엮는다. 타임아웃이 꺼져 있으면 호출부 signal을 그대로 쓴다.
   */
  private withTimeout(signal: AbortSignal | null | undefined, timeoutMs: number) {
    if (timeoutMs <= 0) return { signal: signal ?? undefined, done: () => {} };

    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);

    const abortFromCaller = () => controller.abort();
    if (signal) {
      if (signal.aborted) controller.abort();
      else signal.addEventListener('abort', abortFromCaller, { once: true });
    }

    return {
      signal: controller.signal,
      timedOut: () => timedOut,
      done: () => {
        clearTimeout(timer);
        signal?.removeEventListener('abort', abortFromCaller);
      },
    };
  }

  private async fetch(path: string, init: RequestInit & RequestTimeoutOption): Promise<Response> {
    const token = (await this.opts.getAuthToken?.()) ?? null;
    const fetcher = this.opts.fetcher ?? fetch;
    const { timeoutMs: perRequestTimeout, ...rest } = init;
    const timeoutMs = perRequestTimeout ?? this.opts.timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;
    const timeout = this.withTimeout(rest.signal, timeoutMs);

    try {
      return await fetcher(this.opts.baseUrl + path, {
        ...rest,
        ...(timeout.signal ? { signal: timeout.signal } : {}),
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...rest.headers,
        },
      });
    } catch (err) {
      // 타임아웃으로 끊긴 요청은 호출부 취소(AbortError)와 구분해 사용자에게 보이는 오류로 바꾼다.
      if (timeout.timedOut?.()) {
        throw new ApiError(
          'REQUEST_TIMEOUT',
          '요청이 시간 내에 끝나지 않았습니다. 네트워크 상태를 확인한 뒤 다시 시도해 주세요.',
          408,
        );
      }
      throw err;
    } finally {
      timeout.done();
    }
  }

  async request<T>(
    path: string,
    init: RequestInit & RequestTimeoutOption & { schema: z.ZodType<T> },
  ): Promise<T> {
    const envelope = await this.requestEnvelope(path, init);
    return envelope.data;
  }

  async requestEnvelope<T>(
    path: string,
    init: RequestInit & RequestTimeoutOption & { schema: z.ZodType<T> },
  ): Promise<ApiEnvelope<T>> {
    const res = await this.fetch(path, init);

    if (res.status === 401) {
      this.opts.onUnauthorized?.();
    }

    const text = await res.text();
    const json: unknown = text ? parseJson(text) : {};

    if (!res.ok) {
      const parsed = ErrorEnvelopeSchema.safeParse(json);
      if (parsed.success) {
        throw new ApiError(
          parsed.data.error.code,
          parsed.data.error.message,
          res.status,
          parsed.data.error.details,
          retryAfterSeconds(res),
        );
      }
      throw fallbackApiError(json, text, res.status, retryAfterSeconds(res));
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

  async requestNoContent(path: string, init: RequestInit & RequestTimeoutOption): Promise<void> {
    const res = await this.fetch(path, init);

    if (res.status === 401) {
      this.opts.onUnauthorized?.();
    }

    if (res.ok) {
      return;
    }

    const text = await res.text();
    const json: unknown = text ? parseJson(text) : {};
    const parsed = ErrorEnvelopeSchema.safeParse(json);
    if (parsed.success) {
      throw new ApiError(
        parsed.data.error.code,
        parsed.data.error.message,
        res.status,
        parsed.data.error.details,
        retryAfterSeconds(res),
      );
    }
    throw fallbackApiError(json, text, res.status, retryAfterSeconds(res));
  }
}
