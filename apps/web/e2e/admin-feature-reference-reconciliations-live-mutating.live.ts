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
    await ensureAdminAuth(page);
    await page.goto('/admin/feature-reference-reconciliations');
    await page.getByTestId(`admin-frr-detail-${eventId}`).click();

    const detail = page.getByTestId('admin-frr-detail');
    const receiptValue = (label: RegExp) =>
      detail.locator('dl > dt', { hasText: label }).locator('xpath=following-sibling::dd[1]');
    await expect(detail).toContainText('applied');
    await expect(receiptValue(/^action$/)).toHaveText('rebind');
    await expect(receiptValue(/^이전 Feature$/)).toHaveText(oldFeatureId);
    await expect(receiptValue(/^대체 Feature$/)).toHaveText(replacementFeatureId);
    await expect(receiptValue(/^영향 행$/)).toHaveText(impactCount);
    await expect(detail).not.toContainText('승인');
    await expect(detail).not.toContainText('거절');

    const evidenceDir = process.env.PINVI_M05_UI_EVIDENCE_DIR;
    if (evidenceDir) {
      const response = await page.evaluate(async (id) => {
        const result = await fetch(`/api/proxy/admin/feature-reference-reconciliations/${id}`, {
          credentials: 'same-origin',
          cache: 'no-store',
        });
        return { body: await result.json(), status: result.status };
      }, eventId);
      expect(response.status).toBe(200);
      const responseBody = response.body as { data?: unknown };
      expect(responseBody.data).toBeDefined();
      const marker = {
        assertions: ['status', 'action', 'old_feature', 'replacement_feature', 'impact_count'],
        event_id: eventId,
        impact_count: Number(impactCount),
        old_feature_id: oldFeatureId,
        pinvi_detail_sha256: createHash('sha256')
          .update(canonicalJson(responseBody.data), 'utf8')
          .digest('hex'),
        replacement_feature_id: replacementFeatureId,
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
