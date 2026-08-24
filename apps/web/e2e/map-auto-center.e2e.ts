import { expect, test, type Page } from '@playwright/test';

/**
 * T-325 — 진입 시 단말기 위치로 지도 중심점을 잡는다.
 *
 * CI e2e에는 VWorld 키가 없어 MapLibre가 생성되지 않는다(지도 fallback). 그래서 카메라를 직접
 * 관측할 수 없고, 컴포넌트가 노출하는 결정값(`map-center-state`)으로 계약을 고정한다.
 * 여기서 지키는 계약은 셋이다:
 *   ① 권한이 없으면 좌표를 취득하지 않는다(브라우저 프롬프트 금지)
 *   ② 동의가 없으면 취득하지 않고 **모달도 띄우지 않는다**(다크 패턴 회피)
 *   ③ 둘 다 있으면 조용히 단말기 위치로 센터링한다
 */

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

const GRANTED_CONSENTS = [
  {
    consent_type: 'lbs_tos',
    version: 'v1.0',
    agreed_at: '2026-06-10T00:00:00Z',
    withdrawn_at: null,
  },
  {
    consent_type: 'location_collection',
    version: 'v1.0',
    agreed_at: '2026-06-10T00:00:00Z',
    withdrawn_at: null,
  },
];

async function stubConsents(page: Page, data: unknown[]): Promise<void> {
  await page.route(/.*\/users\/me\/consents$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data }) });
  });
}

/** `navigator.geolocation.getCurrentPosition` 호출 횟수를 세는 스파이를 페이지에 심는다. */
async function spyOnGeolocation(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const counter = { calls: 0 };
    (window as unknown as { __geoCalls: typeof counter }).__geoCalls = counter;
    const original = navigator.geolocation?.getCurrentPosition?.bind(navigator.geolocation);
    if (!original) return;
    navigator.geolocation.getCurrentPosition = ((...args: Parameters<typeof original>) => {
      counter.calls += 1;
      return original(...args);
    }) as typeof navigator.geolocation.getCurrentPosition;
  });
}

function geoCallCount(page: Page): Promise<number> {
  return page.evaluate(
    () => (window as unknown as { __geoCalls?: { calls: number } }).__geoCalls?.calls ?? 0,
  );
}

const state = (page: Page) => page.getByTestId('map-center-state');

test.describe('권한과 동의가 모두 있을 때', () => {
  test.use({
    permissions: ['geolocation'],
    geolocation: { latitude: 35.1796, longitude: 129.0756 }, // 부산
  });

  test('진입만으로 단말기 위치로 센터링하고 모달은 띄우지 않는다', async ({ page }) => {
    await stubConsents(page, GRANTED_CONSENTS);
    await page.goto('/map');

    await expect(state(page)).toHaveAttribute('data-resolved', 'true');
    await expect(state(page)).toHaveAttribute('data-reason', 'located');
    await expect(state(page)).toHaveAttribute('data-source', 'device');
    // 좌표는 4자리로 절사해 노출한다 — 원좌표를 DOM에 싣지 않는다.
    await expect(state(page)).toHaveAttribute('data-center-lat', '35.1796');
    await expect(state(page)).toHaveAttribute('data-center-lon', '129.0756');
    // 자동 센터링 줌은 시군구 수준(13)이며 "내 위치" 버튼(14)보다 넓다.
    await expect(state(page)).toHaveAttribute('data-zoom', '13');

    // 성공은 조용히 — 진입만으로 동의 모달이 뜨면 안 된다.
    await expect(page.getByTestId('location-consent-dialog')).toBeHidden();
  });

  test('국내 범위 밖 좌표면 센터링하지 않고 이유를 알린다', async ({ page, context }) => {
    await context.setGeolocation({ latitude: 35.6895, longitude: 139.6917 }); // 도쿄
    await stubConsents(page, GRANTED_CONSENTS);
    await page.goto('/map');

    await expect(state(page)).toHaveAttribute('data-reason', 'out-of-area');
    await expect(state(page)).toHaveAttribute('data-source', 'default');
    await expect(state(page)).toHaveAttribute('data-center-lat', '37.5665');
    await expect(page.getByText('국내 서비스 범위 밖')).toBeVisible();
  });
});

test.describe('동의가 없을 때', () => {
  test.use({
    permissions: ['geolocation'],
    geolocation: { latitude: 35.1796, longitude: 129.0756 },
  });

  test('좌표를 취득하지 않고 기본 중심점을 유지하며 모달도 띄우지 않는다', async ({ page }) => {
    await spyOnGeolocation(page);
    await stubConsents(page, []);
    await page.goto('/map');

    await expect(state(page)).toHaveAttribute('data-reason', 'no-consent');
    await expect(state(page)).toHaveAttribute('data-source', 'default');
    await expect(state(page)).toHaveAttribute('data-center-lat', '37.5665');
    // 동의 없이 좌표를 취득하면 위치정보법 제15조 위반이다.
    expect(await geoCallCount(page)).toBe(0);
    await expect(page.getByTestId('location-consent-dialog')).toBeHidden();
  });
});

test.describe('브라우저 권한이 없을 때', () => {
  // permissions를 부여하지 않는다 → Permissions API가 'prompt'를 돌려준다.
  test.use({ permissions: [] });

  test('진입만으로 권한 프롬프트를 띄우지 않고 동의 조회도 하지 않는다', async ({ page }) => {
    await spyOnGeolocation(page);
    let consentCalls = 0;
    await page.route(/.*\/users\/me\/consents$/, async (route, request) => {
      if (!isFetch(request.resourceType())) return route.continue();
      consentCalls += 1;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: GRANTED_CONSENTS }),
      });
    });

    await page.goto('/map');

    await expect(state(page)).toHaveAttribute('data-reason', 'no-permission');
    await expect(state(page)).toHaveAttribute('data-source', 'default');
    // 권한 조회가 먼저라서 동의 왕복 자체가 발생하지 않는다.
    expect(await geoCallCount(page)).toBe(0);
    expect(consentCalls).toBe(0);
  });
});
