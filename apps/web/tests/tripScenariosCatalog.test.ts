import { describe, expect, it } from 'vitest';
import {
  ScenarioSchemaError,
  kstDate,
  loadTripScenarios,
  parseScenarioFile,
  scenarioDates,
} from '../e2e-live/helpers/tripScenarios';

// 데이터 기반 여행 시나리오(TRS-*) 카탈로그 — 스키마·분포 불변식. live 실행 없이 CI에서 잡는다.
describe('trip scenario catalog (e2e-live/catalog/trip-scenarios)', () => {
  const all = loadTripScenarios();

  it('loads 190 unique scenarios from the four region files', () => {
    expect(all).toHaveLength(190);
    expect(new Set(all.map((s) => s.id)).size).toBe(all.length);
    const byRegion = Object.fromEntries(
      ['CG', 'CJ', 'GS', 'JT'].map((r) => [r, all.filter((s) => s.id.startsWith(`TRS-${r}-`)).length]),
    );
    expect(byRegion).toEqual({ CG: 50, CJ: 45, GS: 50, JT: 45 });
  });

  it('keeps P1 near 10% and mobile-tagged near 10%', () => {
    const p1 = all.filter((s) => s.priority === 'P1').length / all.length;
    expect(p1).toBeGreaterThanOrEqual(0.08);
    expect(p1).toBeLessThanOrEqual(0.12);
    const mobile = all.filter((s) => s.mobile).length / all.length;
    expect(mobile).toBeGreaterThanOrEqual(0.08);
    expect(mobile).toBeLessThanOrEqual(0.12);
  });

  it('picks Map features (Kakao/Naver ≤ 1 per scenario and ≤ 10% of scenarios)', () => {
    const withExternal = all.filter((s) => s.places.some((p) => p.source !== 'feature')).length;
    expect(withExternal / all.length).toBeLessThanOrEqual(0.1);
  });

  it('mixes at least three place families per scenario', () => {
    const thin = all.filter((s) => new Set(s.places.map((p) => p.family)).size < 3).map((s) => s.id);
    expect(thin).toEqual([]);
  });
});

describe('trip scenario loader errors', () => {
  const ok = [
    '- id: TRS-XX-001',
    '  title: "테스트"',
    '  style: city',
    '  days: 2',
    '  start_offset_days: 3',
    '  priority: P2',
    '  tags: [food, culture]',
    '  places:',
    '    - {day: 1, query: "경복궁", expect_name_contains: "경복궁", family: heritage, source: feature}',
    '    - {day: 2, query: "a, b", expect_name_contains: "b", family: food, source: feature}',
    '  checks:',
    '    - weather_day: 1',
    '    - share_readonly',
    '  notes: ""',
  ];
  const parse = (lines: string[]) => parseScenarioFile(lines.join('\n'), 'x.yaml');
  const failsWith = (lines: string[], re: RegExp) => {
    expect(() => parse(lines)).toThrow(ScenarioSchemaError);
    expect(() => parse(lines)).toThrow(re);
  };

  it('parses the canonical subset (commas inside quoted values)', () => {
    const [s] = parse(ok);
    expect(s!.places[1]!.query).toBe('a, b');
    expect(s!.checks).toEqual([{ kind: 'weather_day', day: 1 }, { kind: 'share_readonly' }]);
  });

  it('reports file:line and the reason', () => {
    failsWith(ok.map((l) => l.replace('style: city', 'style: space')), /^x\.yaml:3: TRS-XX-001: style 'space'/);
    failsWith(ok.map((l) => l.replace('day: 2, query', 'day: 3, query')), /x\.yaml:10: .*outside 1\.\.2/);
    failsWith(ok.map((l) => l.replace('source: feature}', 'source: google}')), /source 'google'/);
    failsWith(ok.map((l) => l.replace('weather_day: 1', 'optimize_day: 1')), /needs ≥ 2 places/);
    failsWith([...ok, '  bogus: 1'], /unknown scenario key 'bogus'/);
    failsWith(ok.map((l) => l.replace('"테스트"', '테스트')), /double-quoted/);
    failsWith(ok.filter((l) => !l.includes('day: 2,')), /day 2 has no places/);
  });

  it('computes KST trip windows', () => {
    expect(kstDate(0)).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    const { start, end } = scenarioDates({ start_offset_days: 3, days: 2 });
    expect(start).toBe(kstDate(3));
    expect(end).toBe(kstDate(4));
  });
});
