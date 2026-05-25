/**
 * 웹용 `LocationAdapter` — `navigator.geolocation` 기반.
 * `docs/architecture/user-location.md` §3.1.
 */
import {
  LocationError,
  type LocationAdapter,
  type LocationOptions,
  type UserLocation,
} from '@tripmate/hooks';

export const webLocationAdapter: LocationAdapter = {
  async getCurrentPosition(opts: LocationOptions = {}): Promise<UserLocation> {
    if (typeof navigator === 'undefined' || !('geolocation' in navigator)) {
      throw new LocationError('UNSUPPORTED', '브라우저가 위치 기능을 지원하지 않습니다.');
    }
    return new Promise<UserLocation>((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          resolve({
            coord: {
              longitude: position.coords.longitude,
              latitude: position.coords.latitude,
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
