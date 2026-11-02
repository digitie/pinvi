import { expect, test } from '@playwright/test';

// 2026-11-02 prod e2e — webpack 빌드가 maplibre 6의 worker URL(`import.meta.url` 유도)을 빌드 머신
// `file://` 경로로 굳혀 "Worker failed to load"가 났고, trip 지도에 POI 마커가 하나도 그려지지
// 않았다. 처방은 worker와 형제 파일을 `public/maplibre/`로 복사(`prebuild`)하고 `setWorkerUrl`로
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
