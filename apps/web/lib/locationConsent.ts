/**
 * 위치 기능 동의(위치정보법/LBS) — `docs/compliance/lbs-act.md` §2.
 *
 * 위치 마커·거리·내 위치 등 LBS 기능 사용 전 `lbs_tos` + `location_collection` 동의가
 * (철회되지 않은 상태로) 필요하다. 회원가입 시 필수로 받지만, 사용자가 철회할 수 있으므로
 * 사용 시점에 다시 확인한다.
 */

import type { ConsentType, UserConsent } from '@tripmate/schemas';

export const LOCATION_CONSENT_TYPES: ConsentType[] = ['lbs_tos', 'location_collection'];
export const CONSENT_VERSION = 'v1.0';

/** 위치 동의 2종이 모두 유효(철회 안 됨)한가. */
export function hasLocationConsent(consents: UserConsent[]): boolean {
  return LOCATION_CONSENT_TYPES.every((type) =>
    consents.some((c) => c.consent_type === type && c.withdrawn_at == null)
  );
}

/** PUT /users/consents 에 보낼 위치 동의 아이템. */
export function locationConsentItems(): { consent_type: ConsentType; version: string }[] {
  return LOCATION_CONSENT_TYPES.map((consent_type) => ({
    consent_type,
    version: CONSENT_VERSION,
  }));
}
