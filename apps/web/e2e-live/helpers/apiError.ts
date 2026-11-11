/**
 * PinVi API error envelope reader for live specs (`docs/api/common.md` §2.2).
 *
 * Every non-2xx body is `{"error": {"code", "message", "details"?}}` — `core/errors.py` rewraps a
 * dict `HTTPException.detail` into `error`, so a spec never sees FastAPI's raw `detail`. Reading
 * `body.detail.code` (the shape inside the route) always yields `undefined` on the wire.
 *
 * No Playwright import, so vitest (tests/apiErrorEnvelope.test.ts) loads it directly.
 */
export interface ApiErrorBody {
  error?: { code?: unknown; message?: unknown; details?: unknown; reason?: unknown };
}

function str(v: unknown): string | undefined {
  return typeof v === 'string' ? v : undefined;
}

/** `error.code` of a PinVi error body, or `undefined` when the body is not an error envelope. */
export function apiErrorCode(body: unknown): string | undefined {
  return str((body as ApiErrorBody | null | undefined)?.error?.code);
}

/** `error.message` of a PinVi error body, or `undefined`. */
export function apiErrorMessage(body: unknown): string | undefined {
  return str((body as ApiErrorBody | null | undefined)?.error?.message);
}
