#!/usr/bin/env node
/**
 * Prints a pass/fail/skip table per catalog area (and per project) from a Playwright JSON report
 * written by playwright.live-catalog.config.ts. Usage: node scripts/live-catalog-summary.mjs <results.json>
 * Only counts and case ids are printed — never env values, URLs or error bodies.
 */
import { readFileSync } from 'node:fs';

const file = process.argv[2];
if (!file) {
  console.error('usage: live-catalog-summary.mjs <results.json>');
  process.exit(2);
}
const report = JSON.parse(readFileSync(file, 'utf8'));

const AREAS = ['trip', 'search', 'nearby', 'weather', 'share', 'poi', 'notify', 'admin', 'core'];
const rows = new Map();
const failed = [];

function areaOf(fileName) {
  // JSON `file` is relative to the config testDir (e2e-live/specs): '<area>/<file>.live.spec.ts'.
  const m = /(?:^|[\\/])(trip|search|nearby|weather|share|poi|notify|admin|core)[\\/][^\\/]+$/.exec(fileName ?? '');
  return m ? m[1] : 'other';
}

function bucket(area, project) {
  const key = `${area}\u0000${project}`;
  if (!rows.has(key)) rows.set(key, { area, project, passed: 0, failed: 0, skipped: 0, flaky: 0 });
  return rows.get(key);
}

function walk(suite, fileName) {
  const current = suite.file ?? fileName;
  for (const spec of suite.specs ?? []) {
    for (const t of spec.tests ?? []) {
      const b = bucket(areaOf(current), t.projectName ?? 'default');
      switch (t.status) {
        case 'expected':
          b.passed += 1;
          break;
        case 'skipped':
          b.skipped += 1;
          break;
        case 'flaky':
          b.flaky += 1;
          break;
        default:
          b.failed += 1;
          failed.push(`${t.projectName ?? ''}: ${spec.title}`);
      }
    }
  }
  for (const child of suite.suites ?? []) walk(child, current);
}
for (const s of report.suites ?? []) walk(s, s.file);

const pad = (v, n, right = false) => (right ? String(v).padStart(n) : String(v).padEnd(n));
const projects = [...new Set([...rows.values()].map((r) => r.project))].sort();
console.log('');
console.log(`${pad('area', 9)} ${pad('project', 9)} ${pad('pass', 6, true)} ${pad('fail', 6, true)} ${pad('skip', 6, true)} ${pad('flaky', 6, true)}`);
const total = { passed: 0, failed: 0, skipped: 0, flaky: 0 };
for (const area of [...AREAS, 'other']) {
  for (const project of projects) {
    const r = rows.get(`${area}\u0000${project}`);
    if (!r) continue;
    console.log(`${pad(area, 9)} ${pad(project, 9)} ${pad(r.passed, 6, true)} ${pad(r.failed, 6, true)} ${pad(r.skipped, 6, true)} ${pad(r.flaky, 6, true)}`);
    total.passed += r.passed;
    total.failed += r.failed;
    total.skipped += r.skipped;
    total.flaky += r.flaky;
  }
}
console.log(`${pad('total', 9)} ${pad('', 9)} ${pad(total.passed, 6, true)} ${pad(total.failed, 6, true)} ${pad(total.skipped, 6, true)} ${pad(total.flaky, 6, true)}`);
if (failed.length > 0) {
  console.log('');
  console.log('failed:');
  for (const f of failed) console.log(`  - ${f}`);
}
