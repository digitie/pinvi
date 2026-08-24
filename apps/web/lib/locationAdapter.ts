/**
 * 웹용 `LocationAdapter` — `navigator.geolocation` 기반.
 * `docs/architecture/user-location.md` §3.1.
 */
import {
  LocationError,
  type LocationAdapter,
  type LocationOptions,
  type UserLocation,
} from '@pinvi/hooks';

export const webLocationAdapter: LocationAdapter = {
  /**
   * 프롬프트 없이 권한 상태만 읽는다(T-325). Permissions API가 없거나 조회가 실패하면
   * **`'prompt'`로 답한다** — 낙관적으로 `'granted'`를 돌려주면 Permissions API에 geolocation이
   * 없는 브라우저(예: 일부 Safari 버전)에서 지도 진입만으로 권한 프롬프트가 뜬다.
   */
  async getPermissionState(): Promise<'granted' | 'prompt' | 'denied' | 'unsupported'> {
    if (typeof navigator === 'undefined' || !('geolocation' in navigator)) {
      return 'unsupported';
    }
    if (!navigator.permissions?.query) {
      return 'prompt';
    }
    try {
      const status = await navigator.permissions.query({ name: 'geolocation' });
      return status.state === 'granted' || status.state === 'denied' ? status.state : 'prompt';
    } catch {
      return 'prompt';
    }
  },

  async getCurrentPosition(opts: LocationOptions = {}): Promise<UserLocation> {
    if (typeof navigator === 'undefined' || !('geolocation' in navigator)) {
      throw new LocationError('UNSUPPORTED', '브라우저가 위치 기능을 지원하지 않습니다.');
    }
    return new Promise<UserLocation>((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          resolve({
            coord: {
              lon: position.coords.longitude,
              lat: position.coords.latitude,
            },
            accuracy_m: position.coords.accuracy,
            timestamp: position.timestamp,
            source: position.coords.accuracy < 100 ? 'gps' : 'network',
          });
        },
        (err) => {
          const code =
            err.code === 1
              ? 'PERMISSION_DENIED'
              : err.code === 2
                ? 'POSITION_UNAVAILABLE'
                : err.code === 3
                  ? 'TIMEOUT'
                  : 'UNKNOWN';
          reject(new LocationError(code, err.message));
        },
        {
          enableHighAccuracy: opts.high_accuracy ?? false,
          timeout: opts.timeout_ms ?? 10000,
          maximumAge: opts.max_age_ms ?? 30000,
        },
      );
    });
  },
};
