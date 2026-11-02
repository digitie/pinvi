/**
 * NOAA sunrise/sunset (Solar Calculator spreadsheet algorithm), zenith 90.833°.
 * Accuracy ~1 min for Korean latitudes; the 2026-11-02 prod e2e measured KASI vs NOAA within ±1 min.
 * Returns KST clock minutes (0..1439) so the result can be compared to the UI's `formatKstTime` "HH:MM".
 */
const rad = (d: number) => (d * Math.PI) / 180;
const deg = (r: number) => (r * 180) / Math.PI;

export interface SunTimesKst {
  sunriseMin: number; // minutes after 00:00 KST
  sunsetMin: number;
  sunrise: string; // "HH:MM"
  sunset: string;
}

export function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

export function minToHhmm(min: number): string {
  const m = ((Math.round(min) % 1440) + 1440) % 1440;
  return `${pad2(Math.floor(m / 60))}:${pad2(m % 60)}`;
}

export function hhmmToMin(text: string): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(text.trim());
  if (!m) return null;
  return Number(m[1]) * 60 + Number(m[2]);
}

/** Circular difference in minutes between two clock times. */
export function clockDiffMin(a: number, b: number): number {
  const d = Math.abs(a - b) % 1440;
  return Math.min(d, 1440 - d);
}

export function noaaSunTimesKst(lat: number, lon: number, isoDate: string): SunTimesKst | null {
  const [y, mo, d] = isoDate.split('-').map(Number);
  if (!y || !mo || !d) return null;
  // Evaluate at local (KST) noon = 03:00 UTC.
  const jd = Date.UTC(y, mo - 1, d, 3, 0, 0) / 86_400_000 + 2_440_587.5;
  const jc = (jd - 2_451_545) / 36_525;

  const L0 = ((((280.46646 + jc * (36_000.76983 + jc * 0.0003032)) % 360) + 360) % 360);
  const M = 357.52911 + jc * (35_999.05029 - 0.0001537 * jc);
  const e = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc);
  const C =
    Math.sin(rad(M)) * (1.914602 - jc * (0.004817 + 0.000014 * jc)) +
    Math.sin(rad(2 * M)) * (0.019993 - 0.000101 * jc) +
    Math.sin(rad(3 * M)) * 0.000289;
  const trueLong = L0 + C;
  const omega = 125.04 - 1934.136 * jc;
  const appLong = trueLong - 0.00569 - 0.00478 * Math.sin(rad(omega));
  const meanObliq =
    23 + (26 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60) / 60;
  const obliq = meanObliq + 0.00256 * Math.cos(rad(omega));
  const decl = deg(Math.asin(Math.sin(rad(obliq)) * Math.sin(rad(appLong))));
  const y2 = Math.tan(rad(obliq / 2)) ** 2;
  const eqTime =
    4 *
    deg(
      y2 * Math.sin(2 * rad(L0)) -
        2 * e * Math.sin(rad(M)) +
        4 * e * y2 * Math.sin(rad(M)) * Math.cos(2 * rad(L0)) -
        0.5 * y2 * y2 * Math.sin(4 * rad(L0)) -
        1.25 * e * e * Math.sin(2 * rad(M)),
    );
  const cosHa =
    Math.cos(rad(90.833)) / (Math.cos(rad(lat)) * Math.cos(rad(decl))) -
    Math.tan(rad(lat)) * Math.tan(rad(decl));
  if (cosHa < -1 || cosHa > 1) return null; // polar day/night — not in Korea
  const ha = deg(Math.acos(cosHa));
  const solarNoonUtc = 720 - 4 * lon - eqTime; // minutes after 00:00 UTC
  const sunriseUtc = solarNoonUtc - ha * 4;
  const sunsetUtc = solarNoonUtc + ha * 4;
  const toKst = (min: number) => (((min + 540) % 1440) + 1440) % 1440;
  const sunriseMin = toKst(sunriseUtc);
  const sunsetMin = toKst(sunsetUtc);
  return { sunriseMin, sunsetMin, sunrise: minToHhmm(sunriseMin), sunset: minToHhmm(sunsetMin) };
}

/** Sanity pin used by the specs' self-check (2026-11-05, 영월 고씨굴 ≈ 128.47E 37.17N → KASI 06:54 / 17:25). */
export const NOAA_SELF_CHECK = {
  date: '2026-11-05',
  lat: 37.17,
  lon: 128.47,
  sunrise: '06:54',
  sunset: '17:25',
  toleranceMin: 3,
};
