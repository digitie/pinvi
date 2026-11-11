// NativeWind5 RC 페어와 모바일/웹의 Tailwind4 정렬을 검사한다.
import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const json = (path) => JSON.parse(readFileSync(resolve(root, path), 'utf8'));
const mobile = json('apps/mobile/package.json'),
  web = json('apps/web/package.json'),
  lock = json('package-lock.json');
const wanted = {
  expo: '58.0.24',
  'expo-constants': '58.0.16',
  'expo-linking': '58.0.17',
  'expo-router': '58.0.31',
  'react-native': '0.88.1',
  'react-native-worklets': '0.13.1',
  nativewind: '5.0.0-rc.1',
  'react-native-css': '3.1.0-rc.1',
  tailwindcss: '4.3.5',
  '@tailwindcss/postcss': '4.3.5',
  lightningcss: '1.33.0+nativecss.fix.4',
  eslint: '10.14.0',
  'react-doctor': '0.9.22',
};
const deps = { ...mobile.dependencies, ...mobile.devDependencies },
  errors = [];
for (const [name, version] of Object.entries(wanted)) {
  const specification =
    name === 'lightningcss' ? 'file:../web/vendor/lightningcss-' + version + '.tgz' : version;
  if (deps[name] !== specification) errors.push(name + ': 모바일 exact 불일치');
  const got =
    lock.packages['apps/mobile/node_modules/' + name] ?? lock.packages['node_modules/' + name];
  if (got?.version !== version) errors.push(name + ': 모바일 lock 해석 불일치');
}
for (const name of ['tailwindcss', '@tailwindcss/postcss'])
  if ((web.dependencies?.[name] ?? web.devDependencies?.[name]) !== wanted[name])
    errors.push(name + ': 웹/모바일 불일치');
for (const [path, pkg] of Object.entries(lock.packages)) {
  if (path.endsWith('node_modules/tailwindcss') && pkg.version !== '4.3.5')
    errors.push(path + ': 중첩 Tailwind 구버전 ' + pkg.version);
  if (path.endsWith('node_modules/lightningcss') && pkg.version !== wanted.lightningcss)
    errors.push(path + ': 중첩 Lightning CSS 불일치 ' + pkg.version);
  if (/node_modules\/lightningcss-/.test(path))
    errors.push(path + ': stock Lightning CSS 바이너리 잔재');
  if (path.endsWith('node_modules/react-native-css-interop'))
    errors.push(path + ': v4 interop 잔재');
}
const css = readFileSync(resolve(root, 'apps/mobile/global.css'), 'utf8');
if (!/@import\s+["']tailwindcss\/utilities\.css["']\s*;/.test(css) || css.includes('@tailwind'))
  errors.push('모바일 CSS layer 이관 필요');
if (existsSync(resolve(root, 'apps/mobile/tailwind.config.js')))
  errors.push('모바일 Tailwind3 config 잔재');
const babel = readFileSync(resolve(root, 'apps/mobile/babel.config.js'), 'utf8');
if (/nativewind\/babel|jsxImportSource/.test(babel)) errors.push('Babel v4 설정 잔재');
const metro = readFileSync(resolve(root, 'apps/mobile/metro.config.js'), 'utf8');
if (!metro.includes('withNativewind(config)') || metro.includes('input:'))
  errors.push('Metro v5 통합 불일치');
execFileSync(
  process.execPath,
  [resolve(root, 'packages/design-tokens/scripts/build-theme.mjs'), '--check'],
  { stdio: 'inherit' },
);
if (errors.length) {
  console.error(errors.join('\n'));
  process.exitCode = 1;
} else console.log('NativeWind5 RC·Tailwind4·디자인 토큰 일치');
