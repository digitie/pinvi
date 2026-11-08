/**
 * TRS-* — data-driven trip scenarios (190 cases, `e2e-live/catalog/trip-scenarios/*.yaml`).
 *
 * One test per scenario: create an `[e2e] <id> …` trip whose dates come from `start_offset_days`
 * (KST), add every place to its day through the plan-panel search (Map feature rows only — badge
 * '장소', never Kakao/Naver, so no residual feature suggestion is created), then assert:
 *  - each day holds exactly its places, matched by NAME (`expect_name_contains`) — never by category
 *    label: Map categories are known to be wrong for some features (Map #1438);
 *  - the map renders one trip marker per place and each marker carries a category/kind;
 *  - the listed checks: optimize (preview, apply when it reorders), reorder, weather section, share
 *    read-only in a fresh logged-out context, copy, date shift, delete day.
 * The trip (and a copy) is deleted in afterEach; global setup/teardown sweep every `[e2e]` trip.
 *
 * Desktop runs every scenario; the mobile project only runs the ones tagged `mobile` (~10%).
 * Batches: `--grep TRS-CG` / `TRS-CJ` / `TRS-GS` / `TRS-JT` (runbook §10). Throttles (ms, env):
 * PINVI_E2E_TRS_TRIP_THROTTLE_MS between scenarios (default 2000), PINVI_E2E_TRS_PLACE_THROTTLE_MS
 * between place adds (default 300) — keeps a 190-trip run well under the per-account API limits.
 */
import { expect, test, type Page, type TestInfo } from '@playwright/test';
import {
  createShareLink,
  createTrip,
  deleteTrip,
  e2ePrefix,
  isMobile,
  loginAsUser,
  openSharedInFreshContext,
  openTripTab,
  pickFeature,
  redact,
  runTag,
  searchAndAddPlace,
  shot,
  waitForMapIdle,
  waitForRequest,
} from '../../helpers/live';
import {
  copyTripViaUi,
  dayDeleteButton,
  dayTab,
  dragPoi,
  gotoTrip,
  koDate,
  mapMarkers,
  openTripEdit,
  poiRows,
  poiTitles,
  saveTripEdit,
  selectDay,
  summaryPattern,
} from '../../helpers/trip';
import { expectSharedReadOnly } from '../../helpers/share';
import { STATUS_TEXT, daySection, openDay, weatherKind } from '../../helpers/weather';
import { loadTripScenarios, scenarioDates, type ScenarioCheck, type ScenarioPlace, type TripScenario } from '../../helpers/tripScenarios';

const SCENARIOS = loadTripScenarios();

const envMs = (name: string, fallback: number): number => {
  const raw = process.env[name];
  const n = raw === undefined || raw === '' ? fallback : Number(raw);
  return Number.isFinite(n) && n >= 0 ? n : fallback;
};
const TRIP_THROTTLE_MS = envMs('PINVI_E2E_TRS_TRIP_THROTTLE_MS', 2_000);
const PLACE_THROTTLE_MS = envMs('PINVI_E2E_TRS_PLACE_THROTTLE_MS', 300);

const DISTANCE = /\d+(\.\d)?(km|m)/; // formatDistanceMeters
/** Order in which checks run — destructive ones (date shift, delete day) last. */
const CHECK_ORDER: ScenarioCheck['kind'][] = [
  'optimize_day',
  'reorder_day',
  'weather_day',
  'share_readonly',
  'copy_trip',
  'date_shift',
  'delete_day',
];

/**
 * Name-based pick: a Map feature row (badge '장소' on its own line, never Kakao/Naver/주소/내 여행) whose
 * name line contains `expect_name_contains`. The loader only accepts `source: feature`.
 */
function pickByName(place: ScenarioPlace): (rowText: string) => boolean {
  return (rowText) => {
    const lines = rowText.split('\n').map((l) => l.trim());
    if (!(lines[0] ?? '').includes(place.expect_name_contains)) return false;
    return lines.includes('장소') && pickFeature(rowText);
  };
}

/** 60 s base + per place + per check (share/copy open extra pages). */
function budgetMs(s: TripScenario): number {
  return 60_000 + s.places.length * 15_000 + s.checks.length * 30_000 + s.days * 5_000;
}

function note(type: string, description: string): void {
  test.info().annotations.push({ type, description });
}

const created: string[] = [];
let firstTest = true;

test.beforeEach(async ({ page }) => {
  // Throttle between trips (not before the first one of the worker).
  if (!firstTest && TRIP_THROTTLE_MS > 0) await page.waitForTimeout(TRIP_THROTTLE_MS);
  firstTest = false;
  await loginAsUser(page);
});

test.afterEach(async ({ page }) => {
  while (created.length > 0) {
    const id = created.pop()!;
    await deleteTrip(page, id).catch(() => undefined);
  }
});

/* ------------------------------------------------------------------ steps */

async function addPlaces(page: Page, s: TripScenario): Promise<Map<number, string[]>> {
  const perDay = new Map<number, string[]>();
  for (const place of s.places) {
    let name: string;
    try {
      name = await searchAndAddPlace(page, place.day, place.query, pickByName(place));
    } catch (err) {
      const msg = (err as Error).message.split('\n')[0];
      throw new Error(`${s.id} day ${place.day} '${place.query}' → no ${place.source} row named '${place.expect_name_contains}' (${msg})`);
    }
    expect(name, `${s.id}: picked row for '${place.query}'`).toContain(place.expect_name_contains);
    perDay.set(place.day, [...(perDay.get(place.day) ?? []), name]);
    if (PLACE_THROTTLE_MS > 0) await page.waitForTimeout(PLACE_THROTTLE_MS);
  }
  return perDay;
}

async function expectDays(page: Page, s: TripScenario, perDay: Map<number, string[]>): Promise<void> {
  for (let day = 1; day <= s.days; day += 1) {
    const expected = s.places.filter((p) => p.day === day).map((p) => p.expect_name_contains);
    await selectDay(page, `${day}일차`);
    await expect(poiRows(page), `${s.id} day ${day} place count`).toHaveCount(expected.length);
    const titles = await poiTitles(page);
    for (let i = 0; i < expected.length; i += 1) {
      expect(titles[i] ?? '', `${s.id} day ${day} row ${i + 1}`).toContain(expected[i]!);
    }
    expect(perDay.get(day)?.length ?? 0).toBe(expected.length);
  }
  await expect(page.getByTestId('trip-top-panel')).toContainText(summaryPattern(s.days, s.places.length));
}

/** One trip marker per place (all days visible), each with a category or kind. */
async function expectMap(page: Page, s: TripScenario, expectedPins: number): Promise<void> {
  await waitForMapIdle(page);
  await expect(mapMarkers(page), `${s.id} map pins`).toHaveCount(expectedPins);
  await expect(page.getByTestId('trip-map-stats')).toContainText(`장소 ${expectedPins}곳`);
  const styles = await mapMarkers(page).evaluateAll((els) =>
    els.map((el) => ({
      title: (el.textContent ?? '').trim(),
      category: el.getAttribute('data-marker-category') ?? '',
      kind: el.getAttribute('data-marker-kind') ?? '',
    })),
  );
  const unlabeled = styles.filter((m) => m.category === '' && m.kind === '').map((m) => m.title);
  expect(unlabeled, `${s.id}: markers without category/kind`).toEqual([]);
  // Categories are recorded, never asserted (Map #1438 — some are wrong).
  note('categories', styles.map((m) => `${m.title}=${m.category || m.kind}`).join(' | '));
}

async function checkOptimize(page: Page, s: TripScenario, day: number): Promise<void> {
  await selectDay(page, `${day}일차`);
  const before = await poiTitles(page);
  const optimize = page.getByTestId('trip-day-optimize');
  await expect(optimize).toBeVisible();
  const preview = waitForRequest(page, new RegExp(`/days/${day}/optimize$`));
  await optimize.getByRole('button', { name: '동선 최적화' }).click();
  const res = await preview;
  expect(res.ok(), `${s.id} optimize preview day ${day}`).toBeTruthy();
  expect((res.request().postDataJSON() as { persist: boolean }).persist).toBe(false);
  await expect(optimize).toContainText(DISTANCE);
  await expect(optimize).toContainText(/순서 변경 \d+곳/);
  const moves = Number(/순서 변경 (\d+)곳/.exec(await optimize.innerText())?.[1] ?? '0');
  note('optimize', `day ${day}: ${moves} move(s)`);
  if (moves === 0) {
    await optimize.getByRole('button', { name: '닫기', exact: true }).click();
    expect(await poiTitles(page)).toEqual(before);
    return;
  }
  const apply = waitForRequest(page, new RegExp(`/days/${day}/optimize$`));
  await optimize.getByRole('button', { name: '적용', exact: true }).click();
  const applied = await apply;
  expect(applied.ok(), `${s.id} optimize apply day ${day}`).toBeTruthy();
  expect((applied.request().postDataJSON() as { persist: boolean }).persist).toBe(true);
  await expect.poll(async () => poiTitles(page)).not.toEqual(before);
  expect([...(await poiTitles(page))].sort()).toEqual([...before].sort());
}

async function checkReorder(page: Page, s: TripScenario, day: number, testInfo: TestInfo): Promise<void> {
  if (testInfo.project.use.hasTouch === true) {
    note('skip-check', `reorder_day ${day}: HTML5 drag needs a mouse pointer (mobile)`);
    return;
  }
  await selectDay(page, `${day}일차`);
  const before = await poiTitles(page);
  const last = before.length - 1;
  const reorder = waitForRequest(page, /\/trips\/[0-9a-f-]{36}\/pois\/reorder/);
  await dragPoi(page, last, 0);
  expect((await reorder).ok(), `${s.id} reorder day ${day}`).toBeTruthy();
  const expected = [before[last]!, ...before.slice(0, last)];
  await expect.poll(async () => poiTitles(page)).toEqual(expected);
}

async function checkWeather(page: Page, s: TripScenario, day: number): Promise<void> {
  const article = await openDay(page, day);
  const section = daySection(article);
  const kind = await weatherKind(section);
  const text = (await section.innerText()).replace(/\s+/g, ' ').slice(0, 160);
  if (kind === 'status') {
    const known = Object.values(STATUS_TEXT).some((t) => text.includes(t));
    expect(known, `${s.id} day ${day}: weather status text is one of the known states`).toBe(true);
    if (text.includes(STATUS_TEXT.unavailable!)) note('warning', `weather day ${day}: unavailable`);
  }
  note('weather', `day ${day}: ${kind} — ${text}`);
}

async function checkShare(page: Page, s: TripScenario, title: string, tripId: string): Promise<void> {
  const browser = page.context().browser();
  if (!browser) throw new Error('no browser handle for the fresh share context');
  await openTripTab(page, '공유');
  const link = await createShareLink(page, { visibility: 'view_only' });
  const fresh = await openSharedInFreshContext(browser, tripId, link.token, {
    viewport: page.viewportSize() ?? undefined,
  });
  try {
    expect(fresh.apiStatus, redact(`${s.id}: shared view API status`, link.token)).toBe(200);
    await expectSharedReadOnly(fresh.page, title);
    await expect(fresh.page.getByRole('complementary', { name: '장소 목록' })).toContainText(
      s.places.find((p) => p.day === 1)!.expect_name_contains,
    );
  } finally {
    await fresh.context.close();
  }
  await openTripTab(page, '일정');
}

async function checkCopy(page: Page, s: TripScenario, title: string, tripId: string): Promise<void> {
  const copyId = await copyTripViaUi(page, tripId);
  created.push(copyId);
  await expect(page.getByRole('heading', { name: `${title} copy` }).first()).toBeVisible();
  await expect(page.getByTestId('trip-top-panel')).toContainText(summaryPattern(s.days, s.places.length));
  await deleteTrip(page, copyId);
  created.splice(created.indexOf(copyId), 1);
  await gotoTrip(page, tripId);
}

async function checkDateShift(page: Page, s: TripScenario, shift: number, tripId: string): Promise<void> {
  const { start, end } = scenarioDates(s, shift);
  await openTripEdit(page);
  await page.locator('#trip-edit-start').fill(start);
  await page.locator('#trip-edit-end').fill(end);
  await saveTripEdit(page);
  await gotoTrip(page, tripId);
  await openTripEdit(page);
  await expect(page.locator('#trip-edit-start')).toHaveValue(start);
  await expect(page.locator('#trip-edit-end')).toHaveValue(end);
  await page.getByRole('button', { name: '취소', exact: true }).click();
  await expect(page.getByTestId('trip-top-panel')).toContainText(summaryPattern(s.days, s.places.length));
  note('date-shift', `${shift > 0 ? '+' : ''}${shift}d → ${koDate(start)}`);
}

async function checkDeleteDay(page: Page, s: TripScenario, day: number): Promise<number> {
  const onDay = s.places.filter((p) => p.day === day).length;
  await selectDay(page, `${day}일차`);
  // desktop header + mobile drawer may both render the control; click the visible one.
  await dayDeleteButton(page, day).filter({ visible: true }).first().click();
  const confirm = page.getByTestId('day-delete-confirm');
  await expect(confirm).toBeVisible();
  await expect(confirm).toContainText(`POI ${onDay}곳`);
  await page.getByTestId('day-delete-confirm-confirm').click();
  await expect(dayTab(page, `${day}일차`)).toHaveCount(0);
  const remaining = s.places.length - onDay;
  await expect(page.getByTestId('trip-top-panel')).toContainText(summaryPattern(s.days - 1, remaining));
  return remaining;
}

/* ------------------------------------------------------------------ tests */

for (const s of SCENARIOS) {
  const tags = ['@trs', `@trs-${s.id.split('-')[1]!.toLowerCase()}`, `@${s.priority.toLowerCase()}`];
  if (s.mobile) tags.push('@mobile');
  test(`[${s.id}] ${s.title}`, { tag: tags }, async ({ page }, testInfo) => {
    test.skip(isMobile(testInfo) && !s.mobile, 'mobile project runs only the scenarios tagged mobile');
    test.setTimeout(budgetMs(s));
    note('scenario', `${s.style} · ${s.days}일 · ${s.places.length}곳 · D+${s.start_offset_days} · ${s.file}`);

    const title = `${e2ePrefix} ${s.id} ${s.title} ${runTag()}`;
    const { start, end } = scenarioDates(s);
    const { id } = await createTrip(page, { title, start, end });
    created.push(id);
    await gotoTrip(page, id);

    const perDay = await addPlaces(page, s);
    await expectDays(page, s, perDay);
    await expectMap(page, s, s.places.length);
    await shot(page, s.id, 'loaded');

    const ordered = [...s.checks].sort((a, b) => CHECK_ORDER.indexOf(a.kind) - CHECK_ORDER.indexOf(b.kind));
    for (const check of ordered) {
      await test.step(`check ${JSON.stringify(check)}`, async () => {
        switch (check.kind) {
          case 'optimize_day':
            return checkOptimize(page, s, check.day);
          case 'reorder_day':
            return checkReorder(page, s, check.day, testInfo);
          case 'weather_day':
            return checkWeather(page, s, check.day);
          case 'share_readonly':
            return checkShare(page, s, title, id);
          case 'copy_trip':
            return checkCopy(page, s, title, id);
          case 'date_shift':
            return checkDateShift(page, s, check.days, id);
          case 'delete_day': {
            const remaining = await checkDeleteDay(page, s, check.day);
            await expectMap(page, s, remaining);
            return;
          }
        }
      });
    }
    if (ordered.length > 0) await shot(page, s.id, 'checked');
  });
}
