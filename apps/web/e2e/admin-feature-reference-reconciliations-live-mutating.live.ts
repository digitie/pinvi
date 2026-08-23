import { createHash } from 'node:crypto';
import { writeFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';

const enabled = process.env.PINVI_M05_LIVE_E2E === '1';
const adminEmail = process.env.PINVI_M05_LIVE_EMAIL;
const adminPassword = process.env.PINVI_M05_LIVE_PASSWORD;
const adminStorageState = process.env.PINVI_M05_LIVE_STORAGE_STATE;
const eventId = process.env.PINVI_M05_LIVE_EVENT_ID;
const oldFeatureId = process.env.PINVI_M05_LIVE_OLD_FEATURE_ID;
const replacementFeatureId = process.env.PINVI_M05_LIVE_REPLACEMENT_FEATURE_ID;
const impactCount = process.env.PINVI_M05_LIVE_IMPACT_COUNT;
const sourceRevision = process.env.PINVI_SOURCE_REVISION;
const verificationId = process.env.PINVI_M05_UI_VERIFICATION_ID;
const playwrightRunnerImageId = process.env.PINVI_M05_PLAYWRIGHT_RUNNER_IMAGE_ID;
const playwrightRunnerImageRef = process.env.PINVI_M05_PLAYWRIGHT_RUNNER_IMAGE_REF;
const apiBaseUrl = (
  process.env.PINVI_M05_UI_API_URL ?? process.env.PINVI_LIVE_API_URL
)?.replace(/\/$/, '');

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value !== null && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`)
      .join(',')}}`;
  }
  return JSON.stringify(value);
}

async function ensureAdminAuth(page: Page) {
  if (adminStorageState) {
    await page.goto('/admin');
    await expect(page.getByTestId('admin-me')).toBeVisible();
    return;
  }
  if (!adminEmail || !adminPassword) {
    throw new Error('PINVI_M05_LIVE_EMAIL/PINVI_M05_LIVE_PASSWORD가 필요합니다.');
  }
  await page.goto('/admin/login');
  await page.getByTestId('admin-login-email').fill(adminEmail);
  await page.getByTestId('admin-login-password').fill(adminPassword);
  await page.getByTestId('admin-login-submit').click();
  await expect(page).toHaveURL(/\/admin(?:[?#].*)?$/);
}

test.describe('M05 isolated Feature reference reconciliation live e2e', () => {
  test.skip(!enabled, 'PINVI_M05_LIVE_E2E=1인 격리 paired stack에서만 실행합니다.');
  test.skip(!eventId, 'PINVI_M05_LIVE_EVENT_ID가 필요합니다.');
  test.skip(!oldFeatureId, 'PINVI_M05_LIVE_OLD_FEATURE_ID가 필요합니다.');
  test.skip(!replacementFeatureId, 'PINVI_M05_LIVE_REPLACEMENT_FEATURE_ID가 필요합니다.');
  test.skip(!impactCount, 'PINVI_M05_LIVE_IMPACT_COUNT가 필요합니다.');
  test.skip(!sourceRevision, 'PINVI_SOURCE_REVISION이 필요합니다.');
  test.skip(!verificationId, 'PINVI_M05_UI_VERIFICATION_ID가 필요합니다.');
  test.skip(!playwrightRunnerImageId, 'PINVI_M05_PLAYWRIGHT_RUNNER_IMAGE_ID가 필요합니다.');
  test.skip(!playwrightRunnerImageRef, 'PINVI_M05_PLAYWRIGHT_RUNNER_IMAGE_REF가 필요합니다.');
  test.skip(!apiBaseUrl, 'PINVI_M05_UI_API_URL가 필요합니다.');
  test.skip(
    !adminStorageState && (!adminEmail || !adminPassword),
    'PINVI_M05_LIVE_EMAIL/PINVI_M05_LIVE_PASSWORD 또는 storage state가 필요합니다.',
  );
  if (adminStorageState) test.use({ storageState: adminStorageState });
  test.describe.configure({ mode: 'serial' });

  test('관리자 UI가 실제 M05 applied receipt와 영향 행을 읽기 전용으로 보인다', async ({ page }) => {
    if (!eventId || !oldFeatureId || !replacementFeatureId || !impactCount) {
      throw new Error('M05 live fixture 환경변수가 준비되지 않았습니다.');
    }
    if (!apiBaseUrl) throw new Error('M05 UI API endpoint가 준비되지 않았습니다.');
    const apiOrigin = new URL(apiBaseUrl).origin;
    const detailPath = `/admin/feature-reference-reconciliations/${eventId}`;
    let observedApiRequests = 0;
    page.on('request', (request) => {
      if (new URL(request.url()).origin === apiOrigin) observedApiRequests += 1;
    });
    await ensureAdminAuth(page);
    await page.goto('/admin/feature-reference-reconciliations');
    const detailResponsePromise = page.waitForResponse((response) => {
      const responseUrl = new URL(response.url());
      return (
        response.request().method() === 'GET' &&
        responseUrl.pathname === detailPath
      );
    });
    await page.getByTestId(`admin-frr-detail-${eventId}`).click();
    const detailResponse = await detailResponsePromise;
    expect(detailResponse.status()).toBe(200);
    expect(new URL(detailResponse.url()).origin).toBe(apiOrigin);
    expect(detailResponse.request().redirectedFrom()).toBeNull();
    const detailResponseBody = (await detailResponse.json()) as { data?: unknown };

    const detail = page.getByTestId('admin-frr-detail');
    const receiptValue = (label: RegExp) =>
      detail.locator('dl > dt', { hasText: label }).locator('xpath=following-sibling::dd[1]');
    await expect(detail).toContainText('applied');
    await expect(receiptValue(/^조치$/)).toContainText('rebind');
    await expect(receiptValue(/^이전 Feature ID$/)).toHaveText(oldFeatureId);
    await expect(receiptValue(/^대체 Feature ID$/)).toHaveText(replacementFeatureId);
    await expect(receiptValue(/^영향 행 수$/)).toHaveText(`${impactCount}건`);
    await expect(detail).not.toContainText('승인');
    await expect(detail).not.toContainText('거절');
    await expect.poll(() => observedApiRequests).toBeGreaterThan(0);

    const evidenceDir = process.env.PINVI_M05_UI_EVIDENCE_DIR;
    if (evidenceDir) {
      expect(detailResponseBody.data).toBeDefined();
      if (!verificationId || !playwrightRunnerImageId || !playwrightRunnerImageRef) {
        throw new Error('M05 UI run binding 환경변수가 준비되지 않았습니다.');
      }
      const marker = {
        assertions: ['status', 'action', 'old_feature', 'replacement_feature', 'impact_count'],
        event_id: eventId,
        impact_count: Number(impactCount),
        old_feature_id: oldFeatureId,
        pinvi_api_endpoint: apiBaseUrl,
        pinvi_detail_sha256: createHash('sha256')
          .update(canonicalJson(detailResponseBody.data), 'utf8')
          .digest('hex'),
        replacement_feature_id: replacementFeatureId,
        verification_id: verificationId,
        playwright_runner_image_id: playwrightRunnerImageId,
        playwright_runner_image_ref: playwrightRunnerImageRef,
        source_revision: sourceRevision,
        status: 'passed',
      };
      writeFileSync(
        path.join(evidenceDir, 'ui-run.json'),
        `${JSON.stringify(marker)}\n`,
        { encoding: 'utf8', mode: 0o600, flag: 'wx' },
      );
    }
  });
});
