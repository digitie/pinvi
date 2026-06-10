import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

// 순수 로직 단위 테스트 전용. Playwright e2e(`e2e/**`)는 제외(별도 러너).
export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('.', import.meta.url)),
    },
  },
  test: {
    include: ['tests/**/*.test.ts'],
    exclude: ['e2e/**', 'node_modules/**', '.next/**'],
    environment: 'node',
  },
});
