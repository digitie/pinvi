import { useCallback, useRef, useState } from 'react';
import { Alert, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { VWorldMapView, type VWorldMapHandle } from 'vworld-map-rn';
import { useUserLocation } from '@pinvi/hooks';
import { friendlyErrorText } from '@pinvi/domain';
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
const SEOUL: [number, number] = [126.978, 37.5665];

const VWorldTokenSchema = z.object({
  api_key: z.string(),
  key_source: z.literal('server-issued'),
  ttl_seconds: z.number(),
});

export default function MapScreen() {
  const mapRef = useRef<VWorldMapHandle>(null);
  const { location, error, loading, refresh } = useUserLocation(expoLocationAdapter, {
    high_accuracy: false,
    on_success: (loc) => {
      mapRef.current?.flyTo({ center: [loc.coord.lon, loc.coord.lat], zoom: 15 });
    },
  });
  // 위치 동의 gate(웹 handleMyLocation 대응) — 동의가 없거나 조회 실패면 OS 권한 요청 전에
  // 동의 안내를 먼저 띄운다. 설정에서 철회하면 같은 query가 갱신돼 다시 잠긴다.
  const consent = useLocationConsent();
  const [granting, setGranting] = useState(false);

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

  const center: [number, number] = location ? [location.coord.lon, location.coord.lat] : SEOUL;

  return (
    <SafeAreaView className="flex-1 bg-canvas" edges={['bottom']}>
      <View className="flex-1">
        {tokenQuery.isSuccess ? (
          <VWorldMapView
            ref={mapRef}
            apiKey={tokenQuery.data.api_key}
            mapType="base"
            initialCenter={center}
            initialZoom={location ? 15 : 12}
            markers={markers}
            style={{ flex: 1 }}
          />
        ) : (
          <View className="flex-1 items-center justify-center">
            <Muted>지도 키 발급 중…</Muted>
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
          {consent.status === 'missing' ? (
            <Card className="gap-1">
              <Muted>
                위치 동의가 없어 내 위치 기능이 꺼져 있습니다. 버튼을 눌러 동의할 수 있습니다.
              </Muted>
            </Card>
          ) : null}
          <Button
            label="현재 위치로"
            onPress={onMyLocation}
            loading={loading || granting || consent.status === 'loading'}
          />
        </View>
      </View>
    </SafeAreaView>
  );
}
