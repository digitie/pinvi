import { expect, test } from './fixtures';

// 2026-11-02 prod e2e — webpack 빌드가 maplibre 6의 worker URL(`import.meta.url` 유도)을 빌드 머신
// `file://` 경로로 굳혀 "Worker failed to load"가 났다(worker를 쓰는 GeoJSON/벡터 source는 그 상태에서
// tile을 만들지 못한다). 처방은 worker와 형제 파일을 `public/maplibre/`로 복사(`prebuild`)하고 `setWorkerUrl`로
// 가리키는 것이다. 이 검사는 **빌드된 앱이 그 파일들을 실제로 서빙하는지**를 센다 — module
// worker는 JavaScript MIME이 아니면 로드되지 않는다.
test('빌드된 앱이 maplibre worker를 JavaScript로 서빙한다', async ({ request }) => {
  const response = await request.get('/maplibre/maplibre-gl-worker.mjs');
  expect(response.status()).toBe(200);
  expect(response.headers()['content-type'] ?? '').toMatch(/javascript/);
  expect((await response.text()).length).toBeGreaterThan(1000);
});

test('worker의 형제 파일도 같은 디렉터리에서 서빙한다', async ({ request }) => {
  // maplibre 6.15의 shared 청크는 비어 있을 수 있다(worker가 자기완결). 버전에 따라 worker가
  // 상대 경로로 import하므로 존재·MIME만 센다.
  const response = await request.get('/maplibre/maplibre-gl-shared.mjs');
  expect(response.status()).toBe(200);
  expect(response.headers()['content-type'] ?? '').toMatch(/javascript/);
});

test('복사된 maplibre worker가 브라우저에서 module worker로 실제로 뜬다', async ({ page }) => {
  // 정적 서빙만 세면 "파일은 있는데 worker로는 못 뜨는" 경우(MIME·상대 import 깨짐)를 놓친다.
  await page.goto('/legal/terms-of-service');
  const outcome = await page.evaluate(
    () =>
      new Promise<string>((resolve) => {
        const worker = new Worker('/maplibre/maplibre-gl-worker.mjs', { type: 'module' });
        const timer = setTimeout(() => {
          worker.terminate();
          resolve('loaded');
        }, 2000);
        worker.addEventListener('error', (event) => {
          clearTimeout(timer);
          worker.terminate();
          resolve(`error: ${(event as ErrorEvent).message ?? 'unknown'}`);
        });
      }),
  );
  expect(outcome).toBe('loaded');
});
