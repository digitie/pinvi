import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';
import { AssertAllPlannedFilesRan } from './vitest.reporters';

// 순수 로직 단위 테스트(`*.test.ts`, node) + 컴포넌트 테스트(`*.test.tsx`, jsdom + RTL).
// Playwright e2e(`e2e/**`)는 제외(별도 러너).
//
// vitest 4는 rolldown-vite를 번들한다. JSX 변환은 oxc가 담당하며 esbuild 옵션은
// 무시된다(rolldown이 esbuild 대신 oxc를 씀). 따라서 esbuild 기반
// `@vitejs/plugin-react`는 필요 없고(오히려 esbuild JSX 옵션을 주입해 oxc와 충돌 →
// `.tsx` import-analysis parse 실패), oxc의 automatic JSX 런타임으로 직접 변환한다.
export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('.', import.meta.url)),
    },
  },
  oxc: {
    jsx: {
      runtime: 'automatic',
      importSource: 'react',
    },
  },
  test: {
    // globals: RTL 자동 cleanup(글로벌 afterEach 후킹)이 동작하려면 필요.
    globals: true,
    include: ['tests/**/*.test.{ts,tsx}'],
    exclude: ['e2e/**', 'node_modules/**', '.next/**'],
    // vitest v3에서 `environmentMatchGlobs`가 제거돼 jsdom 단일 환경으로 통일한다.
    // 순수 로직(.test.ts)도 jsdom에서 동일하게 통과하고(DOM 미사용), RTL(.test.tsx)에 필요하다.
    environment: 'jsdom',
    setupFiles: ['./tests/vitest.setup.ts'],
    // 기본 리포터 + 조용한 파일 누락 가드(T-321). 가드는 계획된 spec과 결과가 나온 module을
    // 대조하므로 부분 실행(`vitest run <file>`, `-t`)에서도 오탐하지 않는다.
    //
    // `reporters`를 명시하면 vitest의 기본 주입 블록이 통째로 건너뛰어진다 — 그 블록은
    // `default`뿐 아니라 CI에서 `github-actions`(주석 annotation)까지 넣으므로 여기서 직접 되살린다.
    reporters: [
      'default',
      ...(process.env.GITHUB_ACTIONS === 'true' ? (['github-actions'] as const) : []),
      new AssertAllPlannedFilesRan(),
    ],
  },
});
