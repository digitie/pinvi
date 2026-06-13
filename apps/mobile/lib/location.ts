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
  async getCurrentPosition(opts?: LocationOptions): Promise<UserLocation> {
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== Location.PermissionStatus.GRANTED) {
      throw new LocationError('PERMISSION_DENIED', '위치 권한이 거부되었습니다.');
    }

    const position = await Location.getCurrentPositionAsync({
      accuracy: opts?.high_accuracy
        ? Location.Accuracy.High
        : Location.Accuracy.Balanced,
    });

    return {
      coord: { lon: position.coords.longitude, lat: position.coords.latitude },
      accuracy_m: position.coords.accuracy ?? 0,
      timestamp: position.timestamp,
      source: 'gps',
    };
  },
};
