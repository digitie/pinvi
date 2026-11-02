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
 * prod 실측(2026-11-02 n150 e2e): PinVi 지도마다 콘솔에 그 오류가 남았다. 지금 PinVi 지도는
 * raster(VWorld) 바탕지도와 HTML 마커만 써서 worker 없이도 그려지지만, worker를 쓰는
 * GeoJSON/벡터 source(경로선·영역 등)는 worker가 없으면 tile을 하나도 만들지 못한다 —
 * kor-travel-map admin은 2026-09-18 바로 그 때문에 zoom 14 이상 마커가 0개였고 같은 처방으로
 * 고쳤다.
 *
 * 처방: worker와 그 형제 파일(`maplibre-gl-shared.mjs`)을 **같은 디렉터리**에 복사해 정적으로
 * 서빙하고 `setWorkerUrl`로 그 경로를 가리킨다(`components/map/vworldPrimitives.tsx`). maplibre 6.15의
 * shared 청크는 비어 있고 worker는 자기완결이지만, 버전에 따라 worker가 shared를 상대 경로로
 * import하므로(kor-travel-map admin 실측) 함께 옮겨 둔다.
 *
 * 출력 위치는 실행 디렉터리 기준 `public/maplibre/`다 — npm script로 `apps/web`에서 돈다.
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
