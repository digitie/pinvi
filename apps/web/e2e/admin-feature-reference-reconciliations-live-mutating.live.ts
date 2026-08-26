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
const webBaseUrl = process.env.PINVI_LIVE_WEB_URL?.replace(/\/$/, '');
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

function assertSameOrigin(page: Page, expectedOrigin: string) {
  if (new URL(page.url()).origin !== expectedOrigin) {
    throw new Error(`M05 live UI document origin이 ${expectedOrigin}이 아닙니다.`);
  }
}

test.describe('M05 isolated Feature reference reconciliation live e2e', () => {
  test.beforeAll(() => {
    const missing: string[] = [];
    if (!enabled) missing.push('PINVI_M05_LIVE_E2E=1');
    if (!eventId) missing.push('PINVI_M05_LIVE_EVENT_ID');
    if (!oldFeatureId) missing.push('PINVI_M05_LIVE_OLD_FEATURE_ID');
    if (!replacementFeatureId) missing.push('PINVI_M05_LIVE_REPLACEMENT_FEATURE_ID');
    if (!impactCount) missing.push('PINVI_M05_LIVE_IMPACT_COUNT');
    if (!sourceRevision) missing.push('PINVI_SOURCE_REVISION');
    if (!verificationId) missing.push('PINVI_M05_UI_VERIFICATION_ID');
    if (!playwrightRunnerImageId) missing.push('PINVI_M05_PLAYWRIGHT_RUNNER_IMAGE_ID');
    if (!playwrightRunnerImageRef) missing.push('PINVI_M05_PLAYWRIGHT_RUNNER_IMAGE_REF');
    if (!webBaseUrl) missing.push('PINVI_LIVE_WEB_URL');
    if (!apiBaseUrl) missing.push('PINVI_M05_UI_API_URL');
    if (!adminStorageState && (!adminEmail || !adminPassword)) {
      missing.push('PINVI_M05_LIVE_EMAIL/PINVI_M05_LIVE_PASSWORD 또는 storage state');
    }
    if (missing.length > 0) {
      throw new Error(`M05 live E2E 환경변수가 없습니다: ${missing.join(', ')}`);
    }
  });
  if (adminStorageState) test.use({ storageState: adminStorageState });
  test.describe.configure({ mode: 'serial' });

  test('관리자 UI가 실제 M05 applied receipt와 영향 행을 읽기 전용으로 보인다', async ({ page }) => {
    if (!eventId || !oldFeatureId || !replacementFeatureId || !impactCount) {
      throw new Error('M05 live fixture 환경변수가 준비되지 않았습니다.');
    }
    if (!apiBaseUrl) throw new Error('M05 UI API endpoint가 준비되지 않았습니다.');
    if (!webBaseUrl) throw new Error('M05 UI web endpoint가 준비되지 않았습니다.');
    const webOrigin = new URL(webBaseUrl).origin;
    const apiOrigin = new URL(apiBaseUrl).origin;
    const detailPath = `/admin/feature-reference-reconciliations/${eventId}`;
    let observedApiRequests = 0;
    const unexpectedApiMutations: string[] = [];
    let foreignDocumentOrigin: string | null = null;
    page.on('request', (request) => {
      const requestUrl = new URL(request.url());
      if (requestUrl.origin !== apiOrigin) return;
      observedApiRequests += 1;
      const method = request.method();
      const isAuthenticationRequest =
        requestUrl.pathname === '/auth/login' && (method === 'POST' || method === 'OPTIONS');
      if (method !== 'GET' && !isAuthenticationRequest) {
        unexpectedApiMutations.push(`${method} ${requestUrl.pathname}`);
      }
    });
    page.on('framenavigated', (frame) => {
      if (frame === page.mainFrame() && frame.url() !== 'about:blank') {
        const origin = new URL(frame.url()).origin;
        if (origin !== webOrigin) foreignDocumentOrigin = origin;
      }
    });
    await ensureAdminAuth(page);
    assertSameOrigin(page, webOrigin);
    const listResponse = await page.goto('/admin/feature-reference-reconciliations');
    if (!listResponse) throw new Error('M05 UI 목록 응답이 없습니다.');
    expect(new URL(listResponse.url()).origin).toBe(webOrigin);
    expect(listResponse.request().redirectedFrom()).toBeNull();
    assertSameOrigin(page, webOrigin);
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
    if (
      !detailResponseBody.data ||
      typeof detailResponseBody.data !== 'object' ||
      Array.isArray(detailResponseBody.data)
    ) {
      throw new Error('M05 detail response data가 object가 아닙니다.');
    }
    const responseData = detailResponseBody.data as Record<string, unknown>;
    const responseReceipt = responseData.receipt;
    if (
      !responseReceipt ||
      typeof responseReceipt !== 'object' ||
      Array.isArray(responseReceipt)
    ) {
      throw new Error('M05 detail response receipt가 object가 아닙니다.');
    }
    const responseReceiptRecord = responseReceipt as Record<string, unknown>;
    const responseStatus = responseData.status;
    const responseImpacts = responseData.impacts;
    if (!Array.isArray(responseImpacts)) {
      throw new Error('M05 detail response impacts가 array가 아닙니다.');
    }
    expect(responseImpacts).toHaveLength(Number(impactCount));
    expect(responseStatus).toBe('applied');
    expect(responseReceiptRecord.action).toBe('rebind');
    expect(responseReceiptRecord.old_feature_id).toBe(oldFeatureId);
    expect(responseReceiptRecord.replacement_feature_id).toBe(replacementFeatureId);
    expect(responseReceiptRecord.impact_count).toBe(Number(impactCount));
    responseImpacts.forEach((rawImpact, index) => {
      if (!rawImpact || typeof rawImpact !== 'object' || Array.isArray(rawImpact)) {
        throw new Error(`M05 impact[${index}]가 object가 아닙니다.`);
      }
      const impact = rawImpact as Record<string, unknown>;
      expect(impact.event_id).toBe(eventId);
      expect(impact.impact_index).toBe(index);
      expect(typeof impact.target_relation).toBe('string');
      expect(typeof impact.target_id).toBe('string');
      expect(impact.old_feature_id).toBe(oldFeatureId);
      expect(impact.replacement_feature_id).toBe(replacementFeatureId);
      expect(typeof impact.outcome).toBe('string');
    });

    const detail = page.getByTestId('admin-frr-detail');
    const receipt = detail.getByRole('region', { name: '로컬 final receipt' });
    const receiptValue = (label: string) =>
      receipt
        .locator('dt')
        .filter({ hasText: label })
        .locator('xpath=following-sibling::dd[1]');
    await expect(
      detail
        .getByRole('region', { name: '결론' })
        .getByTestId(`admin-frr-status-${String(responseStatus)}`),
    ).toBeVisible();
    await expect(receiptValue('조치')).toContainText(String(responseReceiptRecord.action));
    await expect(receiptValue('이전 Feature ID')).toHaveText(oldFeatureId);
    await expect(receiptValue('대체 Feature ID')).toHaveText(replacementFeatureId);
    await expect(receiptValue('영향 행 수')).toHaveText(`${responseReceiptRecord.impact_count}건`);
    const impactRegion = detail.getByRole('region', { name: 'Row-level impact' });
    await expect(impactRegion).toBeVisible();
    await expect(impactRegion.locator('[data-testid^="admin-frr-impact-"]')).toHaveCount(
      responseImpacts.length,
    );
    for (const rawImpact of responseImpacts) {
      const impact = rawImpact as Record<string, unknown>;
      const row = impactRegion.getByTestId(`admin-frr-impact-${String(impact.impact_index)}`);
      await expect(row).toBeVisible();
      await expect(row).toContainText(String(impact.target_relation));
      await expect(row).toContainText(String(impact.target_id));
      await expect(row).toContainText(String(impact.old_feature_id));
      await expect(row).toContainText(String(impact.replacement_feature_id));
      await expect(row).toContainText(String(impact.outcome));
    }
    expect(foreignDocumentOrigin).toBeNull();
    await expect(detail).not.toContainText('승인');
    await expect(detail).not.toContainText('거절');
    expect(unexpectedApiMutations).toEqual([]);
    await expect.poll(() => observedApiRequests).toBeGreaterThan(0);

    const evidenceDir = process.env.PINVI_M05_UI_EVIDENCE_DIR;
    if (evidenceDir) {
      expect(detailResponseBody.data).toBeDefined();
      if (!verificationId || !playwrightRunnerImageId || !playwrightRunnerImageRef) {
        throw new Error('M05 UI run binding 환경변수가 준비되지 않았습니다.');
      }
      const marker = {
        assertions: [
          'status',
          'action',
          'old_feature',
          'replacement_feature',
          'impact_count',
          'impact_rows',
        ],
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
