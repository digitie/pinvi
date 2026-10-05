import { expect, test, type Page } from '@playwright/test';
import { writeFile, mkdir, access } from 'node:fs/promises';
import path from 'node:path';

test.skip(
  process.env.PINVI_COMMON_ISOLATED_LIVE_E2E !== '1',
  'N150 isolated real API/GraphQL fixture only',
);
const evidence = process.env.PINVI_COMMON_LIVE_EVIDENCE_DIR ?? '/evidence';
const password = process.env.PINVI_COMMON_LIVE_PASSWORD ?? '';
async function login(page: Page, role = 'admin') {
  await page.goto('/admin/login');
  await page.locator('[data-slot=login-username]').fill(`${role}@example.test`);
  await page.locator('[data-slot=login-password]').fill(password);
  await page.locator('[data-slot=login-submit]').click();
}
async function control(name: string) {
  await writeFile(path.join(evidence, name), '1');
  await expect
    .poll(
      async () => {
        try {
          await access(path.join(evidence, `done-${name}`));
          return true;
        } catch {
          return false;
        }
      },
      { timeout: 60000 },
    )
    .toBe(true);
}

test('real login validation, nonadmin logout and DB-backed ETL roles', async ({
  page,
  request,
}) => {
  await page.goto('/admin/login');
  await page.locator('[data-slot=login-username]').fill('invalid-email');
  await page.locator('[data-slot=login-password]').fill('dummy');
  await page.locator('[data-slot=login-submit]').click();
  await expect(page.locator('[data-slot=login-error]')).toContainText('이메일');
  await expect(page.locator('[data-slot=login-username]')).toBeFocused();
  await expect(page.locator('[data-slot=login-password]')).toHaveValue('');
  await login(page, 'user');
  await expect(page.locator('[data-slot=login-error]')).toContainText('관리자');
  const anonymous = await page.request.get('http://127.0.0.1:12801/v1/admin/etl/summary');
  expect(anonymous.status()).toBe(401);
  await login(page, 'cpo');
  await expect(page).toHaveURL(/\/admin$/);
  const denied = await page.request.get('http://127.0.0.1:12801/v1/admin/etl/summary');
  expect(denied.status()).toBe(404);
  // 별도 context의 실제 login API도 role=operator가 허용됨을 확인한다.
  const auth = await request.post('http://127.0.0.1:12801/v1/auth/login', {
    data: { email: 'operator@example.test', password },
  });
  expect(auth.status()).toBe(200);
  const permitted = await request.get('http://127.0.0.1:12801/v1/admin/etl/summary');
  expect(permitted.status()).toBe(200);
});

test('old active run, scope, tick and semantic outage recovery through real UI', async ({
  page,
}, info) => {
  await login(page);
  await expect(page).toHaveURL(/\/admin$/);
  await page.getByTestId('admin-nav--admin-etl').click();
  await expect(page).toHaveURL(/\/admin\/etl$/);
  await expect(page.getByTestId('admin-etl-pinvi-status')).toContainText('정상');
  const panel = page.getByTestId('admin-common-dagster');
  await expect(panel).toBeVisible();
  await expect(panel).toContainText('pinvi.etl.definitions');
  const envelope = await (
    await page.request.get('http://127.0.0.1:12801/v1/admin/etl/summary')
  ).json();
  const data = envelope.data;
  expect(data.pinvi.repositories).toHaveLength(1);
  expect(data.pinvi.job_count).toBe(9); // 8 named jobs + implicit asset job.
  expect(
    data.pinvi.recent_runs.some((run: { run_id: string }) => run.run_id === 'old-active-pinvi'),
  ).toBe(true);
  expect(
    data.pinvi.recent_runs.some((run: { run_id: string }) => run.run_id === 'foreign-active'),
  ).toBe(false);
  const search = panel.getByRole('textbox', { name: '실행 검색' });
  await search.fill('pinvi_email_outbox_job');
  await expect(panel).toContainText('old-acti');
  await panel.getByRole('button', { name: /old-acti/ }).click();
  await expect(panel).toContainText('old-active-pinvi');
  await panel.getByRole('button', { name: 'pinvi_email_outbox_job', exact: true }).click();
  const schedule = panel.getByRole('link', { name: /스케줄 열기/ });
  await expect(schedule).toHaveAttribute('href', /__repository__%40pinvi\.etl\.definitions/);
  await mkdir(evidence, { recursive: true });
  await page.screenshot({
    path: path.join(evidence, `${info.project.name}-desktop.png`),
    fullPage: true,
  });
  await control(`${info.project.name}-down`);
  await panel.getByRole('button', { name: /새로고침/ }).click();
  await expect(page.getByTestId('admin-etl-pinvi-status')).toContainText('중단');
  await expect(panel).toContainText('old-active-pinvi');
  await expect(panel.getByRole('alert')).toBeVisible();
  await control(`${info.project.name}-up`);
  await panel.getByRole('button', { name: /새로고침/ }).click();
  await expect(page.getByTestId('admin-etl-pinvi-status')).toContainText('정상');
  await expect(panel.getByRole('alert')).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(panel).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true);
  await page.screenshot({
    path: path.join(evidence, `${info.project.name}-mobile.png`),
    fullPage: true,
  });
});
