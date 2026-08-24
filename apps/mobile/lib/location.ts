import * as Location from 'expo-location';
import {
  LocationError,
  type LocationAdapter,
  type LocationOptions,
  type UserLocation,
} from '@pinvi/hooks';

/**
 * expo-location 기반 LocationAdapter.
 * `@pinvi/hooks`의 `useUserLocation(adapter, opts)`에 주입한다
 * (ADR-012, frontend.md §7). 웹은 navigator.geolocation 어댑터를 주입.
 */
export const expoLocationAdapter: LocationAdapter = {
  /**
   * 프롬프트 없이 권한 상태만 읽는다(T-325 자동 센터링 게이트).
   * `getForegroundPermissionsAsync`는 **요청이 아니라 조회**라 시스템 다이얼로그를 띄우지 않는다.
   * 다시 물을 수 없는 상태(`canAskAgain === false`)는 `denied`와 같게 다룬다.
   */
  async getPermissionState(): Promise<'granted' | 'prompt' | 'denied' | 'unsupported'> {
    try {
      const permission = await Location.getForegroundPermissionsAsync();
      if (permission.status === Location.PermissionStatus.GRANTED) return 'granted';
      if (permission.status === Location.PermissionStatus.DENIED) return 'denied';
      return permission.canAskAgain ? 'prompt' : 'denied';
    } catch {
      // 조회 자체가 실패하면 안전한 쪽(자동 취득 안 함)으로 답한다.
      return 'prompt';
    }
  },

  /** 권한 요청 없이 이미 있는 위치만 읽는다 — 자동 센터링이 진입을 지연시키지 않게 한다. */
  async getCachedPosition(maxAgeMs: number): Promise<UserLocation | null> {
    const last = await Location.getLastKnownPositionAsync({ maxAge: maxAgeMs });
    if (!last) return null;
    return {
      coord: { lon: last.coords.longitude, lat: last.coords.latitude },
      accuracy_m: last.coords.accuracy ?? 0,
      timestamp: last.timestamp,
      source: 'gps',
    };
  },

  async getCurrentPosition(opts?: LocationOptions): Promise<UserLocation> {
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== Location.PermissionStatus.GRANTED) {
      throw new LocationError('PERMISSION_DENIED', '위치 권한이 거부되었습니다.');
    }

    const position = await Location.getCurrentPositionAsync({
      accuracy: opts?.high_accuracy ? Location.Accuracy.High : Location.Accuracy.Balanced,
      // Android 기본값이 true라, 권한이 이미 있어도 시스템 "정확도 향상" 다이얼로그가 뜬다.
      // 진입 시 어떤 프롬프트도 띄우지 않는다는 T-325 계약을 지키려면 명시적으로 꺼야 한다.
      mayShowUserSettingsDialog: false,
    });

    return {
      coord: { lon: position.coords.longitude, lat: position.coords.latitude },
      accuracy_m: position.coords.accuracy ?? 0,
      timestamp: position.timestamp,
      source: 'gps',
    };
  },
};
