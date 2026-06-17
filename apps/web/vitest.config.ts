import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// 순수 로직 단위 테스트(`*.test.ts`, node) + 컴포넌트 테스트(`*.test.tsx`, jsdom + RTL).
// Playwright e2e(`e2e/**`)는 제외(별도 러너).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('.', import.meta.url)),
    },
  },
  test: {
    // globals: RTL 자동 cleanup(글로벌 afterEach 후킹)이 동작하려면 필요.
    globals: true,
    include: ['tests/**/*.test.{ts,tsx}'],
    exclude: ['e2e/**', 'node_modules/**', '.next/**'],
    environment: 'node',
    // .test.tsx만 jsdom(RTL). 기존 순수 로직(.test.ts)은 node 유지.
    environmentMatchGlobs: [['tests/**/*.test.tsx', 'jsdom']],
    setupFiles: ['./tests/vitest.setup.ts'],
  },
});
