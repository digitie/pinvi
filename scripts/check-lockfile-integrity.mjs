#!/usr/bin/env node
/**
 * package-lock.json의 무결성 해시 보유율을 검사한다 (T-358).
 *
 * 왜 있나: T-352에서 lockfile을 `npm install --package-lock-only`로 재생성했더니
 * 실제 패키지 1106개 중 **53개(4.8%)에만** `integrity`가 남았다. 그 플래그는 타르볼을
 * 받지 않으므로, 로컬 캐시나 기존 node_modules로 만족되는 항목에는 `resolved`/`integrity`를
 * 적지 않는다. 결과적으로 `npm ci`가 패키지 대부분을 **무결성 검증 없이** 설치하게 된다.
 * 로컬 4개 게이트도 CI도 이것을 잡지 못해 그대로 머지됐다.
 *
 * 그래서 lockfile을 다시 만들 때는 `--package-lock-only`가 아니라 전체 `npm install`을 쓴다.
 * 이 스크립트는 그 규칙을 실행 가능한 가드로 옮긴 것이다.
 *
 * 검사 대상에서 빼는 것 (원래 resolved/integrity가 없는 게 정상):
 *   - root 항목("")
 *   - workspace 링크(`link: true`)와 `apps/*` · `packages/*` 자체 항목
 *   - `file:` 프로토콜로 참조하는 vendored tarball (resolved는 있고 integrity는 없을 수 있다)
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const LOCKFILE = resolve(HERE, '..', 'package-lock.json');

/** 이 비율 미만이면 실패한다. 정상 재생성이면 100%에 가깝다. */
const MIN_RATIO = 0.99;

const lock = JSON.parse(readFileSync(LOCKFILE, 'utf8'));
const packages = lock.packages ?? {};

const audited = [];
for (const [path, entry] of Object.entries(packages)) {
  if (!path) continue; // root
  if (entry.link) continue; // workspace 심볼릭 링크
  if (/^(apps|packages)\//.test(path)) continue; // workspace 자체
  if (typeof entry.resolved === 'string' && entry.resolved.startsWith('file:')) continue;
  audited.push([path, entry]);
}

const missing = audited.filter(([, e]) => !e.integrity);
const total = audited.length;
const have = total - missing.length;
const ratio = total === 0 ? 1 : have / total;

console.log(`lockfile 무결성 검사 — ${have}/${total} (${(ratio * 100).toFixed(1)}%)`);

if (ratio >= MIN_RATIO) {
  console.log('OK');
  process.exit(0);
}

console.error('');
console.error(`FAIL — integrity 누락 ${missing.length}개 (허용 하한 ${(MIN_RATIO * 100).toFixed(0)}%)`);
console.error('');
console.error('lockfile을 `npm install --package-lock-only`로 만들면 이렇게 된다.');
console.error('전체 설치로 다시 만들어라:');
console.error('');
console.error('    rm -f package-lock.json && npm install');
console.error('');
console.error('누락 예시 (최대 10개):');
for (const [path] of missing.slice(0, 10)) {
  console.error(`  - ${path}`);
}
process.exit(1);
