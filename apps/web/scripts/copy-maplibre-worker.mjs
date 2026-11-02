/**
 * maplibre-gl worker를 `public/maplibre/`로 복사한다.
 *
 * **왜 필요한가.** maplibre 6의 ESM 빌드(`maplibre-gl.mjs`)는 worker URL을
 * `import.meta.url`에서 유도한다. Next 프로덕션 빌드(webpack, ADR-066)는 그
 * `import.meta.url`을 **빌드 머신의 파일 경로**(`file:///repo/node_modules/maplibre-gl/dist/maplibre-gl.mjs`)로
 * 굳혀 버리고, maplibre는 `http(s)`가 아닌 URL이면 빈 문자열을 worker URL로 쓴다. 그러면
 * `new Worker("")`가 페이지 HTML을 worker로 띄우려다 실패한다 — 콘솔에
 * "Worker failed to load. Check that the worker URL is correct."가 남는다.
 *
 * prod 실측(2026-11-02 n150 e2e): 그 상태에서 지도 style이 `load`에 도달하지 못해
 * vworld-map-web `ClusterLayer`가 viewport를 한 번도 받지 못했고, **trip 지도에 POI 마커가
 * 한 개도 그려지지 않았다**("장소 4곳"인데 핀 0개). raster(VWorld)는 worker를 쓰지 않아
 * 바탕지도만 멀쩡했다. kor-travel-map admin이 2026-09-18 같은 증상을 같은 처방으로 고쳤다.
 *
 * 처방: worker와 그 형제 파일(`maplibre-gl-shared.mjs`, worker가 상대 경로로 import)을
 * **같은 디렉터리**에 복사해 정적으로 서빙하고 `setWorkerUrl`로 그 경로를 가리킨다
 * (`components/map/vworldPrimitives.tsx`). 둘을 함께 옮기지 않으면 상대 import가 깨진다.
 *
 * `predev`/`prebuild`에서 돈다.
 */

import { copyFileSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';

const WORKER_FILES = ['maplibre-gl-worker.mjs', 'maplibre-gl-shared.mjs'];

const require = createRequire(import.meta.url);
const dist = path.join(path.dirname(require.resolve('maplibre-gl/package.json')), 'dist');
const dest = path.join(process.cwd(), 'public', 'maplibre');

mkdirSync(dest, { recursive: true });
for (const file of WORKER_FILES) {
  copyFileSync(path.join(dist, file), path.join(dest, file));
}

console.log(`maplibre worker 복사: ${WORKER_FILES.join(', ')} -> ${dest}`);
