import { describe, expect, it } from 'vitest';
import type { FuelPrice } from '@pinvi/schemas';
import {
  formatFuelPrice,
  fuelBrand,
  fuelMarkerPriceLines,
  fuelMarkerPriceSpeech,
  fuelProductLabel,
  fuelStationFacilities,
  fuelStationPriceRows,
  isFuelPriceSold,
  restAreaFuelPriceRows,
  transportMarkerBudget,
} from './fuelStation';

const NOW = Date.parse('2026-10-23T12:00:00+09:00');
const price = (
  code: string,
  key: string,
  value: number | null,
  at = '2026-10-23T09:00:00+09:00',
): FuelPrice => ({
  product_key: key,
  product_code: code,
  product_name: null,
  price: value,
  collected_at: at,
  provider_updated_at: null,
});

describe('fuel price rows', () => {
  it('취급하지 않는 유종(null·0·음수·NaN)은 행을 만들지 않는다', () => {
    const rows = fuelStationPriceRows(
      [
        price('B027', 'gasoline', 1689),
        price('D047', 'diesel', null),
        price('K015', 'lpg', 0),
        price('C004', 'kerosene', -1),
        price('B034', 'premium_gasoline', Number.NaN),
      ],
      NOW,
    );
    expect(rows.map((r) => r.label)).toEqual(['휘발유']);
  });

  it('transport와 같은 이름·순서(유종 코드 오름차순)다', () => {
    const rows = fuelStationPriceRows(
      [
        price('K015', 'lpg', 1100),
        price('D047', 'diesel', 1540),
        price('C004', 'kerosene', 1300),
        price('B034', 'premium_gasoline', 1950),
        price('B027', 'gasoline', 1689),
      ],
      NOW,
    );
    expect(rows.map((r) => r.label)).toEqual(['휘발유', '고급유', '등유', '경유', 'LPG']);
  });

  it('Map 이름보다 transport 이름이 우선하고, 모르는 유종은 Map 이름', () => {
    expect(fuelProductLabel('diesel', '자동차용경유')).toBe('경유');
    expect(fuelProductLabel('premium_gasoline', '고급휘발유', 'B034')).toBe('고급유');
    expect(fuelProductLabel('hydrogen', '수소')).toBe('수소');
    expect(fuelProductLabel('hydrogen')).toBe('hydrogen');
  });

  it('7일보다 오래 확인되지 않은 값만 오래됨이다', () => {
    const rows = fuelStationPriceRows(
      [
        price('B027', 'gasoline', 1689, '2026-10-16T11:59:00+09:00'),
        price('D047', 'diesel', 1540, '2026-10-16T12:01:00+09:00'),
      ],
      NOW,
    );
    expect(rows.map((r) => [r.key, r.old])).toEqual([
      ['B027', true],
      ['D047', false],
    ]);
  });

  it('오래됨은 transport observed_at 규칙 — 제공기관 갱신 시각이 있으면 그것으로 판정한다', () => {
    // 오늘 다시 수집했어도 공시가가 8일째 그대로면 오래됨(transport와 같다).
    const stale = {
      ...price('B027', 'gasoline', 1689),
      provider_updated_at: '2026-10-15T09:00:00+09:00',
    };
    const fresh = {
      ...price('D047', 'diesel', 1540, '2026-10-01T09:00:00+09:00'),
      provider_updated_at: '2026-10-22T09:00:00+09:00',
    };
    const rows = fuelStationPriceRows([stale, fresh], NOW);
    expect(rows.map((r) => [r.key, r.old, r.observedAt])).toEqual([
      ['B027', true, '2026-10-15T09:00:00+09:00'],
      ['D047', false, '2026-10-22T09:00:00+09:00'],
    ]);
  });

  it('같은 유종이 두 번 오면 첫 행만', () => {
    const rows = fuelStationPriceRows(
      [price('B027', 'gasoline', 1689), price('B027', 'gasoline', 1700)],
      NOW,
    );
    expect(rows.map((r) => r.price)).toEqual([1689]);
  });

  it('가격 문구와 판매 판정', () => {
    expect(formatFuelPrice(1689)).toBe('1,689원/L');
    expect(formatFuelPrice(1688.6)).toBe('1,689원/L');
    expect(isFuelPriceSold(1)).toBe(true);
    expect(isFuelPriceSold(0)).toBe(false);
    expect(isFuelPriceSold(null)).toBe(false);
    expect(isFuelPriceSold(Number.POSITIVE_INFINITY)).toBe(false);
  });

  it('휴게소 유가도 판매 중인 유종만', () => {
    const rows = restAreaFuelPriceRows(
      {
        gasoline_price: 1650,
        diesel_price: null,
        lpg_price: 0,
        observed_at: '2026-10-23T08:00:00+09:00',
      },
      NOW,
    );
    expect(rows.map((r) => [r.label, r.price])).toEqual([['휘발유', 1650]]);
    expect(restAreaFuelPriceRows(null, NOW)).toEqual([]);
  });
});

describe('fuel marker label', () => {
  it('Map·transport 가격 마커와 같은 짧은 표기·순서', () => {
    const rows = fuelStationPriceRows(
      [
        price('K015', 'lpg', 1100),
        price('D047', 'diesel', 1540),
        price('B027', 'gasoline', 1650),
        price('C004', 'kerosene', null),
      ],
      NOW,
    );
    expect(fuelMarkerPriceLines(rows)).toEqual(['휘 1,650', '경 1,540', 'LPG 1,100']);
    expect(fuelMarkerPriceSpeech(rows)).toBe('휘발유 1,650원, 경유 1,540원, LPG 1,100원');
  });

  it('화면 예산 — 22,000px²당 1곳, 6~60곳', () => {
    expect(transportMarkerBudget(375, 667)).toBe(11);
    expect(transportMarkerBudget(1440, 900)).toBe(58);
    expect(transportMarkerBudget(100, 100)).toBe(6);
    expect(transportMarkerBudget(4000, 3000)).toBe(60);
  });
});

describe('fuel station brand & facilities', () => {
  it('코드가 이름보다 우선하고 모르는 코드는 로고 없이 원천 이름', () => {
    expect(fuelBrand('SKE', '아무이름')).toEqual({ code: 'SKE', name: 'SK에너지', logo: 'sk.gif' });
    expect(fuelBrand('XYZ', '새상표')).toEqual({ code: 'XYZ', name: '새상표', logo: null });
    expect(fuelBrand('ETC', null)?.logo).toBeNull();
    expect(fuelBrand(null, 'GS칼텍스')?.code).toBe('GSC');
    expect(fuelBrand(null, '동네주유소')).toEqual({ code: '', name: '동네주유소', logo: null });
    expect(fuelBrand(null, null)).toBeNull();
  });

  it('편의시설은 true만, transport 순서', () => {
    expect(
      fuelStationFacilities({
        is_self: true,
        is_24h: false,
        has_carwash: true,
        has_maintenance: null,
        has_cvs: true,
      }),
    ).toEqual(['셀프', '세차', '편의점']);
    expect(fuelStationFacilities({})).toEqual([]);
  });
});
