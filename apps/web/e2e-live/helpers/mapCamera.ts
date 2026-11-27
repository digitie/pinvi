/** MapLibre의 실제 지도·camera를 읽는 live 검증용 helper. 제품 API를 대체하지 않는다. */
import { type JSHandle, type Page } from '@playwright/test';
import type { MapLibreMap } from 'vworld-map-web';

export async function renderedMap(page: Page): Promise<JSHandle<MapLibreMap>> {
  // 설치된 vworld-map-web의 MapStore provider를 읽는다. 앱에 전역 debug 핸들을 추가하지 않는다.
  return (await page.waitForFunction(
    () => {
      const element = document.querySelector('.maplibregl-map');
      if (!element) return null;
      type Fiber = {
        memoizedProps?: { value?: { getSnapshot?: () => { map?: MapLibreMap } } };
        return?: Fiber;
      };
      const record = element as unknown as Record<string, unknown>;
      const key = Object.keys(record).find((name) => name.startsWith('__reactFiber'));
      let fiber = key ? (record[key] as Fiber | undefined) : undefined;
      while (fiber) {
        const store = fiber.memoizedProps?.value;
        const map = store?.getSnapshot?.()?.map;
        if (map?.getCanvas) return map;
        fiber = fiber.return;
      }
      return null;
    },
    undefined,
    { timeout: 30_000 },
  )) as JSHandle<MapLibreMap>;
}

export async function waitForCamera(map: JSHandle<MapLibreMap>): Promise<void> {
  await map.evaluate(async (m) => {
    if (m.isMoving()) await new Promise<void>((resolve) => m.once('moveend', () => resolve()));
  });
}
