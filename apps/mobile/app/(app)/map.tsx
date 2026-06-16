import { View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { useUserLocation } from '@pinvi/hooks';
import { apiClient } from '../../lib/api';
import { expoLocationAdapter } from '../../lib/location';
import { Body, Button, Card, Heading, Muted, Screen, Subheading } from '../../components/ui';

/**
 * 지도 화면 — 현재는 placeholder. 실제 VWorld 지도는 `maplibre-vworld-react`(RN)
 * 선결 항목(키 주입 #3 / git-install #2 / 프리미티브 #5·#6 / 카메라 #8)이 해소되어야
 * 탑재한다(expo-implementation-plan §4). 여기서는 (a) server-issued VWorld 키 경로와
 * (b) `useUserLocation` 어댑터가 동작함을 확인한다.
 */
const VWorldTokenSchema = z.object({
  api_key: z.string(),
  key_source: z.literal('server-issued'),
  ttl_seconds: z.number(),
});

export default function MapScreen() {
  const { location, error, loading, refresh } = useUserLocation(expoLocationAdapter, {
    high_accuracy: false,
  });

  const tokenQuery = useQuery({
    queryKey: ['mobile', 'vworld-token'],
    queryFn: () =>
      apiClient.request('/mobile/vworld/token', { method: 'GET', schema: VWorldTokenSchema }),
    retry: false,
    staleTime: 60_000,
  });

  return (
    <Screen>
      <View className="gap-5 py-2">
        <View className="gap-1">
          <Heading>지도</Heading>
          <Body>주변 장소 탐색은 준비 중입니다.</Body>
        </View>

        <Card className="gap-2">
          <Subheading>지도 라이브러리 준비 상태</Subheading>
          <Muted>
            VWorld + MapLibre 지도는 `maplibre-vworld-react` 선결 항목(키 주입·git 설치·카메라
            제어) 해소 후 탑재됩니다(ADR-043, 이슈 #2/#3/#8).
          </Muted>
        </Card>

        <Card className="gap-2">
          <Subheading>지도 키(server-issued)</Subheading>
          {tokenQuery.isLoading ? (
            <Muted>키 발급 확인 중…</Muted>
          ) : tokenQuery.isError ? (
            <Muted>키 발급 확인 실패 — API 서버 연결 후 다시 시도하세요.</Muted>
          ) : (
            <Body>
              발급 OK · 만료 {tokenQuery.data?.ttl_seconds}s · 키는 앱에 번들하지 않음
            </Body>
          )}
        </Card>

        <Card className="gap-3">
          <Subheading>내 위치</Subheading>
          {location ? (
            <Body>
              위도 {location.coord.lat.toFixed(5)}, 경도 {location.coord.lon.toFixed(5)} (±
              {Math.round(location.accuracy_m)}m)
            </Body>
          ) : error ? (
            <Muted className="text-error-text">
              {error.code === 'PERMISSION_DENIED'
                ? '위치 권한이 거부되었습니다. 설정에서 권한을 허용해 주세요.'
                : '위치를 가져오지 못했습니다.'}
            </Muted>
          ) : (
            <Muted>아직 위치를 가져오지 않았습니다.</Muted>
          )}
          <Button label="현재 위치 가져오기" variant="secondary" onPress={refresh} loading={loading} />
        </Card>
      </View>
    </Screen>
  );
}
