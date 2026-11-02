/**
 * POI-027 — final sweep for the poi area. Runs last by filename order; safe to run alone.
 * Removes every `/files` row with the `[e2e]` prefix and every `[e2e]` trip, then asserts both are empty.
 */
import { expect, test } from '@playwright/test';
import { deleteAllE2eTrips, e2ePrefix, loginAsUser } from '../../helpers/live';
import { snap, sweepE2eFiles } from '../../helpers/poi';

test.skip(({ isMobile }) => isMobile, 'sweep runs once, on the desktop project');

test('POI-027 정리 스윕 — [e2e] 파일·여행 잔여 0', async ({ page }) => {
  await loginAsUser(page);
  const removedFiles = await sweepE2eFiles(page);
  const removedTrips = await deleteAllE2eTrips(page);
  test.info().annotations.push({ type: 'sweep', description: `files=${removedFiles} trips=${removedTrips}` });

  await page.goto('/files');
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0, { timeout: 20_000 });
  await expect(page.getByTestId('my-file-list').getByRole('listitem').filter({ hasText: e2ePrefix })).toHaveCount(0);
  await snap(page, 'POI-027', 'files-clean');

  await page.goto('/trips');
  await expect(page.getByTestId('trip-list')).toBeVisible();
  await expect(page.getByTestId('trip-list').getByRole('link').filter({ hasText: e2ePrefix })).toHaveCount(0);
  await snap(page, 'POI-027', 'trips-clean');
});
