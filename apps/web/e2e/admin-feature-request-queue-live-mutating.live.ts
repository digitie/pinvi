import { createHash } from 'node:crypto';
import { writeFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';

const enabled = process.env.PINVI_M04_LIVE_E2E === '1';
const adminEmail = process.env.PINVI_M04_LIVE_EMAIL;
const adminPassword = process.env.PINVI_M04_LIVE_PASSWORD;
const adminStorageState = process.env.PINVI_M04_LIVE_STORAGE_STATE;
const featureRequestId = process.env.PINVI_M04_LIVE_FEATURE_REQUEST_ID;
const reason = process.env.PINVI_M04_LIVE_REASON ?? '[tvn-m04 isolated live e2e] queue receipt';
const sourceRevision = process.env.PINVI_SOURCE_REVISION;
const verificationId = process.env.PINVI_M04_UI_VERIFICATION_ID;
const playwrightRunnerImageId = process.env.PINVI_M04_PLAYWRIGHT_RUNNER_IMAGE_ID;
const playwrightRunnerImageRef = process.env.PINVI_M04_PLAYWRIGHT_RUNNER_IMAGE_REF;
const webBaseUrl = process.env.PINVI_LIVE_WEB_URL?.replace(/\/$/, '');
const apiBaseUrl = (
  process.env.PINVI_M04_UI_API_URL ?? process.env.PINVI_LIVE_API_URL
)?.replace(/\/$/, '');
const evidenceDir = process.env.PINVI_M04_UI_EVIDENCE_DIR;

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
    throw new Error('PINVI_M04_LIVE_EMAIL/PINVI_M04_LIVE_PASSWORD가 필요합니다.');
  }
  await page.goto('/admin/login');
  await page.getByTestId('admin-login-email').fill(adminEmail);
  await page.getByTestId('admin-login-password').fill(adminPassword);
  await page.getByTestId('admin-login-submit').click();
  await expect(page).toHaveURL(/\/admin(?:[?#].*)?$/);
}

function assertSameOrigin(page: Page, expectedOrigin: string) {
  if (new URL(page.url()).origin !== expectedOrigin) {
    throw new Error(`M04 live UI document origin이 ${expectedOrigin}이 아닙니다.`);
  }
}

test.describe('M04 isolated Map feature-request queue live e2e', () => {
  test.beforeAll(() => {
    if (!enabled) return;
    const missing: string[] = [];
    if (!featureRequestId) missing.push('PINVI_M04_LIVE_FEATURE_REQUEST_ID');
    if (!webBaseUrl) missing.push('PINVI_LIVE_WEB_URL');
    if (!apiBaseUrl) missing.push('PINVI_M04_UI_API_URL');
    if (!adminStorageState && (!adminEmail || !adminPassword)) {
      missing.push('PINVI_M04_LIVE_EMAIL/PINVI_M04_LIVE_PASSWORD 또는 storage state');
    }
    if (!evidenceDir) missing.push('PINVI_M04_UI_EVIDENCE_DIR');
    if (!verificationId) missing.push('PINVI_M04_UI_VERIFICATION_ID');
    if (!sourceRevision) missing.push('PINVI_SOURCE_REVISION');
    if (!playwrightRunnerImageId) missing.push('PINVI_M04_PLAYWRIGHT_RUNNER_IMAGE_ID');
    if (!playwrightRunnerImageRef) missing.push('PINVI_M04_PLAYWRIGHT_RUNNER_IMAGE_REF');
    if (missing.length > 0) {
      throw new Error(`M04 live E2E 환경변수가 없습니다: ${missing.join(', ')}`);
    }
  });
  test.skip(!enabled, 'PINVI_M04_LIVE_E2E=1인 격리 paired stack에서만 실행합니다.');
  if (adminStorageState) test.use({ storageState: adminStorageState });
  test.describe.configure({ mode: 'serial' });

  test('관리자 UI 승인 후 Map pending receipt를 PinVi approved 상태로 보존한다', async ({ page }) => {
    if (!featureRequestId || !webBaseUrl || !apiBaseUrl) {
      throw new Error('M04 live fixture endpoint가 준비되지 않았습니다.');
    }
    const webOrigin = new URL(webBaseUrl).origin;
    const apiOrigin = new URL(apiBaseUrl).origin;
    const approvePath = `/admin/feature-requests/${featureRequestId}/approve`;
    let foreignDocumentOrigin: string | null = null;
    page.on('framenavigated', (frame) => {
      if (frame === page.mainFrame() && frame.url() !== 'about:blank') {
        const origin = new URL(frame.url()).origin;
        if (origin !== webOrigin) foreignDocumentOrigin = origin;
      }
    });
    await ensureAdminAuth(page);
    assertSameOrigin(page, webOrigin);
    const listResponse = await page.goto('/admin/feature-requests');
    if (!listResponse) throw new Error('M04 UI 목록 응답이 없습니다.');
    expect(new URL(listResponse.url()).origin).toBe(webOrigin);
    expect(listResponse.request().redirectedFrom()).toBeNull();
    assertSameOrigin(page, webOrigin);
    await page.getByTestId(`admin-fr-review-${featureRequestId}`).click();
    await expect(page.getByTestId('admin-fr-queue-payload-notice')).toBeVisible();
    await page.getByTestId('admin-fr-reason').fill(reason);

    // M04 attestation은 승인 mutation이 이 격리 API로만 전달된 경우에만 유효하다.
    // Web 이미지의 baked endpoint가 바뀐 경우 외부/공유 API로의 요청은 전송 전에 막는다.
    await page.route(
      (url) => url.pathname === approvePath,
      async (route) => {
        const request = route.request();
        const requestUrl = new URL(request.url());
        if (request.method() === 'POST' && requestUrl.origin !== apiOrigin) {
          await route.abort('blockedbyclient');
          return;
        }
        await route.continue();
      },
    );
    const approvalRequestPromise = page.waitForRequest((request) => {
      const requestUrl = new URL(request.url());
      return request.method() === 'POST' && requestUrl.pathname === approvePath;
    });
    const responsePromise = page.waitForResponse((response) => {
      const responseUrl = new URL(response.url());
      return (
        response.request().method() === 'POST' &&
        responseUrl.origin === apiOrigin &&
        responseUrl.pathname === approvePath
      );
    });
    await page.getByTestId('admin-fr-approve').click();
    const approvalRequest = await approvalRequestPromise;
    expect(new URL(approvalRequest.url()).origin).toBe(apiOrigin);
    const response = await responsePromise;
    expect(response.status()).toBe(200);
    expect(response.request().redirectedFrom()).toBeNull();
    const payload = (await response.json()) as {
      data?: {
        request_id?: string;
        status?: string;
        kor_travel_map_ref?: Record<string, unknown>;
        reviewed_by_admin_id?: string;
        resolved_at?: string;
      };
    };
    const result = payload.data;
    const mapReference = result?.kor_travel_map_ref;
    expect(result?.request_id).toBe(featureRequestId);
    expect(result?.status).toBe('approved');
    expect(result?.reviewed_by_admin_id).toBeTruthy();
    expect(result?.resolved_at).toBeTruthy();
    expect(mapReference).toMatchObject({
      request_id: featureRequestId,
      state: 'pending',
      review_mode: 'feature_request_queue',
      action: 'submit',
    });
    await expect(page.getByTestId('admin-fr-notice')).toContainText('Map Feature 요청 큐');
    expect(foreignDocumentOrigin).toBeNull();

    if (!evidenceDir || !verificationId || !sourceRevision || !playwrightRunnerImageId || !playwrightRunnerImageRef) {
      throw new Error('M04 UI run binding 환경변수가 준비되지 않았습니다.');
    }
    const approvalBinding = {
      kor_travel_map_ref: mapReference,
      request_id: result?.request_id,
      resolved_at: result?.resolved_at,
      reviewed_by_admin_id: result?.reviewed_by_admin_id,
      status: result?.status,
    };
    const marker = {
      assertions: [
        'pinvi_approved',
        'pinvi_approval_binding',
        'map_request_id',
        'map_pending_receipt',
        'map_pending_receipt_fingerprint',
        'same_origin',
      ],
      feature_request_id: featureRequestId,
      map_action: mapReference?.action,
      map_pending_receipt_sha256: createHash('sha256')
        .update(canonicalJson(mapReference), 'utf8')
        .digest('hex'),
      map_request_id: mapReference?.request_id,
      map_review_mode: mapReference?.review_mode,
      map_state: mapReference?.state,
      pinvi_api_endpoint: apiBaseUrl,
      pinvi_approval_sha256: createHash('sha256')
        .update(canonicalJson(approvalBinding), 'utf8')
        .digest('hex'),
      playwright_runner_image_id: playwrightRunnerImageId,
      playwright_runner_image_ref: playwrightRunnerImageRef,
      source_revision: sourceRevision,
      status: 'passed',
      verification_id: verificationId,
    };
    writeFileSync(
      path.join(evidenceDir, 'm04-ui-run.json'),
      `${JSON.stringify(marker)}\n`,
      { encoding: 'utf8', mode: 0o600, flag: 'wx' },
    );
  });
});
