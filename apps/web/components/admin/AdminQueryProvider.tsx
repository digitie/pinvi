'use client';

import { type ReactNode, useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

/**
 * Admin 전용 TanStack Query provider. 모바일 `_layout.tsx`와 같은 기본값을 쓴다.
 * root layout을 침범하지 않도록 admin 레이아웃에서만 마운트한다(다른 route group은 raw fetch 유지).
 */
export function AdminQueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: false },
        },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
