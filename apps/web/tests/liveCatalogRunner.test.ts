import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { expect, it } from 'vitest';

const root = path.resolve(import.meta.dirname, '../../..');

function list(args: string[]) {
  // --list는 env 파일·Docker·브라우저·API 없이 실제 CLI parser와 카탈로그만 검사한다.
  const env = Object.fromEntries(
    Object.entries(process.env).filter(
      ([key]) => !key.startsWith('PINVI_') && !key.startsWith('PLAYWRIGHT_'),
    ),
  );
  return spawnSync('bash', ['scripts/n150-live-catalog.sh', '--list', ...args], {
    cwd: root,
    env: { ...env, NODE_ENV: process.env.NODE_ENV, PINVI_PLAYWRIGHT_RUNNER_REPO_ROOT: root },
    encoding: 'utf8',
    timeout: 20_000,
  });
}

it.skipIf(process.platform !== 'linux')(
  '실제 runner의 area+project가 spec 경로를 project로 삼키지 않는다',
  () => {
    const result = list(['--area', 'search', '--project', 'desktop']);
    expect(result.status, result.stderr).toBe(0);
    expect(result.stdout).toContain('search-basic.live.spec.ts');
    expect(result.stdout).toContain('[desktop]');
    expect(result.stdout).not.toContain('[mobile]');
  },
  25_000,
);

it.skipIf(process.platform !== 'linux')(
  '반복 project와 area도 둘 다 유지한다',
  () => {
    const result = list([
      '--area',
      'search',
      '--area',
      'nearby',
      '--project',
      'desktop',
      '--project',
      'mobile',
    ]);
    expect(result.status, result.stderr).toBe(0);
    expect(result.stdout).toContain('[desktop]');
    expect(result.stdout).toContain('[mobile]');
    expect(result.stdout).toContain('search-basic.live.spec.ts');
    expect(result.stdout).toContain('trip-map.live.spec.ts');
    expect(result.stdout).not.toContain('weather-trip-days.live.spec.ts');
  },
  25_000,
);

it.skipIf(process.platform !== 'linux')(
  'trs area는 trip-scenarios spec으로, mobile은 @mobile 시나리오만 고른다',
  () => {
    const desktop = list(['--area', 'trs', '--project', 'desktop', '--grep', 'TRS-CG']);
    expect(desktop.status, desktop.stderr).toBe(0);
    expect(desktop.stdout).toContain('scenarios.live.spec.ts');
    expect(desktop.stdout).toMatch(/Total: 50 tests/);
    const mobile = list(['--area', 'trs', '--project', 'mobile']);
    expect(mobile.status, mobile.stderr).toBe(0);
    expect(mobile.stdout).toMatch(/Total: 19 tests/);
    // opt-in: without --area trs the scenarios are never selected
    const plain = list(['--grep', 'TRS-CG-001', '--project', 'desktop']);
    expect(plain.stdout).toMatch(/Total: 0 tests/);
  },
  30_000,
);
