import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { VWorldMapView, type VWorldMapHandle } from 'vworld-map-rn';
import { useUserLocation } from '@pinvi/hooks';
import {
  AUTO_CENTER_ZOOM,
  DEFAULT_MAP_CENTER,
  DEFAULT_MAP_ZOOM,
  MY_LOCATION_ZOOM,
  friendlyErrorText,
  resolveMapCenter,
  shouldAutoLocate,
} from '@pinvi/domain';
import { apiClient } from '../../lib/api';
import { useLocationConsent } from '../../lib/consents';
import { expoLocationAdapter } from '../../lib/location';
import { Body, Button, Card, Heading, Muted, Screen, Subheading } from '../../components/ui';

/**
 * 지도 화면 — VWorld + MapLibre (`vworld-map-rn`). VWorld 키는 앱에 번들하지 않고
 * `GET /mobile/vworld/token`으로 server-issued 발급받아 `apiKey`로 주입한다(ADR-043).
 * 내 위치 마커 + "현재 위치로" 카메라 이동(`VWorldMapHandle.flyTo`).
 *
 * 네이티브 모듈(`@maplibre/maplibre-react-native`)이 필요하므로 Expo Dev Client(EAS) 빌드에서만
 * 동작한다(Expo Go 미사용, ADR-043).
 */
/**
 * 자동 센터링 결정이 늦어도 지도가 영원히 placeholder로 남지 않게 하는 상한.
 * 웹보다 길게 잡는 이유는 네이티브 권한/측위 왕복이 브라우저보다 느리기 때문이다.
 */
const AUTO_CENTER_TIMEOUT_MS = 3_000;

/**
 * 세션당 1회(`docs/architecture/user-location.md` §1) — 모듈 스코프 in-memory 캐시.
 * 좌표를 SecureStore/AsyncStorage/서버 어디에도 남기지 않는다(§7). 앱을 다시 띄우면 초기화된다.
 */
let autoCenterSession: { done: true; coord: { lon: number; lat: number } | null } | null = null;

const VWorldTokenSchema = z.object({
  api_key: z.string(),
  key_source: z.literal('server-issued'),
  ttl_seconds: z.number(),
});

export default function MapScreen() {
  const mapRef = useRef<VWorldMapHandle>(null);
  const { location, error, loading, refresh } = useUserLocation(expoLocationAdapter, {
    high_accuracy: true,
    max_age_ms: 30_000,
  });

  /**
   * 진입 시 자동 센터링(T-325). `vworld-map-rn`은 `initialCenter`를 mount 시 1회만 읽고
   * map-ready 콜백도 노출하지 않으므로, 웹처럼 선언형으로 카메라를 옮길 수 없다.
   * 그래서 **결정이 끝날 때까지 지도 mount 자체를 미룬다** — 확정된 중심점으로 한 번에 마운트한다.
   */
  const [autoCenter, setAutoCenter] = useState<{
    resolved: boolean;
    center: [number, number];
    zoom: number;
    outOfServiceArea: boolean;
  }>({
    resolved: false,
    center: [...DEFAULT_MAP_CENTER] as [number, number],
    zoom: DEFAULT_MAP_ZOOM,
    outOfServiceArea: false,
  });
  // 위치 동의 gate(웹 handleMyLocation 대응) — 동의가 없거나 조회 실패면 OS 권한 요청 전에
  // 동의 안내를 먼저 띄운다. 설정에서 철회하면 같은 query가 갱신돼 다시 잠긴다.
  const consent = useLocationConsent();
  const [granting, setGranting] = useState(false);

  // 버튼으로 얻은 위치는 지도가 이미 떠 있으므로 명령형으로 옮긴다. 훅 콜백이 아니라 effect에서
  // 부르는 이유는 카메라 API 예외가 측위 실패로 오분류되지 않게 하기 위해서다.
  useEffect(() => {
    if (!location || !autoCenter.resolved) return;
    mapRef.current?.flyTo({
      center: [location.coord.lon, location.coord.lat],
      zoom: MY_LOCATION_ZOOM,
    });
  }, [location, autoCenter.resolved]);

  // 화면이 사라졌는지만 추적한다. effect 재실행으로 취소하면 진행 중이던 측위 결과가 버려진다.
  const unmountedRef = useRef(false);
  useEffect(() => {
    return () => {
      unmountedRef.current = true;
    };
  }, []);
  // 자동 센터링은 화면당 1회만 시작한다.
  const autoCenterStartedRef = useRef(false);

  /**
   * 자동 센터링 게이트 — 웹과 같은 순수 로직(`shouldAutoLocate`)을 쓴다.
   * 권한이 `granted`가 아니면 좌표를 취득하지 않고, 어떤 프롬프트도 띄우지 않는다.
   *
   * 타임아웃과 실제 측위가 경쟁한다. 타임아웃이 먼저 이겨 기본 중심점으로 지도를 띄웠더라도
   * **뒤늦게 도착한 좌표를 버리지 않고** 카메라로 옮긴다 — `initialCenter`는 mount 시 1회만
   * 읽히므로 그때는 명령형 `flyTo`가 유일한 수단이다.
   */
  useEffect(() => {
    if (autoCenterStartedRef.current) return;
    // 동의 판정이 끝나야 게이트를 통과시킬 수 있다. 늦어지면 아래 타임아웃이 지도를 먼저 띄운다.
    if (consent.status === 'loading') return;
    autoCenterStartedRef.current = true;

    let resolvedOnce = false;

    const settle = (coord: { lon: number; lat: number } | null) => {
      if (unmountedRef.current) return;
      const outcome = resolveMapCenter({ deviceCoord: coord });
      if (resolvedOnce) {
        // 이미 지도가 떠 있다 — 늦게 온 좌표는 카메라 이동으로 반영한다.
        if (outcome.source === 'device') {
          mapRef.current?.flyTo({ center: outcome.center, zoom: AUTO_CENTER_ZOOM });
        }
        return;
      }
      resolvedOnce = true;
      setAutoCenter({
        resolved: true,
        center: outcome.center,
        zoom: outcome.source === 'device' ? AUTO_CENTER_ZOOM : DEFAULT_MAP_ZOOM,
        outOfServiceArea: outcome.source === 'default' && outcome.outOfServiceArea,
      });
    };

    // 결정이 늦어도 지도는 뜬다.
    const timeout = setTimeout(() => settle(null), AUTO_CENTER_TIMEOUT_MS);

    void (async () => {
      const permission = (await expoLocationAdapter.getPermissionState?.()) ?? 'prompt';
      if (unmountedRef.current) return;

      const gate = shouldAutoLocate({
        permission,
        consent: consent.status,
        gate: { alreadyResolved: false, userInteracted: false },
      });
      if (!gate.proceed) {
        clearTimeout(timeout);
        settle(null);
        return;
      }

      // 권한·동의를 모두 통과한 뒤에만 세션 캐시를 본다 — 캐시가 게이트를 우회하면 안 된다.
      if (autoCenterSession?.done) {
        clearTimeout(timeout);
        settle(autoCenterSession.coord);
        return;
      }

      try {
        // 최근 위치가 있으면 그것으로 즉시 확정해 진입을 지연시키지 않는다.
        const cached = await expoLocationAdapter.getCachedPosition?.(300_000);
        const loc =
          cached ?? (await expoLocationAdapter.getCurrentPosition({ high_accuracy: false }));
        if (unmountedRef.current) return;
        const outcome = resolveMapCenter({ deviceCoord: loc.coord });
        // 국내 좌표만 캐시한다 — 국외 좌표를 캐시하면 재진입 때 안내 없이 조용히 넘어간다.
        autoCenterSession = {
          done: true,
          coord: outcome.source === 'device' ? loc.coord : null,
        };
        clearTimeout(timeout);
        settle(loc.coord);
      } catch {
        if (unmountedRef.current) return;
        // 자동 경로는 재시도하지 않는다. "현재 위치로" 버튼은 언제든 쓸 수 있다.
        autoCenterSession = { done: true, coord: null };
        clearTimeout(timeout);
        settle(null);
      }
    })();

    return () => {
      clearTimeout(timeout);
    };
  }, [consent.status]);

  const onMyLocation = useCallback(() => {
    if (consent.status === 'granted') {
      refresh();
      return;
    }
    if (consent.status === 'loading') return;
    Alert.alert(
      '위치정보 이용 동의',
      '내 위치 표시·주변 검색 등 위치 기반 기능을 사용하려면 위치기반서비스 이용약관과 ' +
        '개인위치정보 수집·이용(모두 필수)에 동의해야 합니다.',
      [
        { text: '취소', style: 'cancel' },
        {
          text: '동의하고 사용',
          onPress: () => {
            setGranting(true);
            consent
              .grant()
              .then(() => refresh())
              .catch((err: unknown) => Alert.alert('동의 저장 실패', friendlyErrorText(err)))
              .finally(() => setGranting(false));
          },
        },
      ],
    );
  }, [consent, refresh]);

  const tokenQuery = useQuery({
    queryKey: ['mobile', 'vworld-token'],
    queryFn: () =>
      apiClient.request('/mobile/vworld/token', { method: 'GET', schema: VWorldTokenSchema }),
    retry: false,
    staleTime: 60_000,
  });

  // 키 미발급(미설정/오프라인) → 지도를 띄울 수 없으므로 안내 화면.
  if (tokenQuery.isError || (tokenQuery.isSuccess && !tokenQuery.data.api_key)) {
    return (
      <Screen>
        <View className="gap-5 py-2">
          <Heading>지도</Heading>
          <Card className="gap-2">
            <Subheading>지도를 불러올 수 없습니다</Subheading>
            <Muted>
              VWorld 지도 키를 발급받지 못했습니다. API 서버 연결과 키
              설정(`PINVI_VWORLD_API_KEY`)을 확인한 뒤 다시 시도하세요.
            </Muted>
            <Button label="다시 시도" variant="secondary" onPress={() => tokenQuery.refetch()} />
          </Card>
        </View>
      </Screen>
    );
  }

  const markers =
    location != null
      ? [
          {
            id: 'me',
            coordinate: [location.coord.lon, location.coord.lat] as [number, number],
            color: '#1E88E5',
            selected: true,
            ariaLabel: '내 위치',
          },
        ]
      : [];

  return (
    <SafeAreaView className="flex-1 bg-canvas" edges={['bottom']}>
      <View className="flex-1">
        {tokenQuery.isSuccess && autoCenter.resolved ? (
          <VWorldMapView
            ref={mapRef}
            apiKey={tokenQuery.data.api_key}
            mapType="base"
            initialCenter={autoCenter.center}
            initialZoom={autoCenter.zoom}
            markers={markers}
            style={{ flex: 1 }}
          />
        ) : (
          <View className="flex-1 items-center justify-center">
            <Muted>{tokenQuery.isSuccess ? '지도를 준비하는 중…' : '지도 키 발급 중…'}</Muted>
          </View>
        )}

        {/* 오버레이 컨트롤 */}
        <View className="absolute bottom-5 left-5 right-5 gap-2">
          {error ? (
            <Card className="gap-1">
              <Body className="text-error-text">
                {error.code === 'PERMISSION_DENIED'
                  ? '위치 권한이 거부되었습니다. 설정에서 허용해 주세요.'
                  : '위치를 가져오지 못했습니다.'}
              </Body>
            </Card>
          ) : null}
          {autoCenter.outOfServiceArea ? (
            <Card className="gap-1">
              <Muted>현재 위치가 국내 서비스 범위 밖이라 기본 위치(서울)를 표시합니다.</Muted>
            </Card>
          ) : null}
          {consent.status === 'missing' ? (
            <Card className="gap-1">
              <Muted>
                위치 동의가 없어 내 위치 기능이 꺼져 있습니다. 버튼을 눌러 동의할 수 있습니다.
              </Muted>
            </Card>
          ) : null}
          {/* 지도가 아직 mount되지 않았으면 `flyTo`가 무음 no-op이 된다 — 그동안은 눌리지 않게 한다. */}
          <Button
            label="현재 위치로"
            onPress={onMyLocation}
            loading={loading || granting || consent.status === 'loading' || !autoCenter.resolved}
          />
        </View>
      </View>
    </SafeAreaView>
  );
}
