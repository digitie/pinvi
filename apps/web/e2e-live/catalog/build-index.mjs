#!/usr/bin/env node
/**
 * Generates `apps/web/e2e-live/catalog/INDEX.md` from the nine area catalogs plus the data-driven
 * trip scenarios (`trip-scenarios/*.yaml`, area `trs`) and verifies them:
 *  - ids are unique across areas and match `<PREFIX>-<3 digits>` (`TRS-<REGION>-<3 digits>` for trs);
 *  - `automation` is one of scripted | manual | blocked;
 *  - every scripted case points at an existing spec file that mentions the id (trs: one data-driven
 *    spec that loads the scenario files — its full schema is enforced by `helpers/tripScenarios.ts`,
 *    covered by `tests/tripScenariosCatalog.test.ts`).
 * Run: `node apps/web/e2e-live/catalog/build-index.mjs` (add `--check` to only verify).
 *
 * The catalogs follow the SPEC.md schema closely enough that a line-oriented reader is sufficient;
 * no YAML dependency is added to apps/web for this.
 */
import { readdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const liveRoot = resolve(here, '..');
const check = process.argv.includes('--check');
const AREAS = [
  'trip',
  'search',
  'nearby',
  'weather',
  'share',
  'poi',
  'notify',
  'admin',
  'core',
  'trs',
];
/** Data-driven area: every scenario file under TRS_DIR is one case, all run by TRS_SPEC. */
const TRS_DIR = join(here, 'trip-scenarios');
const TRS_SPEC = 'specs/trip-scenarios/scenarios.live.spec.ts';
const TRS_SPEC_ANCHOR = 'loadTripScenarios';
const AUTOMATION = new Set(['scripted', 'manual', 'blocked']);

function unquote(value) {
  const v = value.trim();
  if ((v.startsWith("'") && v.endsWith("'")) || (v.startsWith('"') && v.endsWith('"'))) {
    return v.slice(1, -1).replace(/''/g, "'");
  }
  return v;
}

function parseCatalog(area) {
  if (area === 'trs') return parseTripScenarios();
  return parseCatalogFile(area, join(here, `${area}.yaml`));
}

/** `trip-scenarios/*.yaml`: id/title/priority/tags only; automation/spec are implied by the area. */
function parseTripScenarios() {
  if (!existsSync(TRS_DIR)) return [];
  return readdirSync(TRS_DIR)
    .filter((f) => f.endsWith('.yaml'))
    .sort()
    .flatMap((f) => parseCatalogFile('trs', join(TRS_DIR, f)))
    .map((c) => ({ ...c, automation: 'scripted', spec: TRS_SPEC }));
}

function parseCatalogFile(area, file) {
  const lines = readFileSync(file, 'utf8').split(/\r?\n/);
  const cases = [];
  let current = null;
  for (const raw of lines) {
    if (/^\s*#/.test(raw) || raw.trim() === '') continue;
    const start = /^- id:\s*(.+)$/.exec(raw);
    if (start) {
      current = {
        area,
        id: unquote(start[1]),
        title: '',
        priority: '',
        tags: [],
        automation: '',
        spec: '',
      };
      cases.push(current);
      continue;
    }
    if (!current) continue;
    const field = /^\s{2}(id|title|priority|tags|automation|spec):\s*(.*)$/.exec(raw);
    if (!field) continue;
    const [, key, value] = field;
    if (key === 'tags') {
      current.tags = unquote(value)
        .replace(/^\[|\]$/g, '')
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean);
    } else {
      current[key] = unquote(value);
    }
  }
  return cases;
}

const all = AREAS.flatMap(parseCatalog);
const errors = [];
const seen = new Map();
for (const c of all) {
  const idRe = c.area === 'trs' ? /^TRS-[A-Z]{2,3}-\d{3}$/ : /^[A-Z]+-\d{3}$/;
  if (!idRe.test(c.id)) errors.push(`${c.area}: bad id '${c.id}'`);
  if (seen.has(c.id)) errors.push(`duplicate id ${c.id} (${seen.get(c.id)} and ${c.area})`);
  seen.set(c.id, c.area);
  if (!AUTOMATION.has(c.automation)) errors.push(`${c.id}: automation '${c.automation}'`);
  if (!c.title) errors.push(`${c.id}: missing title`);
  if (!/^P[123]$/.test(c.priority)) errors.push(`${c.id}: priority '${c.priority}'`);
  if (c.automation === 'scripted') {
    const [specPath, anchor] = c.spec.split('#');
    const abs = join(liveRoot, specPath ?? '');
    if (!specPath || !existsSync(abs)) {
      errors.push(`${c.id}: spec file missing '${c.spec}'`);
    } else if (
      // oxlint-disable-next-line react-doctor/js-set-map-lookups -- string 부분 검색이며 Set 원소 비교로 대체할 수 없다.
      !readFileSync(abs, 'utf8').includes(anchor ?? (c.area === 'trs' ? TRS_SPEC_ANCHOR : c.id))
    ) {
      errors.push(`${c.id}: '${anchor ?? c.id}' not found in ${specPath}`);
    }
  }
}

const specFiles = AREAS.flatMap((a) => {
  const dir = join(liveRoot, 'specs', a === 'trs' ? 'trip-scenarios' : a);
  return existsSync(dir)
    ? readdirSync(dir)
        .filter((f) => f.endsWith('.live.spec.ts'))
        .map((f) => `specs/${a}/${f}`)
    : [];
});

if (errors.length > 0) {
  console.error(errors.join('\n'));
  process.exit(1);
}

const byArea = AREAS.map((area) => {
  const rows = all.filter((c) => c.area === area);
  const count = (s) => rows.filter((c) => c.automation === s).length;
  return {
    area,
    total: rows.length,
    scripted: count('scripted'),
    manual: count('manual'),
    blocked: count('blocked'),
  };
});
const totals = byArea.reduce(
  (acc, r) => ({
    total: acc.total + r.total,
    scripted: acc.scripted + r.scripted,
    manual: acc.manual + r.manual,
    blocked: acc.blocked + r.blocked,
  }),
  { total: 0, scripted: 0, manual: 0, blocked: 0 },
);

const esc = (s) => String(s).replace(/\|/g, '\\|');
const out = [];
out.push('# Live e2e catalog index');
out.push('');
out.push(
  'Generated by `node apps/web/e2e-live/catalog/build-index.mjs` from `<area>.yaml` + `trip-scenarios/*.yaml` (area `trs`) — do not edit by hand.',
);
out.push(
  'Runbook: `docs/runbooks/live-e2e-catalog.md`. Config: `apps/web/playwright.live-catalog.config.ts`.',
);
out.push('');
out.push('## Totals');
out.push('');
out.push('| area | total | scripted | manual | blocked |');
out.push('|---|---:|---:|---:|---:|');
for (const r of byArea)
  out.push(`| ${r.area} | ${r.total} | ${r.scripted} | ${r.manual} | ${r.blocked} |`);
out.push(
  `| **all** | **${totals.total}** | **${totals.scripted}** | **${totals.manual}** | **${totals.blocked}** |`,
);
out.push('');
out.push(`Spec files: ${specFiles.length}.`);
out.push('');
out.push('## Cases');
out.push('');
out.push('| id | area | title | priority | tags | automation | spec |');
out.push('|---|---|---|---|---|---|---|');
for (const c of all) {
  out.push(
    `| ${c.id} | ${c.area} | ${esc(c.title)} | ${c.priority} | ${c.tags.join(', ')} | ${c.automation} | ${c.spec ? `\`${c.spec}\`` : ''} |`,
  );
}
out.push('');

const target = join(here, 'INDEX.md');
const rendered = out.join('\n');
if (check) {
  const current = existsSync(target) ? readFileSync(target, 'utf8') : '';
  if (current !== rendered) {
    console.error('INDEX.md is stale — run node apps/web/e2e-live/catalog/build-index.mjs');
    process.exit(1);
  }
  console.log(`INDEX.md up to date (${totals.total} cases, ${totals.scripted} scripted)`);
} else {
  writeFileSync(target, rendered);
  console.log(
    `INDEX.md written (${totals.total} cases, ${totals.scripted} scripted, ${totals.manual} manual, ${totals.blocked} blocked)`,
  );
}
