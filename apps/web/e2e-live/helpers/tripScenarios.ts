/**
 * Loader for the data-driven trip scenarios (`e2e-live/catalog/trip-scenarios/*.yaml`, area `trs`).
 *
 * apps/web carries no YAML dependency (build-index.mjs reads the area catalogs line by line too), so
 * the scenario files use a fixed subset of YAML and this loader parses exactly that subset — anything
 * else is rejected with `file:line` and the reason:
 *
 *   - id: TRS-CG-001                       # TRS-<2..3 letters>-<3 digits>, unique across files
 *     title: "…"                           # double-quoted JSON string
 *     style: heritage                      # one of STYLES
 *     days: 2                              # 1..7
 *     start_offset_days: 3                 # 0..60, trip start = today (KST) + offset
 *     priority: P2                         # P1 | P2 | P3
 *     tags: [heritage, food, mobile]       # `mobile` = also runs on the mobile project
 *     places:                              # 1..6 per day, every day of the trip has ≥ 1 place
 *       - {day: 1, query: "…", expect_name_contains: "…", family: heritage, source: feature}
 *     checks:                              # or `checks: []`
 *       - optimize_day: 1                  # day-number checks: optimize_day reorder_day weather_day delete_day
 *       - date_shift: 1                    # shift the trip by N days (≠ 0)
 *       - share_readonly                   # flag checks: share_readonly copy_trip
 *     notes: "…"
 *
 * No Node-only globals at module scope beyond `fs`/`path`, so vitest (tests/tripScenariosCatalog.test.ts)
 * and Playwright both import it.
 */
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';

export const STYLES = [
  'sea', 'mountain', 'city', 'heritage', 'food', 'family', 'camping', 'island', 'festival', 'wellness',
  'drive', 'culture', 'nature', 'mixed',
] as const;
export const FAMILIES = [
  'lodging', 'food', 'cafe', 'heritage', 'museum', 'park', 'beach', 'trail', 'festival', 'market', 'camping',
  'spa', 'leisure', 'transport', 'parking', 'rest_area', 'shopping', 'culture', 'nature', 'religious',
] as const;
export const SOURCES = ['feature', 'kakao', 'naver'] as const;
export const DAY_CHECKS = ['optimize_day', 'reorder_day', 'weather_day', 'delete_day'] as const;
export const FLAG_CHECKS = ['share_readonly', 'copy_trip'] as const;

export type Family = (typeof FAMILIES)[number];
export type PlaceSource = (typeof SOURCES)[number];
export type DayCheck = (typeof DAY_CHECKS)[number];
export type FlagCheck = (typeof FLAG_CHECKS)[number];

export interface ScenarioPlace {
  day: number;
  query: string;
  expect_name_contains: string;
  family: Family;
  source: PlaceSource;
}

export type ScenarioCheck =
  | { kind: DayCheck; day: number }
  | { kind: 'date_shift'; days: number }
  | { kind: FlagCheck };

export interface TripScenario {
  id: string;
  title: string;
  style: (typeof STYLES)[number];
  days: number;
  start_offset_days: number;
  priority: 'P1' | 'P2' | 'P3';
  tags: string[];
  mobile: boolean;
  places: ScenarioPlace[];
  checks: ScenarioCheck[];
  notes: string;
  /** Catalog file (basename) the scenario came from. */
  file: string;
}

export const MAX_DAYS = 7;
export const MAX_PLACES_PER_DAY = 6;
export const MAX_START_OFFSET = 60;
const ID_RE = /^TRS-[A-Z]{2,3}-\d{3}$/;

export class ScenarioSchemaError extends Error {
  constructor(file: string, line: number, reason: string) {
    super(`${file}:${line}: ${reason}`);
    this.name = 'ScenarioSchemaError';
  }
}

/** `e2e-live/catalog/trip-scenarios` next to this helper (works from Playwright and vitest). */
export const scenariosDir = path.resolve(__dirname, '..', 'catalog', 'trip-scenarios');

/* ------------------------------------------------------------------ scalar parsing */

function parseString(raw: string, fail: (r: string) => never): string {
  const v = raw.trim();
  if (!v.startsWith('"') || !v.endsWith('"') || v.length < 2) fail(`expected a double-quoted string, got ${v}`);
  try {
    return JSON.parse(v) as string;
  } catch {
    return fail(`bad string escape in ${v}`);
  }
}

function parseInt10(raw: string, what: string, fail: (r: string) => never): number {
  const v = raw.trim();
  if (!/^-?\d+$/.test(v)) fail(`${what} must be an integer, got '${v}'`);
  return Number(v);
}

function parseWord(raw: string, what: string, fail: (r: string) => never): string {
  const v = raw.trim();
  if (!/^[A-Za-z0-9_]+$/.test(v)) fail(`${what} must be a bare word, got '${v}'`);
  return v;
}

function oneOf<T extends string>(value: string, allowed: readonly T[], what: string, fail: (r: string) => never): T {
  if (!(allowed as readonly string[]).includes(value)) fail(`${what} '${value}' is not one of ${allowed.join('|')}`);
  return value as T;
}

/** `{k: v, k: "v", …}` — values are integers, bare words or double-quoted strings (commas allowed inside). */
function parseFlowMap(raw: string, fail: (r: string) => never): Map<string, string> {
  const v = raw.trim();
  if (!v.startsWith('{') || !v.endsWith('}')) fail(`expected a {flow mapping}, got ${v}`);
  const body = v.slice(1, -1);
  const out = new Map<string, string>();
  let i = 0;
  while (i < body.length) {
    while (body[i] === ' ' || body[i] === ',') i += 1;
    if (i >= body.length) break;
    const colon = body.indexOf(':', i);
    if (colon < 0) fail(`missing ':' in ${v}`);
    const key = body.slice(i, colon).trim();
    i = colon + 1;
    while (body[i] === ' ') i += 1;
    let value: string;
    if (body[i] === '"') {
      let j = i + 1;
      while (j < body.length && body[j] !== '"') j += body[j] === '\\' ? 2 : 1;
      if (j >= body.length) fail(`unterminated string in ${v}`);
      value = body.slice(i, j + 1);
      i = j + 1;
    } else {
      const comma = body.indexOf(',', i);
      const end = comma < 0 ? body.length : comma;
      value = body.slice(i, end).trim();
      i = end;
    }
    if (out.has(key)) fail(`duplicate key '${key}' in ${v}`);
    out.set(key, value);
  }
  return out;
}

/* ------------------------------------------------------------------ file parsing */

const SCALAR_KEYS = ['id', 'title', 'style', 'days', 'start_offset_days', 'priority', 'tags', 'notes'] as const;
const PLACE_KEYS = ['day', 'query', 'expect_name_contains', 'family', 'source'];

interface Draft {
  line: number;
  fields: Map<string, { value: string; line: number }>;
  places: Array<{ value: string; line: number }>;
  checks: Array<{ value: string; line: number }>;
}

/** Parses and validates one scenario file. Throws `ScenarioSchemaError` on the first problem. */
export function parseScenarioFile(text: string, file: string): TripScenario[] {
  const lines = text.split(/\r?\n/);
  const drafts: Draft[] = [];
  let current: Draft | null = null;
  let list: 'places' | 'checks' | null = null;

  lines.forEach((raw, idx) => {
    const lineNo = idx + 1;
    const fail = (reason: string): never => {
      throw new ScenarioSchemaError(file, lineNo, reason);
    };
    if (raw.trim() === '' || /^\s*#/.test(raw)) return;
    if (/\t/.test(raw)) fail('tabs are not allowed');
    let m: RegExpExecArray | null;
    if ((m = /^- id: (.+)$/.exec(raw))) {
      current = { line: lineNo, fields: new Map(), places: [], checks: [] };
      current.fields.set('id', { value: m[1]!, line: lineNo });
      drafts.push(current);
      list = null;
      return;
    }
    if (!current) return fail('content before the first "- id:" entry');
    const cur: Draft = current;
    if ((m = /^ {2}(places|checks):(.*)$/.exec(raw))) {
      const key = m[1] as 'places' | 'checks';
      const rest = m[2]!.trim();
      if (cur.fields.has(key)) fail(`duplicate key '${key}'`);
      cur.fields.set(key, { value: rest, line: lineNo });
      if (key === 'checks' && rest === '[]') {
        list = null;
        return;
      }
      if (rest !== '') fail(`'${key}:' must be followed by an indented list`);
      list = key;
      return;
    }
    if ((m = /^ {2}([a-z_]+): (.*)$/.exec(raw))) {
      const key = m[1]!;
      if (!(SCALAR_KEYS as readonly string[]).includes(key)) fail(`unknown scenario key '${key}'`);
      if (cur.fields.has(key)) fail(`duplicate key '${key}'`);
      cur.fields.set(key, { value: m[2]!, line: lineNo });
      list = null;
      return;
    }
    if ((m = /^ {4}- (.+)$/.exec(raw))) {
      if (!list) fail('list item outside places/checks');
      (list === 'places' ? cur.places : cur.checks).push({ value: m[1]!, line: lineNo });
      return;
    }
    fail(`unrecognised line: ${raw.trim()}`);
  });

  return drafts.map((d) => buildScenario(d, file));
}

function buildScenario(d: Draft, file: string): TripScenario {
  const at = (line: number) => (reason: string): never => {
    throw new ScenarioSchemaError(file, line, reason);
  };
  const field = (key: string) => {
    const f = d.fields.get(key);
    if (!f) at(d.line)(`missing '${key}'`);
    return f!;
  };
  const id = field('id').value.trim();
  if (!ID_RE.test(id)) at(d.line)(`id '${id}' must match TRS-<REGION>-<3 digits>`);
  const where = (line: number) => (reason: string): never => at(line)(`${id}: ${reason}`);

  const title = parseString(field('title').value, where(field('title').line));
  if (title.trim() === '') where(field('title').line)('empty title');
  if (title.startsWith('[e2e]')) where(field('title').line)('title must not carry the [e2e] prefix (added at runtime)');
  const style = oneOf(parseWord(field('style').value, 'style', where(field('style').line)), STYLES, 'style', where(field('style').line));
  const days = parseInt10(field('days').value, 'days', where(field('days').line));
  if (days < 1 || days > MAX_DAYS) where(field('days').line)(`days must be 1..${MAX_DAYS}`);
  const offset = parseInt10(field('start_offset_days').value, 'start_offset_days', where(field('start_offset_days').line));
  if (offset < 0 || offset > MAX_START_OFFSET) where(field('start_offset_days').line)(`start_offset_days must be 0..${MAX_START_OFFSET}`);
  const priority = oneOf(field('priority').value.trim(), ['P1', 'P2', 'P3'] as const, 'priority', where(field('priority').line));

  const tagsRaw = field('tags');
  const tm = /^\[(.*)\]$/.exec(tagsRaw.value.trim());
  if (!tm) where(tagsRaw.line)('tags must be a [flow, list]');
  const tags = tm![1]!.split(',').map((t) => t.trim()).filter(Boolean);
  for (const t of tags) parseWord(t, 'tag', where(tagsRaw.line));

  const notesRaw = d.fields.get('notes');
  const notes = notesRaw ? parseString(notesRaw.value, where(notesRaw.line)) : '';

  if (d.places.length === 0) where(d.line)('places must not be empty');
  const places: ScenarioPlace[] = d.places.map(({ value, line }) => {
    const fail = where(line);
    const map = parseFlowMap(value, fail);
    for (const key of map.keys()) if (!PLACE_KEYS.includes(key)) fail(`unknown place key '${key}'`);
    for (const key of PLACE_KEYS) if (!map.has(key)) fail(`place is missing '${key}'`);
    const day = parseInt10(map.get('day')!, 'day', fail);
    if (day < 1 || day > days) fail(`place day ${day} is outside 1..${days}`);
    const query = parseString(map.get('query')!, fail);
    const expectName = parseString(map.get('expect_name_contains')!, fail);
    if (query.trim() === '' || expectName.trim() === '') fail('query / expect_name_contains must not be empty');
    return {
      day,
      query,
      expect_name_contains: expectName,
      family: oneOf(map.get('family')!.trim(), FAMILIES, 'family', fail),
      source: oneOf(map.get('source')!.trim(), SOURCES, 'source', fail),
    };
  });
  const perDay = new Map<number, number>();
  for (const p of places) perDay.set(p.day, (perDay.get(p.day) ?? 0) + 1);
  for (let day = 1; day <= days; day += 1) {
    const n = perDay.get(day) ?? 0;
    if (n === 0) where(d.line)(`day ${day} has no places`);
    if (n > MAX_PLACES_PER_DAY) where(d.line)(`day ${day} has ${n} places (max ${MAX_PLACES_PER_DAY})`);
  }
  const external = places.filter((p) => p.source !== 'feature').length;
  if (external > 1) where(d.line)(`${external} kakao/naver picks (max 1 per scenario — they auto-create feature suggestions)`);

  const checks: ScenarioCheck[] = d.checks.map(({ value, line }) => {
    const fail = where(line);
    const v = value.trim();
    if ((FLAG_CHECKS as readonly string[]).includes(v)) return { kind: v as FlagCheck };
    const cm = /^([a-z_]+): (-?\d+)$/.exec(v);
    if (!cm) return fail(`unknown check '${v}'`);
    const kind = cm[1]!;
    const n = Number(cm[2]);
    if (kind === 'date_shift') {
      if (n === 0 || Math.abs(n) > 30) fail('date_shift must be a non-zero shift of at most 30 days');
      return { kind: 'date_shift', days: n };
    }
    const dayKind = oneOf(kind, DAY_CHECKS, 'check', fail);
    if (n < 1 || n > days) fail(`${kind} day ${n} is outside 1..${days}`);
    const onDay = perDay.get(n) ?? 0;
    if ((dayKind === 'optimize_day' || dayKind === 'reorder_day') && onDay < 2) {
      fail(`${kind}: day ${n} needs ≥ 2 places (has ${onDay})`);
    }
    if (dayKind === 'delete_day' && days < 2) fail('delete_day needs a trip of ≥ 2 days');
    return { kind: dayKind, day: n };
  });
  const seen = new Set<string>();
  for (const c of checks) {
    const key = JSON.stringify(c);
    if (seen.has(key)) where(d.line)(`duplicate check ${key}`);
    seen.add(key);
  }
  if (checks.filter((c) => c.kind === 'delete_day').length > 1) where(d.line)('at most one delete_day per scenario');

  return {
    id,
    title,
    style,
    days,
    start_offset_days: offset,
    priority,
    tags,
    mobile: tags.includes('mobile'),
    places,
    checks,
    notes,
    file,
  };
}

/** Every `*.yaml` under `dir`, sorted by file name; ids must be unique across files. */
export function loadTripScenarios(dir: string = scenariosDir): TripScenario[] {
  const files = readdirSync(dir).filter((f) => f.endsWith('.yaml')).sort();
  if (files.length === 0) throw new Error(`no trip scenario files in ${dir}`);
  const all: TripScenario[] = [];
  const seen = new Map<string, string>();
  for (const f of files) {
    for (const s of parseScenarioFile(readFileSync(path.join(dir, f), 'utf8'), f)) {
      const prev = seen.get(s.id);
      if (prev) throw new ScenarioSchemaError(f, 0, `duplicate id ${s.id} (also in ${prev})`);
      seen.set(s.id, f);
      all.push(s);
    }
  }
  return all;
}

/* ------------------------------------------------------------------ dates (KST) */

const KST_DATE = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' });

/** `YYYY-MM-DD` of today + `offset` in Asia/Seoul, whatever the runner's TZ is. */
export function kstDate(offset: number): string {
  const today = KST_DATE.format(new Date());
  const d = new Date(`${today}T00:00:00.000Z`);
  d.setUTCDate(d.getUTCDate() + offset);
  return d.toISOString().slice(0, 10);
}

/** Trip window of a scenario: start = today(KST) + offset, end = start + days − 1. */
export function scenarioDates(s: Pick<TripScenario, 'start_offset_days' | 'days'>, shift = 0): { start: string; end: string } {
  return { start: kstDate(s.start_offset_days + shift), end: kstDate(s.start_offset_days + shift + s.days - 1) };
}
