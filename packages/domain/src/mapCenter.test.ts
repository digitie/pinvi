import { describe, expect, it } from 'vitest';
import {
  AUTO_CENTER_ZOOM,
  DEFAULT_MAP_CENTER,
  DEFAULT_MAP_ZOOM,
  coarseCoordText,
  isCoordInKorea,
  resolveMapCenter,
  shouldAutoLocate,
  type LocationConsentState,
  type LocationPermissionState,
} from './mapCenter';

const OPEN_GATE = { alreadyResolved: false, userInteracted: false };

function gateFor(permission: LocationPermissionState, consent: LocationConsentState) {
  return shouldAutoLocate({ permission, consent, gate: OPEN_GATE });
}

describe('shouldAutoLocate', () => {
  it('동의와 권한이 모두 있으면 진행한다', () => {
    expect(gateFor('granted', 'granted')).toEqual({ proceed: true });
  });

  // 진입만으로 OS/브라우저 프롬프트를 띄우지 않는다 — T-325의 핵심 계약.
  it.each<LocationPermissionState>(['prompt', 'denied', 'unsupported'])(
    '권한이 %s면 동의가 있어도 취득하지 않는다',
    (permission) => {
      expect(gateFor(permission, 'granted')).toEqual({
        proceed: false,
        skipReason: 'no-permission',
      });
    },
  );

  it('동의가 없으면 취득하지 않는다', () => {
    expect(gateFor('granted', 'missing')).toEqual({ proceed: false, skipReason: 'no-consent' });
  });

  // 비로그인·조회 실패·로딩은 "확인되지 않음"이며 확인 못 한 동의는 동의가 아니다.
  it.each<LocationConsentState>(['unauthenticated', 'error', 'loading'])(
    '동의 상태가 %s면 취득하지 않는다',
    (consent) => {
      expect(gateFor('granted', consent)).toEqual({
        proceed: false,
        skipReason: 'consent-unknown',
      });
    },
  );

  it('권한 검사가 동의 검사보다 먼저다 — 권한이 없으면 동의 조회 자체가 불필요하다', () => {
    expect(shouldAutoLocate({ permission: 'denied', consent: 'loading', gate: OPEN_GATE })).toEqual({
      proceed: false,
      skipReason: 'no-permission',
    });
  });

  it('이미 결정을 끝냈으면 세션 안에서 다시 취득하지 않는다', () => {
    const gate = { alreadyResolved: true, userInteracted: false };
    expect(shouldAutoLocate({ permission: 'granted', consent: 'granted', gate })).toEqual({
      proceed: false,
      skipReason: 'already-resolved',
    });
  });

  it('사용자가 지도를 움직였으면 카메라를 빼앗지 않는다', () => {
    const gate = { alreadyResolved: false, userInteracted: true };
    expect(shouldAutoLocate({ permission: 'granted', consent: 'granted', gate })).toEqual({
      proceed: false,
      skipReason: 'user-interacted',
    });
  });

  it('가드가 권한·동의보다 우선한다', () => {
    const gate = { alreadyResolved: true, userInteracted: true };
    expect(shouldAutoLocate({ permission: 'granted', consent: 'granted', gate }).proceed).toBe(
      false,
    );
  });
});

describe('isCoordInKorea', () => {
  it.each([
    ['서울시청', 126.978, 37.5665],
    ['제주', 126.5312, 33.4996],
    ['독도', 131.8664, 37.2411],
  ])('%s는 국내다', (_name, lon, lat) => {
    expect(isCoordInKorea({ lon, lat })).toBe(true);
  });

  it.each([
    ['도쿄', 139.6917, 35.6895],
    ['베이징', 116.4074, 39.9042],
    ['적도 부근', 126.978, 0],
  ])('%s는 국내가 아니다', (_name, lon, lat) => {
    expect(isCoordInKorea({ lon, lat })).toBe(false);
  });
});

describe('resolveMapCenter', () => {
  it('좌표가 없으면 기본 중심점을 유지한다', () => {
    expect(resolveMapCenter({ deviceCoord: null })).toEqual({
      center: [...DEFAULT_MAP_CENTER],
      zoom: DEFAULT_MAP_ZOOM,
      source: 'default',
      outOfServiceArea: false,
    });
  });

  it('국내 좌표면 단말기 위치로 센터링한다', () => {
    expect(resolveMapCenter({ deviceCoord: { lon: 129.0756, lat: 35.1796 } })).toEqual({
      center: [129.0756, 35.1796],
      zoom: AUTO_CENTER_ZOOM,
      source: 'device',
    });
  });

  it('국외 좌표면 센터링하지 않고 범위 밖임을 알린다', () => {
    expect(resolveMapCenter({ deviceCoord: { lon: 139.6917, lat: 35.6895 } })).toEqual({
      center: [...DEFAULT_MAP_CENTER],
      zoom: DEFAULT_MAP_ZOOM,
      source: 'default',
      outOfServiceArea: true,
    });
  });

  it('자동 센터링 줌은 "내 위치" 버튼보다 넓다 — 시군구 수준을 유지한다', () => {
    const outcome = resolveMapCenter({ deviceCoord: { lon: 126.978, lat: 37.5665 } });
    expect(outcome.zoom).toBe(AUTO_CENTER_ZOOM);
    expect(AUTO_CENTER_ZOOM).toBeLessThan(14);
  });

  it('기본 중심점 상수를 호출부가 변형할 수 없다', () => {
    const first = resolveMapCenter({ deviceCoord: null });
    first.center[0] = 0;
    expect(resolveMapCenter({ deviceCoord: null }).center).toEqual([...DEFAULT_MAP_CENTER]);
  });
});

describe('coarseCoordText', () => {
  it('소수점 4자리로 절사해 원좌표를 그대로 노출하지 않는다', () => {
    expect(coarseCoordText(37.566535123)).toBe('37.5665');
    expect(coarseCoordText(126.9779692)).toBe('126.9780');
  });
});
