/**
 * `/map?suggest=<lon>,<lat>` 딥링크 파라미터 파싱 — 지도 우클릭 없이 장소 제안 다이얼로그를
 * 특정 좌표로 미리 연다. 한국 범위 밖/형식 오류는 무시(null).
 */

import { CoordSchema } from '@tripmate/schemas';

export function parseSuggestParam(
  raw: string | string[] | undefined | null
): { lon: number; lat: number } | null {
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (!value) return null;
  const parts = value.split(',');
  if (parts.length !== 2) return null;
  const lon = Number(parts[0]);
  const lat = Number(parts[1]);
  const parsed = CoordSchema.safeParse({ lon, lat });
  return parsed.success ? parsed.data : null;
}
