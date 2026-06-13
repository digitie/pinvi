import { useState } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '../global.css';

// Expo Router 루트 레이아웃. TanStack Query는 @pinvi/api-client query key와
// 같은 클라이언트를 공유한다 (frontend.md §4.3 — 웹/모바일 공용 패턴).
export default function RootLayout() {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <StatusBar style="auto" />
      <Stack screenOptions={{ headerShown: true }} />
    </QueryClientProvider>
  );
}
