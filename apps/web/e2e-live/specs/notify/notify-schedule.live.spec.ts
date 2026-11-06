/**
 * NTF — 일정 전송(#636)·기상특보 동의(#637)·KST 일간/주간 브리프 설정(#638). PR688/689.
 * Cases: NTF-018, 019, 020, 027, 028.
 *
 * UI: apps/web/components/trips/TelegramNotificationPreferences.tsx (설정 > Telegram '예약 알림'),
 *     TripTelegramTargets.tsx ('알람으로 보내기', data-testid telegram-send-itinerary),
 *     TelegramNotificationHistory.tsx ('최근 발송 내역').
 * API: apps/api/app/api/v1/telegram_notifications.py
 *   - GET/PUT /users/me/telegram-notification-preferences (사용자 전역 — 테스트 전 값을 보존·복원)
 *   - POST /trips/{id}/telegram/send (202, request_id 멱등, 연결 대상 없으면 422)
 *   - GET /users/me/telegram-notifications?trip_id=
 *
 * 예약 회차(일간/주간)와 실제 공식 특보 발송은 Dagster planner·공식 발표에 의존해 여기서 유발하지 않는다
 * (NTF-029/030 manual). 예약 시각은 KST 23:59 로 두고(현재 시각 이후) 끝나면 원래 설정으로 되돌린다.
 * chat id·token 은 출력하지 않는다(boolean 비교만).
 */
import { randomUUID } from 'node:crypto';
import { expect, test, type Page } from '@playwright/test';
import {
  createTrip,
  deleteTrip,
  loginAsUser,
  openTripTab,
  shot,
  withRateLimitRetry,
} from '../../helpers/live';
import {
  e2eLabel,
  isMobileProject,
  isoDateFromToday,
  listTargets,
  registerTargetViaForm,
  requireTestChat,
  resolveApiBase,
  sweepE2eTargets,
  tripTitle,
} from '../../helpers/notify';

const PREFS_PATH = '/users/me/telegram-notification-preferences';

interface Preferences {
  weather_enabled: boolean;
  daily_enabled: boolean;
  weekly_enabled: boolean;
  send_time: string;
  weekly_day: number;
  weekly_target_id: string | null;
}

interface NotificationDto {
  id: string;
  category: string;
  trip_ids: string[];
  deliveries: {
    target_id: string | null;
    status: string;
    sent_chunks: number;
    total_chunks: number;
    error_code: string | null;
  }[];
}

async function getPrefs(page: Page, apiBase: string): Promise<Preferences> {
  const res = await withRateLimitRetry(`GET ${PREFS_PATH}`, () =>
    page.request.get(apiBase + PREFS_PATH),
  );
  expect(res.ok(), `GET ${PREFS_PATH} → HTTP ${res.status()}`).toBeTruthy();
  return ((await res.json()) as { data: Preferences }).data;
}

async function putPrefs(page: Page, apiBase: string, body: Preferences): Promise<number> {
  const res = await withRateLimitRetry(`PUT ${PREFS_PATH}`, () =>
    page.request.put(apiBase + PREFS_PATH, { data: body }),
  );
  return res.status();
}

/**
 * 예약 시각. planner 는 "KST 현재 HH:MM ≥ send_time" 이면 그날 회차를 바로 보낸다(늦게 켜면 즉시 따라잡기).
 * 저장한 예약이 테스트 중 회차에 걸리지 않게 그날의 마지막 분을 쓰고, 그 경계 30분 안에서는 건너뛴다.
 */
const SAFE_SEND_TIME = '23:59';
function nearKstMidnight(): boolean {
  const kst = new Date(Date.now() + 9 * 3_600_000);
  return kst.getUTCHours() === 23 && kst.getUTCMinutes() >= 30;
}

const prefsForm = (page: Page) => page.getByTestId('telegram-notification-preferences');

async function savePrefsViaForm(page: Page): Promise<number> {
  const [res] = await Promise.all([
    page.waitForResponse((r) => r.request().method() === 'PUT' && r.url().endsWith(PREFS_PATH)),
    prefsForm(page).getByRole('button', { name: '예약 설정 저장' }).click(),
  ]);
  return res.status();
}

const tripSection = (page: Page) => page.getByTestId('trip-telegram-targets');

async function openShareTab(page: Page, tripId: string): Promise<void> {
  await page.goto(`/trips/${tripId}`);
  await openTripTab(page, '공유');
  await expect(
    tripSection(page).getByRole('heading', { name: 'Telegram 알림 대상' }),
  ).toBeVisible();
  await expect(tripSection(page).getByText('불러오는 중…')).toHaveCount(0);
}

test.describe('NTF 예약·일정 전송', () => {
  let apiBase = '';
  let original: Preferences | null = null;
  let tripId: string | null = null;

  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
    apiBase = await resolveApiBase(page); // lands on /settings/telegram
    await sweepE2eTargets(page, apiBase);
    test.skip(
      nearKstMidnight(),
      'KST 23:30 이후 — 예약 시각 경계에서 실제 회차가 나갈 수 있어 건너뛴다',
    );
    original = await getPrefs(page, apiBase);
  });

  test.afterEach(async ({ page }) => {
    if (tripId) await deleteTrip(page, tripId).catch(() => undefined);
    tripId = null;
    if (original) {
      // 원래 주간 대상이 이번에 지운 [e2e] 대상일 수는 없다(시작 전에 sweep 했다).
      await putPrefs(page, apiBase, original).catch(() => undefined);
    }
    original = null;
    await sweepE2eTargets(page, apiBase).catch(() => undefined);
  });

  test('NTF-018 기상특보 동의 — 기본 안내, 켜고 저장·reload 보존, 끄기 저장', async ({
    page,
  }, info) => {
    await page.reload();
    const form = prefsForm(page);
    await expect(form).toBeVisible();
    await expect(page.getByText('한국 표준시(KST) 기준입니다.')).toBeVisible();
    await expect(page.getByText('현재 안전 상태를 보장하지 않습니다.')).toBeVisible();
    const weather = form.getByLabel('여행 중 기상 특보 발표');
    await expect(weather).toBeChecked({ checked: original!.weather_enabled });

    if (!original!.weather_enabled) await weather.check();
    await form.getByLabel('발송 시각 (KST)').fill(SAFE_SEND_TIME);
    expect(await savePrefsViaForm(page)).toBe(200);
    await expect(form.getByRole('status')).toHaveText('예약 설정을 저장했습니다.');
    await page.reload();
    await expect(prefsForm(page).getByLabel('여행 중 기상 특보 발표')).toBeChecked();
    expect((await getPrefs(page, apiBase)).weather_enabled).toBe(true);
    await shot(page, 'NTF-018', isMobileProject(info) ? 'mobile-weather-on' : 'weather-on');

    await prefsForm(page).getByLabel('여행 중 기상 특보 발표').uncheck();
    expect(await savePrefsViaForm(page)).toBe(200);
    expect((await getPrefs(page, apiBase)).weather_enabled).toBe(false);
  });

  test('NTF-019 일간·주간 브리프 설정 — 시각·요일 저장 보존, 주간은 대상 필수(UI·API)', async ({
    page,
  }) => {
    await page.reload();
    const form = prefsForm(page);
    const time = SAFE_SEND_TIME;
    await form.getByLabel('일간 브리프').check();
    await form.getByLabel('발송 시각 (KST)').fill(time);
    await form.getByLabel('주간 요약 요일').selectOption({ label: '금요일' });
    if (await form.getByLabel('주간 여행 요약').isChecked())
      await form.getByLabel('주간 여행 요약').uncheck();
    expect(await savePrefsViaForm(page)).toBe(200);
    await page.reload();
    const saved = await getPrefs(page, apiBase);
    expect(saved).toMatchObject({
      daily_enabled: true,
      weekly_enabled: false,
      send_time: time,
      weekly_day: 4,
      weekly_target_id: null,
    });
    await expect(prefsForm(page).getByLabel('일간 브리프')).toBeChecked();
    await expect(prefsForm(page).getByLabel('발송 시각 (KST)')).toHaveValue(time);
    await expect(prefsForm(page).getByLabel('주간 요약 요일')).toHaveValue('4');

    // 주간을 켜고 대상을 고르지 않으면 브라우저 필수 검증이 막는다 — PUT 0건.
    let puts = 0;
    page.on('request', (r) => {
      if (r.method() === 'PUT' && r.url().endsWith(PREFS_PATH)) puts += 1;
    });
    await prefsForm(page).getByLabel('주간 여행 요약').check();
    await prefsForm(page).getByLabel('주간 요약 대상').selectOption('');
    await prefsForm(page).getByRole('button', { name: '예약 설정 저장' }).click();
    expect(
      await prefsForm(page)
        .getByLabel('주간 요약 대상')
        .evaluate((el) => (el as HTMLSelectElement).validity.valueMissing),
    ).toBe(true);
    expect(puts).toBe(0);
    // 서버도 같은 규칙: 대상 없는 주간 → 422, 남의/없는 대상 → 422.
    expect(
      await putPrefs(page, apiBase, { ...saved, weekly_enabled: true, weekly_target_id: null }),
    ).toBe(422);
    expect(
      await putPrefs(page, apiBase, {
        ...saved,
        weekly_enabled: true,
        weekly_target_id: randomUUID(),
      }),
    ).toBe(422);
    expect(await getPrefs(page, apiBase)).toMatchObject({
      weekly_enabled: false,
      daily_enabled: true,
    });
  });

  test('NTF-027 대상 미연결 여행 — 알람으로 보내기 비활성, API 422·없는 여행 404·범위 검증', async ({
    page,
  }) => {
    ({ id: tripId } = await createTrip(page, {
      title: tripTitle('NTF-027'),
      start: isoDateFromToday(20),
      end: isoDateFromToday(21),
    }));
    await openShareTab(page, tripId);
    await expect(page.getByTestId('telegram-send-itinerary')).toBeDisabled();
    const history = tripSection(page).getByTestId('telegram-notification-history');
    await expect(history).toContainText('발송 내역이 없습니다.');
    await expect(tripSection(page).getByLabel('보낼 일정')).toContainText('2일차');

    const send = (id: string, data: Record<string, unknown>) =>
      withRateLimitRetry('POST telegram/send', () =>
        page.request.post(`${apiBase}/trips/${id}/telegram/send`, { data }),
      );
    const noTarget = await send(tripId, { request_id: randomUUID(), scope: 'trip' });
    expect(noTarget.status()).toBe(422);
    expect(JSON.stringify(await noTarget.json())).toContain(
      '먼저 활성·검증된 Telegram 대상을 여행에 연결하세요.',
    );
    expect((await send(randomUUID(), { request_id: randomUUID(), scope: 'trip' })).status()).toBe(
      404,
    );
    expect((await send(tripId, { request_id: randomUUID(), scope: 'day' })).status()).toBe(422); // day_index 없음
    const list = await withRateLimitRetry('GET telegram-notifications', () =>
      page.request.get(`${apiBase}/users/me/telegram-notifications?trip_id=${tripId}`),
    );
    expect(((await list.json()) as { data: unknown[] }).data).toHaveLength(0);
  });

  test('NTF-020 일정 정보 알람으로 보내기 — 여행 전체·2일차 전송 완료, 같은 요청 ID 멱등', async ({
    page,
  }, info) => {
    const chatId = requireTestChat(test);
    const label = e2eLabel('NTF-020');
    await page.goto('/settings/telegram');
    const created = await registerTargetViaForm(page, { chatId, label, isDefault: false });
    expect(created.status).toBe(201);
    test.skip(
      !created.data?.last_verified_at,
      'prod bot token 미설정 → 미검증 대상은 전송 대상이 아니다(blocked)',
    );

    ({ id: tripId } = await createTrip(page, {
      title: tripTitle('NTF-020'),
      start: isoDateFromToday(20),
      end: isoDateFromToday(21),
    }));
    await openShareTab(page, tripId);
    await page.getByTestId('trip-telegram-select').selectOption(created.data!.id);
    await Promise.all([
      page.waitForResponse(
        (r) =>
          r.request().method() === 'POST' &&
          r.url().endsWith(`/trips/${tripId}/telegram-targets`) &&
          r.status() === 201,
      ),
      page.getByTestId('trip-telegram-link').click(),
    ]);
    const button = page.getByTestId('telegram-send-itinerary');
    await expect(button).toBeEnabled();

    const isSend = (r: { request(): { method(): string }; url(): string }) =>
      r.request().method() === 'POST' && r.url().endsWith(`/trips/${tripId}/telegram/send`);
    for (const scope of ['여행 전체', '2일차']) {
      await tripSection(page).getByLabel('보낼 일정').selectOption({ label: scope });
      const [res] = await Promise.all([page.waitForResponse(isSend), button.click()]);
      expect(res.status(), `send ${scope}`).toBe(202);
    }
    const history = tripSection(page).getByTestId('telegram-notification-history');
    await expect(history.getByRole('listitem')).toHaveCount(2);
    await expect(history.getByRole('listitem').first()).toContainText('일정 보내기');
    // pending 이면 화면이 5초마다 다시 읽는다; API worker drain 이 끝나면 '전송 완료'.
    await expect(history.getByText(/전송 완료/)).toHaveCount(2, { timeout: 90_000 });
    await expect(history.getByText('전송 실패')).toHaveCount(0);
    expect(
      ((await history.textContent()) ?? '').includes(chatId),
      'history must not show the chat id',
    ).toBe(false);
    await shot(page, 'NTF-020', isMobileProject(info) ? 'mobile-sent' : 'sent');

    const listRes = await withRateLimitRetry('GET telegram-notifications', () =>
      page.request.get(`${apiBase}/users/me/telegram-notifications?trip_id=${tripId}`),
    );
    const rows = ((await listRes.json()) as { data: NotificationDto[] }).data;
    expect(rows.map((r) => r.category)).toEqual(['itinerary', 'itinerary']);
    for (const row of rows) {
      expect(row.trip_ids).toEqual([tripId]);
      expect(row.deliveries).toHaveLength(1);
      expect(row.deliveries[0]).toMatchObject({
        target_id: created.data!.id,
        status: 'sent',
        error_code: null,
      });
      expect(row.deliveries[0]!.sent_chunks).toBe(row.deliveries[0]!.total_chunks);
    }
    expect(JSON.stringify(rows).includes(chatId), 'API response must not carry the chat id').toBe(
      false,
    );

    // 같은 request_id 재시도는 같은 알림(새 발송 없음), 다른 범위에 재사용하면 422.
    const requestId = randomUUID();
    const post = (data: Record<string, unknown>) =>
      withRateLimitRetry('POST telegram/send', () =>
        page.request.post(`${apiBase}/trips/${tripId}/telegram/send`, { data }),
      );
    const first = await post({ request_id: requestId, scope: 'day', day_index: 1 });
    const again = await post({ request_id: requestId, scope: 'day', day_index: 1 });
    expect([first.status(), again.status()]).toEqual([202, 202]);
    const firstId = ((await first.json()) as { data: NotificationDto }).data.id;
    expect(((await again.json()) as { data: NotificationDto }).data.id).toBe(firstId);
    expect((await post({ request_id: requestId, scope: 'trip' })).status()).toBe(422);
  });

  test('NTF-028 주간 요약 대상 — 검증된 [e2e] 대상만 선택지, 저장·reload 보존', async ({
    page,
  }) => {
    const chatId = requireTestChat(test);
    const label = e2eLabel('NTF-028');
    const created = await registerTargetViaForm(page, { chatId, label, isDefault: false });
    expect(created.status).toBe(201);
    test.skip(
      !created.data?.last_verified_at,
      'prod bot token 미설정 → 미검증 대상은 선택지에 없다(blocked)',
    );
    await page.reload();
    const form = prefsForm(page);
    await form.getByLabel('발송 시각 (KST)').fill(SAFE_SEND_TIME);
    await form.getByLabel('주간 여행 요약').check();
    await form.getByLabel('주간 요약 대상').selectOption({ label });
    expect(await savePrefsViaForm(page)).toBe(200);
    await page.reload();
    await expect(prefsForm(page).getByLabel('주간 요약 대상')).toHaveValue(created.data!.id);
    expect(await getPrefs(page, apiBase)).toMatchObject({
      weekly_enabled: true,
      weekly_target_id: created.data!.id,
    });

    // 주간 대상을 지우면(soft delete) 수신 해제 저장은 여전히 가능해야 한다.
    const del = await withRateLimitRetry('DELETE target', () =>
      page.request.delete(`${apiBase}/users/me/telegram-targets/${created.data!.id}`),
    );
    expect(del.status()).toBe(204);
    expect((await listTargets(page, apiBase)).some((t) => t.id === created.data!.id)).toBe(false);
    const current = await getPrefs(page, apiBase);
    expect(await putPrefs(page, apiBase, { ...current, weekly_enabled: false })).toBe(200);
    expect(await getPrefs(page, apiBase)).toMatchObject({
      weekly_enabled: false,
      weekly_target_id: null,
    });
  });
});
