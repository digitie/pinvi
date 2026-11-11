export type GeoCandidate = Record<string, unknown>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function cleanText(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null;
}

function firstText(source: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = cleanText(source[key]);
    if (value) return value;
  }
  return null;
}

function nestedAddressLabel(value: unknown): string | null {
  if (typeof value === 'string') return cleanText(value);
  if (!isRecord(value)) return null;
  return firstText(value, [
    'label',
    'full',
    'full_address',
    'road',
    'road_address',
    'jibun',
    'jibun_address',
    'addr',
    'name',
  ]);
}

function regionLabel(value: unknown): string | null {
  if (!isRecord(value)) return null;
  const direct = firstText(value, ['label', 'full_name', 'name', 'legal_dong_name', 'emd_name']);
  if (direct) return direct;
  const joined = [value.sido_name, value.sigungu_name, value.emd_name]
    .map(cleanText)
    .filter(Boolean)
    .join(' ');
  return joined || null;
}

export function geoCandidateAddressLabel(candidate: GeoCandidate | null): string | null {
  if (!candidate) return null;
  return (
    firstText(candidate, [
      'address_label',
      'road_address',
      'jibun_address',
      'full_address',
      'address_name',
      'addr',
    ]) ??
    nestedAddressLabel(candidate.address) ??
    regionLabel(candidate.region) ??
    cleanText(candidate.name) ??
    null
  );
}
