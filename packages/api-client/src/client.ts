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
   * 요청 기본 타임아웃(ms). 0 이하면 끈다. 개별 호출은 `timeoutMs`로 덮어쓴다.
   *
   * 응답이 오지 않는 요청이 UI를 영구 `저장 중`으로 잠그지 않게 하는 최후 방어선이다.
   * 타이머는 **본문(body) 소비가 끝날 때까지** 살아 있고(헤더만 오고 스트림이 멈추는 경우도 덮는다),
   * 호출부가 넘긴 AbortSignal도 그 시점까지 계속 전파된다(T-316 요청 수명 계약).
   */
  timeoutMs?: number;
}

/** 사용자 대면 호출의 기본 요청 예산. 장시간 admin 작업은 호출부에서 `timeoutMs: 0`으로 끈다. */
export const DEFAULT_REQUEST_TIMEOUT_MS = 30_000;

/** 타임아웃으로 끊긴 요청의 코드. 서버가 확정한 4xx와 구분하기 위해 status는 0이다. */
export const REQUEST_TIMEOUT_CODE = 'REQUEST_TIMEOUT';

/** 요청 단위 옵션 — 타임아웃 덮어쓰기(0이면 끄기). */
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

/**
 * 클라이언트가 시간 예산으로 끊은 요청인가.
 *
 * 서버가 **확정한** 4xx(멱등 키를 폐기해도 되는 terminal outcome)와 반드시 구분해야 한다 —
 * 타임아웃은 서버가 그 요청을 끝까지 처리했을 수도 있는 미확정 상태다. 그래서 status를 0으로 둔다
 * (408을 쓰면 `status < 500` 규칙을 쓰는 호출부가 terminal로 오분류해 비멱등 요청을 중복 실행한다).
 */
export function isRequestTimeoutError(error: unknown): error is ApiError {
  return error instanceof ApiError && error.code === REQUEST_TIMEOUT_CODE && error.status === 0;
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

/**
 * 호출부 signal + 타임아웃을 하나의 파생 signal로 엮는다.
 *
 * `AbortSignal.any`/`AbortSignal.timeout`은 런타임(구형 브라우저·jsdom)에 따라 없을 수 있어 직접 만든다.
 * `settle()`은 **본문 소비까지 끝난 뒤**에 호출해야 한다 — 헤더에서 풀면 body 스트림이 멈춘 요청을
 * 놓치고, 호출부 취소도 그 시점 이후로는 전파되지 않는다.
 */
function linkAbort(signal: AbortSignal | null | undefined, timeoutMs: number) {
  if (timeoutMs <= 0 && !signal) {
    return { signal: undefined, timedOut: () => false, settle: () => {} };
  }

  const controller = new AbortController();
  let timedOut = false;

  const timer =
    timeoutMs > 0
      ? setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, timeoutMs)
      : null;

  const abortFromCaller = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener('abort', abortFromCaller);
  }

  return {
    signal: controller.signal,
    timedOut: () => timedOut,
    settle: () => {
      if (timer !== null) clearTimeout(timer);
      signal?.removeEventListener('abort', abortFromCaller);
    },
  };
}

function requestTimeoutError(): ApiError {
  return new ApiError(
    REQUEST_TIMEOUT_CODE,
    '요청이 시간 내에 끝나지 않았습니다. 네트워크 상태를 확인한 뒤 다시 시도해 주세요.',
    // status 0 = "서버가 확정하지 않음". 4xx로 두면 terminal outcome으로 오분류된다.
    0,
  );
}

export class ApiClient {
  constructor(private readonly opts: ApiClientOptions) {}

  private resolveTimeout(perRequest: number | undefined): number {
    return perRequest ?? this.opts.timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;
  }

  private async fetch(
    path: string,
    init: RequestInit & RequestTimeoutOption,
    link: ReturnType<typeof linkAbort>,
  ): Promise<Response> {
    const token = (await this.opts.getAuthToken?.()) ?? null;
    const fetcher = this.opts.fetcher ?? fetch;
    const { timeoutMs: _ignored, signal: _callerSignal, ...rest } = init;
    return fetcher(this.opts.baseUrl + path, {
      ...rest,
      ...(link.signal ? { signal: link.signal } : {}),
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
    init: RequestInit & RequestTimeoutOption & { schema: z.ZodType<T> },
  ): Promise<T> {
    const envelope = await this.requestEnvelope(path, init);
    return envelope.data;
  }

  async requestEnvelope<T>(
    path: string,
    init: RequestInit & RequestTimeoutOption & { schema: z.ZodType<T> },
  ): Promise<ApiEnvelope<T>> {
    const link = linkAbort(init.signal, this.resolveTimeout(init.timeoutMs));
    let res: Response;
    let text: string;
    try {
      res = await this.fetch(path, init, link);

      if (res.status === 401) {
        this.opts.onUnauthorized?.();
      }

      // 본문까지 읽은 뒤에야 타이머를 푼다(헤더만 오고 멈춘 스트림도 예산 안에 들어온다).
      text = await res.text();
    } catch (err) {
      if (link.timedOut()) throw requestTimeoutError();
      throw err;
    } finally {
      link.settle();
    }

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
    const link = linkAbort(init.signal, this.resolveTimeout(init.timeoutMs));
    let res: Response;
    let text: string;
    try {
      res = await this.fetch(path, init, link);

      if (res.status === 401) {
        this.opts.onUnauthorized?.();
      }

      if (res.ok) {
        return;
      }

      text = await res.text();
    } catch (err) {
      if (link.timedOut()) throw requestTimeoutError();
      throw err;
    } finally {
      link.settle();
    }

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
