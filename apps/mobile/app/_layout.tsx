import { useState } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '../lib/auth';
import '../global.css';

/**
 * Expo Router 루트 레이아웃 — 프로바이더 스택(SafeArea → Query → Auth).
 * TanStack Query는 @pinvi/api-client query key와 같은 클라이언트를 공유한다
 * (frontend.md §4.3 — 웹/모바일 공용 패턴). 라우트 그룹: `(app)`(인증 필요),
 * `(auth)`(비인증), `shared`(익명 공유 뷰).
 */
export default function RootLayout() {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
      }),
  );

  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <StatusBar style="auto" />
          <Stack screenOptions={{ headerShown: false }} />
        </AuthProvider>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
