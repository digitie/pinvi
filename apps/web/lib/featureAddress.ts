import type { FeatureDetail } from '@pinvi/schemas';

/**
 * kor_travel_map 구조화 `address`에서 표시용 한 줄을 뽑는다 — 서버 detail-card의 `address_line`과 같은 규칙.
 * 도로명 → full → 법정동 주소(`legal`) → 지번 → "시도 시군구 읍면동" 순이고, 코드·우편번호 값은 쓰지
 * 않는다(예전에는 dict의 첫 문자열로 떨어져 "김삿갓면"만 보이거나 우편번호가 보일 수 있었다).
 */
export function addressLine(detail: Pick<FeatureDetail, 'address'> | null): string | null {
  const addr = detail?.address;
  if (!addr) return null;
  const pick = (key: string): string | null => {
    const value = addr[key];
    return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null;
  };
  const direct = pick('road') ?? pick('full') ?? pick('legal') ?? pick('jibun') ?? pick('name');
  if (direct) return direct;
  const admin = pick('admin');
  const parts = [pick('sido_name'), pick('sigungu_name')].filter(
    (region): region is string => region != null && !(admin != null && admin.includes(region)),
  );
  if (admin) parts.push(admin);
  return parts.length > 0 ? parts.join(' ') : null;
}
