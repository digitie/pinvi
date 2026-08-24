import { isInServiceArea } from '@pinvi/schemas';

/**
 * 지도 중심점 결정 — 웹/모바일 공용 순수 로직 (T-325).
 *
 * `docs/architecture/user-location.md` §1이 "지도 초기 중심점(앱 진입 시), 시군구 수준(~1km),
 * 세션당 1회"를 사양으로 두고 §5가 폴백 체인을 규정한다. 여기서는 그 결정을 **부작용 없는 함수**로
 * 고정해 웹(`FeatureMapView`)과 모바일(`app/(app)/map.tsx`)이 같은 규칙을 쓰게 한다.
 *
 * 플랫폼 코드가 하는 일은 입력 4개(동의·권한·좌표·가드)를 모으는 것뿐이고, "언제 위치를 취득해도
 * 되는가"와 "어디를 중심으로 잡는가"는 전부 이 파일이 답한다.
 */

/** 기본 중심점 — 서울시청(`docs/architecture/user-location.md` §5 fallback C). */
export const DEFAULT_MAP_CENTER: readonly [number, number] = [126.978, 37.5665];
export const DEFAULT_MAP_ZOOM = 12;
/** 자동 센터링 줌 — 시군구 수준(~1km, §1 표). 사용자를 핀포인트로 노출하지 않는다. */
export const AUTO_CENTER_ZOOM = 13;
/** "내 위치" 버튼 줌 — 사용자가 명시적으로 요청한 경우(높은 정확도, §1 표). */
export const MY_LOCATION_ZOOM = 14;

/** OS/브라우저 권한 상태. `prompt`는 "아직 묻지 않음" — 이 상태에서 자동 취득은 금지다. */
export type LocationPermissionState = 'granted' | 'prompt' | 'denied' | 'unsupported';

/** 위치 동의 상태. `unauthenticated`는 비로그인(동의 조회 401)이며 조용히 중단한다. */
export type LocationConsentState = 'granted' | 'missing' | 'unauthenticated' | 'error' | 'loading';

/** 자동 센터링을 하지 않은 이유 — 관측/테스트용. 사용자 문구가 아니다. */
export type AutoCenterSkipReason =
  | 'already-resolved'
  | 'user-interacted'
  | 'no-permission'
  | 'no-consent'
  | 'consent-unknown';

export interface AutoLocateGate {
  /** 이 세션에서 이미 자동 센터링 결정을 끝냈는가(성공/실패 무관). */
  alreadyResolved: boolean;
  /** 결정 전에 사용자가 지도를 움직였는가 — 움직였으면 카메라를 빼앗지 않는다. */
  userInteracted: boolean;
}

export interface ShouldAutoLocateInput {
  permission: LocationPermissionState;
  consent: LocationConsentState;
  gate: AutoLocateGate;
}

export type ShouldAutoLocateResult =
  | { proceed: true }
  | { proceed: false; skipReason: AutoCenterSkipReason };

/**
 * 자동 위치 취득을 해도 되는지 판정한다. **게이트 순서가 계약이다.**
 *
 * 권한 검사를 동의 검사보다 먼저 두는 이유: 권한 조회는 로컬·무비용이고 프롬프트를 띄우지 않으므로,
 * 권한이 없는 사용자에게 `GET /users/me/consents` 왕복을 발생시키지 않는다. 위치정보법이 요구하는 것은
 * "동의 없이 위치를 **취득**하지 말 것"이며 권한 상태를 읽는 것은 취득이 아니다 — 실제 취득은
 * 두 검사를 모두 통과한 뒤에만 일어난다.
 */
export function shouldAutoLocate({
  permission,
  consent,
  gate,
}: ShouldAutoLocateInput): ShouldAutoLocateResult {
  if (gate.alreadyResolved) {
    return { proceed: false, skipReason: 'already-resolved' };
  }
  if (gate.userInteracted) {
    return { proceed: false, skipReason: 'user-interacted' };
  }
  // `prompt`/`denied`/`unsupported` 전부 중단 — 진입만으로 권한 프롬프트를 띄우지 않는다.
  if (permission !== 'granted') {
    return { proceed: false, skipReason: 'no-permission' };
  }
  if (consent === 'granted') {
    return { proceed: true };
  }
  // 비로그인·조회 실패·로딩은 "동의를 확인하지 못한 상태"다. 확인되지 않으면 취득하지 않는다.
  return {
    proceed: false,
    skipReason: consent === 'missing' ? 'no-consent' : 'consent-unknown',
  };
}

/**
 * 좌표가 Pinvi 서비스 범위(남한) 안인지 — `@pinvi/schemas`의 `isInServiceArea`를 그대로 쓴다.
 *
 * 이전에는 `CoordSchema`(좌표 **입력 유효** 범위, lat 상한 43)를 그대로 썼다. 그것은 한반도
 * 전체를 덮는 사각형이라 온성(42.95)까지 "서비스 지역"으로 통과시켰다. 두 범위는 목적이 다르다 —
 * 하나는 "좌표로서 말이 되는가", 다른 하나는 "여기로 지도를 옮길 만한가"다.
 *
 * **사각형으로는 정확할 수 없다는 것이 이 판정의 성질이다.** 대마도와 평양은 여전히 통과하고,
 * 상한을 조여도 고쳐지지 않는다 — 개성(37.97)이 강원 고성(38.38)보다 남쪽이라 어떤 위도선도
 * 남북한을 가르지 못한다. 그래서 이 함수는 "국내인가"를 답한다고 주장하지 않는다. 틀렸을 때의
 * 결과는 사용자가 빈 지도를 보는 것뿐이다. **좌표 기반 차단에 쓰지 마라** — 그런 판정이 필요하면
 * kor-travel-geo 행정구역 조회를 써야 한다(ADR-064).
 */
export function isCoordInServiceArea(coord: { lon: number; lat: number }): boolean {
  return isInServiceArea(coord);
}

export interface ResolveMapCenterInput {
  /** 측위 성공 좌표. 실패했거나 아직 없으면 null. */
  deviceCoord: { lon: number; lat: number } | null;
}

export type MapCenterOutcome =
  /** 단말기 위치로 센터링한다. */
  | { center: [number, number]; zoom: number; source: 'device' }
  /** 기본 중심점을 유지한다. `outOfServiceArea`면 사용자에게 이유를 알린다. */
  | { center: [number, number]; zoom: number; source: 'default'; outOfServiceArea: boolean };

/**
 * 측위 결과로 최종 중심점을 정한다. 좌표가 국내 범위 밖이면 기본 중심점을 유지하고
 * `outOfServiceArea: true`를 돌려준다 — 호출부는 이때 마커도 찍지 않고 안내만 표시한다.
 */
export function resolveMapCenter({ deviceCoord }: ResolveMapCenterInput): MapCenterOutcome {
  if (deviceCoord === null) {
    return {
      center: [...DEFAULT_MAP_CENTER] as [number, number],
      zoom: DEFAULT_MAP_ZOOM,
      source: 'default',
      outOfServiceArea: false,
    };
  }
  if (!isCoordInServiceArea(deviceCoord)) {
    return {
      center: [...DEFAULT_MAP_CENTER] as [number, number],
      zoom: DEFAULT_MAP_ZOOM,
      source: 'default',
      outOfServiceArea: true,
    };
  }
  return { center: [deviceCoord.lon, deviceCoord.lat], zoom: AUTO_CENTER_ZOOM, source: 'device' };
}

/**
 * 관측·테스트용으로 노출할 좌표를 절사한다. 소수점 4자리는 약 11m 격자로,
 * `docs/architecture/user-location.md` §7의 정밀도 하한과 맞춘다 — 원좌표를 DOM에 그대로 싣지 않는다.
 */
export function coarseCoordText(value: number): string {
  return value.toFixed(4);
}
