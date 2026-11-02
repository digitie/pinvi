import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * maplibre worker 배선이 **실제로 성립하는지** 센다.
 *
 * 2026-11-02 prod e2e: webpack 빌드가 maplibre의 `import.meta.url`을 빌드 머신 `file://`
 * 경로로 굳혀 worker URL이 빈 문자열이 됐다("Worker failed to load"). worker를 쓰는
 * GeoJSON/벡터 source는 그 상태에서 tile을 하나도 만들지 못한다. 처방은 worker와 형제
 * 파일(`maplibre-gl-shared.mjs`)을 `public/maplibre/`로 복사하고 `setWorkerUrl`로 가리키는 것.
 *
 * 이름을 손으로 맞추지 않고 **세 조각이 서로 맞는지**를 센다: 복사 스크립트가 옮기는 파일 목록,
 * 소스가 가리키는 URL, 빌드 훅. 하나만 바뀌어도 빨개진다(kor-travel-map admin과 같은 검사).
 */

const WEB_ROOT = path.resolve(__dirname, '..');
const SCRIPT = path.join(WEB_ROOT, 'scripts', 'copy-maplibre-worker.mjs');
const MAP_PRIMITIVES = path.join(WEB_ROOT, 'components', 'map', 'vworldPrimitives.tsx');
const PACKAGE_JSON = path.join(WEB_ROOT, 'package.json');
const GITIGNORE = path.join(WEB_ROOT, '.gitignore');

function copiedFileNames(): string[] {
  const source = readFileSync(SCRIPT, 'utf8');
  const match = source.match(/WORKER_FILES\s*=\s*\[([^\]]+)\]/);
  if (match === null) throw new Error('복사 스크립트에서 WORKER_FILES를 찾지 못했다');
  return [...match[1]!.matchAll(/'([^']+)'/g)].map((m) => m[1]!);
}

function configuredWorkerUrl(): string {
  const source = readFileSync(MAP_PRIMITIVES, 'utf8');
  const match = source.match(/MAPLIBRE_WORKER_URL\s*=\s*'([^']+)'/);
  if (match === null) throw new Error('vworldPrimitives.tsx에 MAPLIBRE_WORKER_URL이 없다');
  if (!/setWorkerUrl\(\s*`\$\{MAPLIBRE_WORKER_URL\}/.test(source)) {
    throw new Error('vworldPrimitives.tsx가 setWorkerUrl(MAPLIBRE_WORKER_URL…)을 부르지 않는다');
  }
  return match[1]!;
}

describe('maplibre worker 배선', () => {
  it('worker와 그 형제 파일을 **함께** 옮긴다', () => {
    const files = copiedFileNames();
    // 둘 중 하나만 옮기면 worker가 상대 import를 풀지 못해 죽는다.
    expect(files).toContain('maplibre-gl-worker.mjs');
    expect(files).toContain('maplibre-gl-shared.mjs');
  });

  it('소스가 가리키는 URL이 실제로 복사되는 파일이다', () => {
    const url = configuredWorkerUrl();
    expect(url.startsWith('/maplibre/')).toBe(true);
    expect(copiedFileNames()).toContain(path.posix.basename(url));
  });

  it('빌드/개발 훅이 그 스크립트를 부른다', () => {
    const pkg = JSON.parse(readFileSync(PACKAGE_JSON, 'utf8')) as {
      scripts: Record<string, string>;
    };
    for (const hook of ['prebuild', 'predev']) {
      expect(pkg.scripts[hook] ?? '').toContain('copy-maplibre-worker.mjs');
    }
  });

  it('복사 결과(생성물)는 추적하지 않는다', () => {
    expect(readFileSync(GITIGNORE, 'utf8')).toMatch(/^\/public\/maplibre\/$/m);
  });

  it('스크립트를 실제로 돌리면 두 파일이 모두 생긴다', () => {
    // 선언이 아니라 **효과**를 센다 — 설치된 maplibre가 그 파일들을 더 이상 내보내지 않으면
    // (경로/이름 변경) 여기서 빨개진다. 그때는 배선 전체를 다시 봐야 한다.
    const workdir = mkdtempSync(path.join(tmpdir(), 'maplibre-worker-'));
    try {
      execFileSync(process.execPath, [SCRIPT], { cwd: workdir, stdio: 'pipe' });
      for (const file of copiedFileNames()) {
        expect(existsSync(path.join(workdir, 'public', 'maplibre', file))).toBe(true);
      }
    } finally {
      rmSync(workdir, { recursive: true, force: true });
    }
  });
});
