/**
 * NTF (notify) area — local helpers shared by the notify specs.
 *
 * Everything here builds on the integrator's `../helpers/live` contract. Nothing
 * in this file prints, logs or attaches a token, password or chat id. The only
 * Telegram-related env the specs read is listed in `telegramEnv()`.
 *
 * Source facts (PinVi main 620b6046+):
 *  - apps/web/app/(app)/settings/telegram/page.tsx   (settings UI, testids)
 *  - apps/web/components/trips/TripTelegramTargets.tsx (trip Share tab section)
 *  - apps/api/app/api/v1/telegram_targets.py, trip_telegram_targets.py
 *  - apps/api/app/services/telegram_targets.py (verify, ≤3 per trip, soft delete)
 *  - apps/api/app/services/telegram_notify.py / telegram_outbox.py (drain worker 5s)
 *  - apps/api/app/middleware/api_call_logging.py (provider=telegram, token masked)
 */
import { expect, type Locator, type Page, type TestInfo } from '@playwright/test';
import { apiBaseURL, e2ePrefix, isMobile, withRateLimitRetry } from './live';

export const TARGETS_PATH = '/users/me/telegram-targets';

/** Labels we create always carry the `[e2e]` prefix so sweeps never touch real targets. */
export const e2eLabel = (suffix: string) => `${e2ePrefix} ${suffix}`;

export interface TelegramEnv {
  /** Dedicated TEST chat that the PinVi prod bot is a member of. Optional. */
  chatId: string | undefined;
  /** Dedicated chat from which the PinVi prod bot was REMOVED (bot_forbidden). Optional. */
  forbiddenChatId: string | undefined;
}

export function telegramEnv(): TelegramEnv {
  return {
    chatId: process.env.PINVI_E2E_TELEGRAM_CHAT_ID?.trim() || undefined,
    forbiddenChatId: process.env.PINVI_E2E_TELEGRAM_FORBIDDEN_CHAT_ID?.trim() || undefined,
  };
}

/**
 * Chat-dependent cases are `blocked` until the owner provisions the test chat.
 * We skip with an explicit message instead of failing so the rest of the suite
 * still reports (credentials, by contrast, fail fast inside loginAsUser/Admin).
 */
export function requireTestChat(test: { skip: (c: boolean, d: string) => void }): string {
  const { chatId } = telegramEnv();
  test.skip(!chatId, 'PINVI_E2E_TELEGRAM_CHAT_ID 미설정 — 이 케이스는 blocked (README §preconditions)');
  return chatId as string;
}

/** 390x844 project detection by viewport (shared `isMobile`). */
export const isMobileProject = (info: TestInfo) => isMobile(info);

/** Bogus chat id that cannot exist — getChat returns 400 "chat not found" → invalid_chat (422). */
export const BOGUS_CHAT_ID = '-1009999999999999';

export interface TelegramTargetDto {
  id: string;
  telegram_chat_id: string;
  telegram_chat_type: string | null;
  telegram_label: string | null;
  title_snapshot: string | null;
  is_default: boolean;
  is_enabled: boolean;
  last_verified_at: string | null;
  last_send_status: string | null;
  created_at: string;
}

/**
 * The web app talks to the API with cookie auth (apps/web/lib/api.ts) at
 * NEXT_PUBLIC_PINVI_API_URL, which we do not know on prod. We derive the API base
 * from the first targets list request the settings page makes, then reuse
 * `page.request` (shares the browser context cookies) for state checks and sweeps.
 */
export async function resolveApiBase(page: Page): Promise<string> {
  const base = await apiBaseURL(page);
  await page.goto('/settings/telegram');
  await expect(page.getByTestId('telegram-chat-id')).toBeVisible({ timeout: 30_000 });
  return base;
}

export async function listTargets(page: Page, apiBase: string): Promise<TelegramTargetDto[]> {
  const res = await withRateLimitRetry(`GET ${TARGETS_PATH}`, () => page.request.get(apiBase + TARGETS_PATH));
  expect(res.ok(), `GET ${TARGETS_PATH} → HTTP ${res.status()}`).toBeTruthy();
  const body = (await res.json()) as { data: TelegramTargetDto[] };
  return body.data;
}

/** Deletes every target of the CURRENT user whose label starts with `[e2e]`. Never touches others. */
export async function sweepE2eTargets(page: Page, apiBase: string): Promise<number> {
  const rows = await listTargets(page, apiBase);
  let n = 0;
  for (const t of rows) {
    if (!t.telegram_label?.startsWith(e2ePrefix)) continue;
    const res = await withRateLimitRetry(`DELETE ${TARGETS_PATH}`, () => page.request.delete(`${apiBase}${TARGETS_PATH}/${t.id}`));
    if (res.ok() || res.status() === 404) n += 1;
  }
  return n;
}

/**
 * Registering an `[e2e]` target as default clears the default flag of whatever target the account
 * already has, and the sweep cannot give it back. Skip default-registering cases while a real
 * (non-`[e2e]`) default target exists so the account's own setting is never changed.
 */
export async function skipIfRealDefaultTarget(
  test: { skip: (c: boolean, d: string) => void },
  page: Page,
  apiBase: string,
): Promise<void> {
  const rows = await listTargets(page, apiBase);
  const realDefault = rows.some((t) => t.is_default && !t.telegram_label?.startsWith(e2ePrefix));
  test.skip(realDefault, '계정에 실제(non-[e2e]) 기본 Telegram 대상이 있어 기본 지정 케이스를 건너뛴다(설정 보존)');
}

/** The settings list (`<ul aria-label="연결된 Telegram 대상">`) and the row for one label. */
export const targetsList = (page: Page): Locator =>
  page.getByRole('list', { name: '연결된 Telegram 대상' });

export const targetRow = (page: Page, label: string): Locator =>
  targetsList(page).getByRole('listitem').filter({ hasText: label });

/**
 * Registers a target through the settings form and waits for the POST response.
 * Returns the raw POST response status + parsed body so callers can branch on
 * verify outcome (prod bot token set → getChat runs; unset → persisted as 미검증).
 */
export async function registerTargetViaForm(
  page: Page,
  opts: { chatId: string; label: string; isDefault?: boolean },
): Promise<{ status: number; data?: TelegramTargetDto; code?: string; message?: string }> {
  await page.getByTestId('telegram-chat-id').fill(opts.chatId);
  await page.getByTestId('telegram-label').fill(opts.label);
  const checkbox = page.getByTestId('telegram-default');
  const wantDefault = opts.isDefault ?? true;
  if ((await checkbox.isChecked()) !== wantDefault) await checkbox.click();

  const [res] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith(TARGETS_PATH) && r.request().method() === 'POST'),
    page.getByTestId('telegram-create').click(),
  ]);
  const status = res.status();
  const json = (await res.json().catch(() => ({}))) as {
    data?: TelegramTargetDto;
    detail?: { code?: string; message?: string };
    code?: string;
    message?: string;
  };
  return {
    status,
    data: json.data,
    code: json.detail?.code ?? json.code,
    message: json.detail?.message ?? json.message,
  };
}

/** `[e2e]`-prefixed trip title with the case id, unique per run. */
export const tripTitle = (caseId: string) => `${e2ePrefix} ${caseId} ${Date.now()}`;

/** ISO date `days` from today (local), for trip date inputs. */
export function isoDateFromToday(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Korean date as `telegram_messages._format_date` renders it: `M월 D일` (no zero padding). */
export function koreanMonthDay(iso: string): string {
  const [, m, d] = iso.split('-').map(Number);
  return `${m}월 ${d}일`;
}

export interface AdminApiCallRow {
  log_id: string | number;
  provider: string;
  endpoint: string;
  status_code: number | null;
  occurred_at: string;
}

/**
 * Admin-side delivery evidence: `app.api_call_log` rows for provider=telegram.
 * The admin page (`/admin/api-calls`) applies filters only on submit; we capture
 * the JSON of the request it makes rather than parsing the rendered table.
 * The bot token is masked in `endpoint` by the API (`/bot<id>:*** /sendMessage`).
 */
export async function adminTelegramCalls(page: Page): Promise<AdminApiCallRow[]> {
  await page.goto('/admin/api-calls');
  await page.getByTestId('admin-api-calls-provider').fill('telegram');
  const [res] = await Promise.all([
    page.waitForResponse(
      (r) => /\/admin\/api-calls\?/.test(r.url()) && r.url().includes('provider=telegram'),
    ),
    page.getByTestId('admin-api-calls-submit').click(),
  ]);
  expect(res.ok(), `GET /admin/api-calls → HTTP ${res.status()}`).toBeTruthy();
  const body = (await res.json()) as { data: AdminApiCallRow[] };
  return body.data;
}

/**
 * Polls the admin api-call log until a `sendMessage` row with HTTP 200 appears
 * whose `occurred_at` is at/after `sinceIso`. Outbox drain runs every 5s
 * (pinvi_telegram_outbox_drain_interval_seconds); 45s budget covers one retry
 * slot plus admin page latency.
 */
export async function waitForTelegramSendSince(
  page: Page,
  sinceIso: string,
  opts: { timeoutMs?: number; method?: 'sendMessage' | 'getChat' } = {},
): Promise<AdminApiCallRow> {
  const deadline = Date.now() + (opts.timeoutMs ?? 45_000);
  const method = opts.method ?? 'sendMessage';
  const since = new Date(sinceIso).getTime();
  for (;;) {
    const rows = await adminTelegramCalls(page);
    const hit = rows.find(
      (r) =>
        r.endpoint.includes(`/${method}`) &&
        r.status_code === 200 &&
        new Date(r.occurred_at).getTime() >= since,
    );
    if (hit) return hit;
    if (Date.now() > deadline) {
      throw new Error(`telegram ${method} 200 row not found in admin api-call log within budget`);
    }
    await page.waitForTimeout(5_000);
  }
}
