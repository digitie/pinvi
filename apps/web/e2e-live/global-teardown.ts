/**
 * Live catalog global teardown — leaves prod as the run found it:
 *  - soft-deletes every remaining `[e2e]` trip of the test user (share links / companions /
 *    comments / telegram links cascade with the trip);
 *  - removes `[e2e]`-prefixed files from `/files` (POI-scope attachments outlive their trip);
 *  - deletes `[e2e]`-labelled Telegram targets of the test user.
 * Each step is independent; a failure is logged (without values) and the others still run.
 * The seed trip (`[e2e-seed] …`) never matches the `[e2e]` prefix and is kept.
 */
import { chromium } from '@playwright/test';
import { apiBaseURL, deleteAllE2eTrips, e2ePrefix, loginAsUser } from './helpers/live';
import { sweepE2eFiles } from './helpers/poi';
import { TARGETS_PATH, sweepE2eTargets } from './helpers/notify';

export default async function globalTeardown(): Promise<void> {
  const baseURL = process.env.PLAYWRIGHT_BASE_URL;
  if (!baseURL || !process.env.PINVI_E2E_USER_EMAIL || !process.env.PINVI_E2E_USER_PASSWORD) return;

  const browser = await chromium.launch();
  const context = await browser.newContext({ baseURL, locale: 'ko-KR', timezoneId: 'Asia/Seoul' });
  const page = await context.newPage();
  const report: string[] = [];
  try {
    await loginAsUser(page);
    try {
      report.push(`trips=${await deleteAllE2eTrips(page)}`);
    } catch (err) {
      report.push(`trips=ERR(${(err as Error).message})`);
    }
    try {
      report.push(`files=${await sweepE2eFiles(page)}`);
    } catch (err) {
      report.push(`files=ERR(${(err as Error).message})`);
    }
    try {
      const api = await apiBaseURL(page);
      report.push(`telegram(${TARGETS_PATH})=${await sweepE2eTargets(page, api)}`);
    } catch (err) {
      report.push(`telegram=ERR(${(err as Error).message})`);
    }
  } catch (err) {
    report.push(`login=ERR(${(err as Error).message})`);
  } finally {
    await context.close();
    await browser.close();
  }
  console.log(`[live-catalog] teardown sweep (${e2ePrefix}): ${report.join(' ')}`);
}
