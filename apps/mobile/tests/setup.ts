import type { ReactNode } from 'react';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// globals를 켜지 않으므로 RTL 자동 cleanup이 걸리지 않는다 — 테스트마다 직접 비운다.
afterEach(() => {
  cleanup();
});

// node_modules 패키지는 alias를 거치지 않고 Node가 읽어 진짜 `react-native`(Flow 소스)를 부른다.
// 화면 껍데기(SafeAreaView)만 쓰므로 react-native-web View로 대신한다.
vi.mock('react-native-safe-area-context', async () => {
  const { View } = await import('react-native');
  return {
    SafeAreaView: View,
    SafeAreaProvider: ({ children }: { children?: ReactNode }) => children,
    useSafeAreaInsets: () => ({ top: 0, right: 0, bottom: 0, left: 0 }),
  };
});
