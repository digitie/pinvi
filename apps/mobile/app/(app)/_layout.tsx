import { Redirect, Stack } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../../lib/auth';
import { Loading } from '../../components/ui';

/**
 * 인증 필요 그룹 가드. 부팅 복구 중(loading)에는 스플래시, 비인증이면 `/login`으로
 * 리다이렉트한다. 웹은 미들웨어/서버에서 쿠키로 가드하지만(ADR-032), 모바일은
 * SecureStore 토큰 상태로 클라이언트 가드한다.
 */
export default function AppLayout() {
  const { status } = useAuth();

  if (status === 'loading') {
    return (
      <SafeAreaView className="flex-1 bg-canvas">
        <Loading />
      </SafeAreaView>
    );
  }
  if (status === 'unauthenticated') {
    return <Redirect href="/login" />;
  }

  return (
    <Stack
      screenOptions={{
        headerShown: true,
        headerTintColor: '#222222',
        headerStyle: { backgroundColor: '#ffffff' },
        headerTitleStyle: { color: '#222222' },
        contentStyle: { backgroundColor: '#ffffff' },
      }}
    >
      <Stack.Screen name="index" options={{ title: 'Pinvi' }} />
      <Stack.Screen name="map" options={{ title: '지도' }} />
      <Stack.Screen name="trips/index" options={{ title: '내 여행' }} />
      <Stack.Screen name="trips/[tripId]/index" options={{ title: '여행 상세' }} />
      <Stack.Screen name="trips/[tripId]/edit" options={{ title: '여행 편집' }} />
      <Stack.Screen name="notice-plans/index" options={{ title: '추천 여행' }} />
      <Stack.Screen name="settings/index" options={{ title: '설정' }} />
      <Stack.Screen name="settings/telegram" options={{ title: 'Telegram 알림' }} />
      <Stack.Screen name="settings/consents" options={{ title: '동의 관리' }} />
      <Stack.Screen name="settings/mcp-tokens" options={{ title: 'MCP 토큰' }} />
      <Stack.Screen name="profile" options={{ title: '프로필' }} />
    </Stack>
  );
}
