/**
 * 주유소 정보 표시 규칙 — 웹 교통 상세·모바일 교통 카드가 같은 규칙을 쓴다.
 *
 * 기준은 kor-travel-transport 공개 유가 화면(`/public/fuel`)의 장소 상세다. 거기서 가져온 규칙:
 *
 * - **취급하지 않는 유종은 보이지 않는다.** 판매가가 양의 유한수일 때만 행을 만든다(transport
 *   `hasFuelPrice`). null·0·음수·NaN 행은 "판매 안 함"·"-"로도 그리지 않는다.
 * - 유종 이름·순서: transport `FUEL_PRODUCT_LABELS`(휘발유·고급유·경유·등유·LPG)와 그 화면의 행 순서
 *   (오피넷 유종 코드 오름차순 — transport가 `product_code`로 정렬해 낸다).
 * - 가격은 `1,689원/L`.
 * - 관측 시각(transport `observed_at` = 제공기관 갱신 시각, 없으면 수집 시각)이 7일(168시간)보다 오래면 "오래됨".
 * - 편의시설은 셀프·24시간·세차·정비·편의점 순서로, 값이 `true`인 것만.
 * - 상표는 오피넷 상표 코드가 이름보다 우선하고, 모르는 코드를 다른 정유사로 추측하지 않는다.
 *
 * transport 화면에 있지만 PinVi가 받지 못하는 것(품질인증·전산보고 표시, 시군구 가격 등급, 30일 그래프)은
 * 지어내지 않고 그리지 않는다 — Map `/v1/service/transport/*`가 그 값을 싣지 않는다.
 */

import type { FuelPrice, FuelStationItem, RestAreaFuelPrices } from '@pinvi/schemas';

/** 오피넷 유종 코드 → 표시 이름. transport `FUEL_PRODUCT_LABELS`와 같다. */
export const FUEL_PRODUCT_LABEL_BY_CODE: Readonly<Record<string, string>> = {
  B027: '휘발유',
  B034: '고급유',
  D047: '경유',
  C004: '등유',
  K015: 'LPG',
};

/** Map 표준 유종 키 → 오피넷 유종 코드(가격 추이처럼 키만 오는 응답용). */
export const FUEL_PRODUCT_CODE_BY_KEY: Readonly<Record<string, string>> = {
  gasoline: 'B027',
  premium_gasoline: 'B034',
  diesel: 'D047',
  kerosene: 'C004',
  lpg: 'K015',
};

/**
 * 유종 이름. 유종 코드(없으면 표준 키)로 transport와 같은 이름을 쓰고, 둘 다 모르면 Map이 준 이름,
 * 그것도 없으면 키 그대로.
 */
export function fuelProductLabel(
  productKey: string,
  productName?: string | null,
  productCode?: string | null,
): string {
  const code = productCode?.trim() || FUEL_PRODUCT_CODE_BY_KEY[productKey];
  const known = code ? FUEL_PRODUCT_LABEL_BY_CODE[code] : undefined;
  if (known) return known;
  return productName?.trim() || productKey;
}

/** 판매 중인 유종인가 — 가격이 양의 유한수일 때만(transport `hasFuelPrice`). */
export function isFuelPriceSold(price: number | null | undefined): price is number {
  return typeof price === 'number' && Number.isFinite(price) && price > 0;
}

/** `1,689원/L`. 판매 중인 가격(`isFuelPriceSold`)에만 쓴다. */
export function formatFuelPrice(price: number): string {
  return `${Math.round(price).toLocaleString('ko-KR')}원/L`;
}

/** KST 짧은 일시("26. 10. 23. 오전 9:00") — transport `dateTime`과 같은 형식. 읽을 수 없으면 null. */
export function fuelDateTime(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return null;
  return at.toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul',
    dateStyle: 'short',
    timeStyle: 'short',
  });
}

/** transport가 "오래됨"을 붙이는 나이 — 7일. */
export const FUEL_PRICE_OLD_AFTER_MS = 168 * 3_600_000;

/** 확인 시각이 7일보다 오래됐는가. 시각을 읽을 수 없으면 판단하지 않는다(false). */
export function isOldFuelObservation(iso: string | null | undefined, nowMs: number): boolean {
  if (!iso) return false;
  const at = Date.parse(iso);
  return Number.isFinite(at) && nowMs - at > FUEL_PRICE_OLD_AFTER_MS;
}

export interface FuelPriceRow {
  /** 행 key — 유종 코드(없으면 표준 키). */
  key: string;
  label: string;
  price: number;
  /**
   * 관측 시각(ISO) — transport `observed_at`과 같은 뜻: 제공기관이 이 가격을 마지막으로 바꾼 시각이 있으면 그것,
   * 없으면 transport가 이 가격을 수집한 시각. Map 상태 표면은 `observed_at`을 싣지 않아 같은 규칙으로 다시 만든다.
   */
  observedAt: string | null;
  /** 제공기관(오피넷·도로공사)이 이 가격을 마지막으로 바꾼 시각(ISO). 원천이 주지 않으면 null. */
  providerUpdatedAt: string | null;
  /** 관측 시각이 7일보다 오래됐다(transport "오래됨" — 공시가가 7일 넘게 그대로면 붙는다). */
  old: boolean;
}

function codeOrder(a: FuelPriceRow, b: FuelPriceRow): number {
  // transport는 유종 코드를 C collation으로 정렬해 낸다 — 같은 순서를 locale 없이 재현한다.
  if (a.key === b.key) return 0;
  return a.key < b.key ? -1 : 1;
}

/** 주유소 현재가 → 판매 중인 유종만, transport와 같은 순서·이름으로. */
export function fuelStationPriceRows(prices: readonly FuelPrice[], nowMs: number): FuelPriceRow[] {
  const rows = new Map<string, FuelPriceRow>();
  for (const price of prices) {
    if (!isFuelPriceSold(price.price)) continue;
    const key =
      price.product_code?.trim() ||
      FUEL_PRODUCT_CODE_BY_KEY[price.product_key] ||
      price.product_key;
    // 같은 유종이 두 번 오면 첫 행만(응답 순서를 바꾸지 않는다).
    if (rows.has(key)) continue;
    const observedAt = price.provider_updated_at ?? price.collected_at;
    rows.set(key, {
      key,
      label: fuelProductLabel(price.product_key, price.product_name, price.product_code),
      price: price.price,
      observedAt,
      providerUpdatedAt: price.provider_updated_at ?? null,
      old: isOldFuelObservation(observedAt, nowMs),
    });
  }
  return [...rows.values()].sort(codeOrder);
}

/** 휴게소 주유소 유가(휘발유·경유·LPG 세 칸) → 판매 중인 유종만. */
export function restAreaFuelPriceRows(
  prices: RestAreaFuelPrices | null | undefined,
  nowMs: number,
): FuelPriceRow[] {
  if (!prices) return [];
  const columns: [string, number | null | undefined][] = [
    ['B027', prices.gasoline_price],
    ['D047', prices.diesel_price],
    ['K015', prices.lpg_price],
  ];
  const old = isOldFuelObservation(prices.observed_at, nowMs);
  return columns
    .flatMap(([code, price]): FuelPriceRow[] =>
      isFuelPriceSold(price)
        ? [
            {
              key: code,
              label: FUEL_PRODUCT_LABEL_BY_CODE[code] ?? code,
              price,
              observedAt: prices.observed_at,
              providerUpdatedAt: null,
              old,
            },
          ]
        : [],
    )
    .sort(codeOrder);
}

// 지도 마커 가격 라벨 — transport `lib/place-marker-style.ts`(= Map 가격 마커)와 같은 짧은 표기·순서.
const MARKER_SHORT_LABEL: Readonly<Record<string, string>> = { B027: '휘', D047: '경', B034: '고' };
const MARKER_ORDER = ['B027', 'D047', 'B034', 'K015', 'C004'];

function markerOrder(key: string): number {
  const index = MARKER_ORDER.indexOf(key);
  return index === -1 ? MARKER_ORDER.length : index;
}

/** 마커 라벨 행(판매 중인 유종만, 휘발유 → 경유 → 고급유 → LPG → 등유). */
export function fuelMarkerPriceLines(rows: readonly FuelPriceRow[]): string[] {
  return [...rows]
    .sort((a, b) => markerOrder(a.key) - markerOrder(b.key) || (a.key < b.key ? -1 : 1))
    .map(
      (row) =>
        `${MARKER_SHORT_LABEL[row.key] ?? row.label} ${Math.round(row.price).toLocaleString('ko-KR')}`,
    );
}

/** 화면 낭독기용 가격 문구 — 짧은 표기 대신 유종 이름("휘발유 1,650원, 경유 1,540원"). */
export function fuelMarkerPriceSpeech(rows: readonly FuelPriceRow[]): string {
  return [...rows]
    .sort((a, b) => markerOrder(a.key) - markerOrder(b.key) || (a.key < b.key ? -1 : 1))
    .map((row) => `${row.label} ${Math.round(row.price).toLocaleString('ko-KR')}원`)
    .join(', ');
}

/**
 * 화면 면적 대비 마커가 많으면 묶는다 — transport `clusterAtScale`의 예산(화면 22,000px²당 1곳, 6~60곳).
 * PinVi는 주유소를 줌 11 이상에서만 받으므로 줌 조건은 없다.
 */
export function transportMarkerBudget(width: number, height: number): number {
  if (!Number.isFinite(width) || !Number.isFinite(height)) return 6;
  return Math.max(6, Math.min(60, Math.floor((width * height) / 22_000)));
}

/** 주유소 편의시설 — transport `FUEL_FACILITY_LABELS`와 같은 순서·이름, `true`인 것만. */
const FUEL_FACILITIES = [
  ['is_self', '셀프'],
  ['is_24h', '24시간'],
  ['has_carwash', '세차'],
  ['has_maintenance', '정비'],
  ['has_cvs', '편의점'],
] as const satisfies readonly (readonly [keyof FuelStationItem, string])[];

export function fuelStationFacilities(
  item: Pick<FuelStationItem, (typeof FUEL_FACILITIES)[number][0]>,
): string[] {
  return FUEL_FACILITIES.filter(([field]) => item[field] === true).map(([, label]) => label);
}

export interface FuelBrand {
  /** 오피넷 상표 코드. 코드도 이름도 별칭에 없으면 빈 문자열. */
  code: string;
  name: string;
  /** 상표 이미지 파일 이름(웹 `public/fuel-brands/`). 공통 로고가 없거나 모르면 null. */
  logo: string | null;
}

// transport `lib/fuel-brands.ts`와 같은 표. 코드가 있으면 이름보다 우선한다 — 자가상표를 정유사로 추측하지 않는다.
const BRANDS: Readonly<Record<string, FuelBrand>> = {
  SKE: { code: 'SKE', name: 'SK에너지', logo: 'sk.gif' },
  GSC: { code: 'GSC', name: 'GS칼텍스', logo: 'gs.gif' },
  HDO: { code: 'HDO', name: 'HD현대오일뱅크', logo: 'hy.gif' },
  SOL: { code: 'SOL', name: 'S-OIL', logo: 'soil.gif' },
  SKG: { code: 'SKG', name: 'SK가스', logo: 'sk_gas.gif' },
  E1G: { code: 'E1G', name: 'E1', logo: 'e1.gif' },
  NCO: { code: 'NCO', name: '남해화학클린오일', logo: 'nc.gif' },
  NHO: { code: 'NHO', name: '농협알뜰 (NH-OIL)', logo: 'nho.gif' },
  RTO: { code: 'RTO', name: '알뜰주유소', logo: 'rto.gif' },
  RTE: { code: 'RTE', name: '자영알뜰', logo: 'rto.gif' },
  RTX: { code: 'RTX', name: '고속도로알뜰 (EX-OIL)', logo: 'rtx.gif' },
  ETC: { code: 'ETC', name: '자가상표', logo: null },
};

const BRAND_ALIASES: Readonly<Record<string, string>> = {
  SK에너지: 'SKE',
  SKENERGY: 'SKE',
  GS칼텍스: 'GSC',
  GSCALTEX: 'GSC',
  현대오일뱅크: 'HDO',
  HD현대오일뱅크: 'HDO',
  HYUNDAIOILBANK: 'HDO',
  HDHYUNDAIOILBANK: 'HDO',
  SOIL: 'SOL',
  에쓰오일: 'SOL',
  에스오일: 'SOL',
  SK가스: 'SKG',
  SKGAS: 'SKG',
  E1: 'E1G',
  남해화학클린오일: 'NCO',
  NHOIL: 'NHO',
  농협알뜰: 'NHO',
  알뜰주유소: 'RTO',
  알뜰: 'RTO',
  자영알뜰: 'RTE',
  고속도로알뜰: 'RTX',
  EXOIL: 'RTX',
  자가상표: 'ETC',
};

const normalizeBrandName = (value: string) => value.toUpperCase().replace(/[\s\-·]/g, '');

/**
 * 상표. 원천이 상표를 하나도 주지 않으면 null(표시하지 않는다). 모르는 코드는 원천 이름을 그대로 쓰고
 * 로고를 붙이지 않는다.
 */
export function fuelBrand(code?: string | null, name?: string | null): FuelBrand | null {
  const key = code?.trim().toUpperCase();
  const label = name?.trim();
  if (key) return BRANDS[key] ?? { code: key, name: label || '상표 미확인', logo: null };
  if (!label) return null;
  const alias = BRAND_ALIASES[normalizeBrandName(label)];
  return (alias ? BRANDS[alias] : undefined) ?? { code: '', name: label, logo: null };
}
