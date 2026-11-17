import { defineConfig } from 'vitest/config';

// 모바일 단위·컴포넌트 테스트(`tests/**/*.test.{ts,tsx}`).
//
// - 러너는 웹·공용 패키지와 같은 vitest(정책 고정 버전)다. jest-expo는 Babel·Flow 변환 체인을 따로
//   들여와야 하고 공통 의존성 정책에 없는 패키지를 늘린다.
// - `react-native` 본체는 Flow 소스라 vite(oxc)가 읽지 못한다. 이미 Expo Web이 쓰는 `react-native-web`으로
//   바꿔 jsdom에 그린다 — 정확히 `react-native`만 바꾼다(`react-native-*` 패키지는 그대로).
// - 네이티브 모듈(`vworld-map-rn`, expo-*)은 각 테스트가 `vi.mock`으로 대신한다. node_modules 안의
//   패키지는 vite alias를 거치지 않고 Node가 직접 읽으므로, 그런 패키지가 `react-native`를 부르면 mock해야 한다.
// - JSX는 웹 설정과 같이 oxc automatic 런타임으로 변환한다.
export default defineConfig({
  resolve: {
    alias: [{ find: /^react-native$/, replacement: 'react-native-web' }],
  },
  oxc: {
    jsx: {
      runtime: 'automatic',
      importSource: 'react',
    },
  },
  define: {
    __DEV__: 'true',
  },
  test: {
    include: ['tests/**/*.test.{ts,tsx}'],
    exclude: ['node_modules/**', 'dist/**', '.expo/**'],
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
  },
});
