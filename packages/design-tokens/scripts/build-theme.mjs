// 기존 preset을 정본으로 사용하여 Tailwind4 CSS 테마를 생성한다.
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const theme = require('../tailwind-preset.cjs').theme.extend;
const declarations = [];
function flatten(prefix, entries) {
  for (const [key, value] of Object.entries(entries)) {
    const name = key === 'DEFAULT' ? prefix : prefix + '-' + key;
    if (typeof value === 'object' && !Array.isArray(value)) flatten(name, value);
    else
      declarations.push(
        '  ' + name + ': ' + (Array.isArray(value) ? value.join(', ') : value) + ';',
      );
  }
}
for (const [field, prefix] of Object.entries({
  colors: '--color',
  fontFamily: '--font',
  borderRadius: '--radius',
  boxShadow: '--shadow',
  spacing: '--spacing',
  transitionDuration: '--duration',
  transitionTimingFunction: '--ease',
}))
  flatten(prefix, theme[field]);
let css =
  '/* 이 파일은 scripts/build-theme.mjs로 생성한다. 정본: tailwind-preset.cjs */\n@theme {\n' +
  declarations.join('\n') +
  '\n}\n';
for (const [key, value] of Object.entries(theme.zIndex))
  css += '@utility z-' + key + ' { z-index: ' + value + '; }\n';
for (const [key, value] of Object.entries(theme.minHeight))
  css += '@utility min-h-' + key + ' { min-height: ' + value + '; }\n';
for (const [key, value] of Object.entries(theme.minWidth))
  css += '@utility min-w-' + key + ' { min-width: ' + value + '; }\n';
const target = new URL('../theme.css', import.meta.url);
if (process.argv.includes('--check')) {
  if (readFileSync(target, 'utf8') !== css)
    throw new Error('Pinvi Tailwind4 CSS 테마를 재생성하세요.');
} else writeFileSync(target, css);
