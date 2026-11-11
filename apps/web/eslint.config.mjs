import nextPlugin from '@next/eslint-plugin-next';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import react from '@eslint-react/eslint-plugin';
import jsxA11y from 'eslint-plugin-jsx-a11y-x';
import importPlugin from 'eslint-plugin-import-x';
import globals from 'globals';

// eslint-config-next의 React/import/a11y 플러그인은 peer가 ESLint9까지라 전이9를
// 설치한다. ESLint10 지원 public 플러그인으로 기존 Next·TS·Hooks·접근성 검사를 연결한다.
const eslint10Base = [
  {
    files: ['**/*.{js,jsx,mjs,cjs,ts,tsx}'],
    plugins: {
      '@next/next': nextPlugin,
      '@eslint-react': react,
      'react-hooks': reactHooks,
      'jsx-a11y': jsxA11y,
      import: importPlugin,
    },
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      ...nextPlugin.configs['core-web-vitals'].rules,
      ...reactHooks.configs.recommended.rules,
      'import/no-anonymous-default-export': 'warn',
      '@eslint-react/no-missing-component-display-name': 'error',
      '@eslint-react/no-missing-key': 'error',
      '@eslint-react/no-duplicate-key': 'error',
      '@eslint-react/jsx-no-comment-textnodes': 'error',
      '@eslint-react/jsx-no-children-prop': 'error',
      '@eslint-react/dom-no-dangerously-set-innerhtml-with-children': 'error',
      '@eslint-react/no-component-will-mount': 'error',
      '@eslint-react/no-component-will-receive-props': 'error',
      '@eslint-react/no-component-will-update': 'error',
      '@eslint-react/no-direct-mutation-state': 'error',
      '@eslint-react/dom-no-find-dom-node': 'error',
      '@eslint-react/dom-no-render': 'error',
      '@eslint-react/dom-no-hydrate': 'error',
      '@eslint-react/dom-no-render-return-value': 'error',
      'jsx-a11y/alt-text': ['warn', { elements: ['img'], img: ['Image'] }],
      'jsx-a11y/aria-props': 'warn',
      'jsx-a11y/aria-proptypes': 'warn',
      'jsx-a11y/aria-unsupported-elements': 'warn',
      'jsx-a11y/role-has-required-aria-props': 'warn',
      'jsx-a11y/role-supports-aria-props': 'warn',
    },
  },
  ...tseslint.configs.recommended.map((config) => ({ ...config, files: ['**/*.{ts,tsx}'] })),
  { ignores: ['.next/**', 'out/**', 'build/**', 'next-env.d.ts'] },
];

/**
 * Hallmark 잠금 시스템(DESIGN.md) 재발 방지 가드 — T-316/T-317.
 *
 * T-312~T-316이 토큰 우회·임의 z-index·12px 이하 텍스트·44px 미달 컨트롤을 코드모드로 걷어냈다.
 * 사람이 다음에 같은 클래스를 다시 써 넣는 것을 lint가 막는다(정본은 DESIGN.md, 여기는 집행부).
 * 대상은 문자열 리터럴 전체이므로 className뿐 아니라 헬퍼 상수에 넣어도 걸린다.
 */
const HALLMARK_CLASS_GUARDS = [
  {
    pattern: String.raw`\bbg-white\b|\btext-white\b|\bbg-black/`,
    message:
      'DESIGN.md 토큰을 쓰세요 — bg-canvas / text-on-primary|text-canvas / bg-scrim. (마커 팔레트 인라인 색 위 텍스트만 예외이며 그 경우 주석으로 사유를 남깁니다.)',
  },
  {
    pattern: String.raw`\bshadow-(sm|md|lg|xl|2xl)\b`,
    message:
      'DESIGN.md 그림자는 2티어뿐입니다 — shadow-card(hover 카드·드롭다운) / shadow-overlay(모달·시트).',
  },
  {
    pattern: String.raw`\bz-\[`,
    message: 'DESIGN.md named z-index를 쓰세요 — z-nav < z-panel < z-overlay < z-modal < z-toast.',
  },
  {
    pattern: String.raw`\btext-\[\d`,
    message: 'DESIGN.md 타이포 스케일을 쓰세요(임의 px 금지, 12px 이하 금지 — 뱃지 예외).',
  },
  {
    pattern: String.raw`(?:^|\s)h-(?:8|9|10)(?:\s|$)[^'"]*\b(?:rounded-sm|rounded-md|rounded-full)\b[^'"]*\b(?:px-|font-semibold)`,
    message:
      'DESIGN.md 터치 타깃 44px — 컨트롤은 min-h-11(아이콘 버튼은 size-11)을 쓰세요. 밀도가 필요한 admin 표면은 이 규칙 밖입니다.',
  },
];

/**
 * flat config는 같은 규칙을 뒤 블록이 정의하면 **옵션을 병합하지 않고 통째로 교체**한다.
 * 그래서 `no-restricted-imports`를 재정의하는 모든 블록이 이 공통 패턴을 직접 펴야 한다 —
 * 안 그러면 그 블록 대상 파일에서 kakao 가드가 조용히 사라진다(T-357 리뷰가 실제로 잡았다).
 */
const KAKAO_IMPORT_GUARD = {
  group: ['*react-kakao-maps-sdk*'],
  message:
    'ADR-015/046 — Kakao Maps SDK 폐기. vworld-map-web 사용 (`docs/integrations/maplibre-vworld.md`).',
};

/**
 * 공개 디자인/도메인 어댑터와 관리자 밀도 어댑터의 import 경계를 유지한다.
 * 양쪽 모두 common Radix를 쓰며 focus/scroll 엔진의 별도 구현은 허용하지 않는다.
 */
const MODAL_STACK_MODULES = [
  'components/ui/Dialog',
  'components/ui/ConfirmDialog',
  'components/map/FeatureDetailModal',
  'components/map/FeatureDetailModalController',
  'components/map/FeatureMapView',
  'components/map/FeatureRequestDialog',
  'components/map/LocationConsentDialog',
  'components/notice-plans/NoticePlanCopyDialog',
  'components/notice-plans/NoticePlanShelf',
  'components/trips/ConflictDialog',
  'components/trips/SharedTripView',
  'components/trips/TripDashboard',
  'components/trips/TripDayControls',
  'components/trips/TripDetail',
  'components/trips/TripEditDialog',
  'components/trips/TripManualPoiDialog',
  'components/trips/TripMapView',
];

const config = [
  ...eslint10Base,
  {
    rules: {
      // Pinvi `(lng, lat)` 좌표 순서 일관 — react-kakao 호환 잔존 코드 방지
      'no-restricted-imports': ['error', { patterns: [KAKAO_IMPORT_GUARD] }],
    },
  },
  {
    // 사용자 표면(공개·앱)만 — `(admin)`과 admin 컴포넌트는 밀도 규칙이 달라 제외한다.
    files: ['app/**/*.tsx', 'components/**/*.tsx'],
    ignores: ['app/(admin)/**', 'components/admin/**'],
    rules: {
      'no-restricted-syntax': [
        'error',
        // esquery 선택자 안의 `/`는 정규식 종료로 읽히므로 이스케이프한다.
        ...HALLMARK_CLASS_GUARDS.map(({ pattern, message }) => ({
          selector: `Literal[value=/${pattern.replace(/\//g, '\\/')}/]`,
          message,
        })),
        ...HALLMARK_CLASS_GUARDS.map(({ pattern, message }) => ({
          selector: `TemplateElement[value.raw=/${pattern.replace(/\//g, '\\/')}/]`,
          message,
        })),
      ],
    },
  },
  {
    // 관리자 표면은 공개 여행 도메인/디자인 어댑터를 가져오지 않는다.
    files: [
      'app/(admin)/**/*.{ts,tsx}',
      'components/admin/**/*.{ts,tsx}',
      // `lib/admin/**`도 admin 소유다 — 여기서 헬퍼를 만들면서 사용자 표면 모듈을 끌어오면
      // 그 헬퍼를 쓰는 admin 컴포넌트로 모달 스택이 전이된다.
      'lib/admin/**/*.{ts,tsx}',
    ],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            KAKAO_IMPORT_GUARD,
            {
              group: MODAL_STACK_MODULES.flatMap((mod) => [`**/${mod}`, `@/${mod}`]),
              message:
                '관리자는 common Radix를 연결한 관리자 디자인 어댑터를 사용하고 공개 여행 도메인 모달을 import하지 않습니다.',
            },
            {
              group: ['**/lib/useModalDialog', '@/lib/useModalDialog'],
              message:
                '제거한 자체 모달 엔진을 다시 사용하지 마세요. 공통 Radix 생명주기와 focusTarget 판별을 사용합니다.',
            },
          ],
        },
      ],
    },
  },
  {
    // 공개 표면은 common 직접 소비를 허용하고 관리자 전용 어댑터와 Base UI만 차단한다.
    files: ['app/**/*.{ts,tsx}', 'components/**/*.{ts,tsx}', 'lib/**/*.{ts,tsx}'],
    ignores: ['app/(admin)/**', 'components/admin/**', 'lib/admin/**'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            KAKAO_IMPORT_GUARD,
            {
              group: ['**/components/admin/**', '@/components/admin/**'],
              message:
                '공개 표면은 common Radix의 공개 디자인 어댑터를 사용하고 관리자 전용 UI를 import하지 않습니다.',
            },
            {
              group: ['@base-ui/react', '@base-ui/react/**'],
              message:
                'Base UI는 제거 대상입니다. 공개/관리자 모두 common의 Radix 프리미티브를 사용합니다.',
            },
          ],
        },
      ],
    },
  },
  {
    // Playwright fixture 파일의 `use(page)`는 React hook이 아니다 — 이름이 `use*`로 시작한다는
    // 이유만으로 react-hooks/rules-of-hooks가 오탐한다(ESLint 10 + eslint-plugin-react-hooks 7).
    files: ['e2e/**/*.ts', 'e2e-live/**/*.ts'],
    rules: {
      'react-hooks/rules-of-hooks': 'off',
    },
  },
];

config.push({
  files: ['e2e/**/*.e2e.ts'],
  rules: {
    'no-restricted-imports': [
      'error',
      {
        paths: [
          {
            name: '@playwright/test',
            importNames: ['test'],
            message: '#618 — mocked 검사는 ./fixtures의 격리 test를 사용하세요.',
          },
        ],
        patterns: [KAKAO_IMPORT_GUARD],
      },
    ],
    'no-restricted-syntax': [
      'error',
      {
        selector: 'CallExpression[callee.object.name="route"][callee.property.name="continue"]',
        message: '#618 — mock 미처리 요청은 route.fallback()으로 격리 guard에 넘기세요.',
      },
      {
        selector:
          'CallExpression[callee.object.name="browser"][callee.property.name=/^(newContext|newPage)$/]',
        message: '#618 — 추가 세션은 newMockContext fixture를 사용하세요.',
      },
    ],
  },
});

// worker와 Playwright trace/report의 번들 생성물은 소스 lint 대상이 아니다.
config.unshift({
  ignores: ['public/maplibre/**', 'test-results/**', 'playwright-report/**', 'blob-report/**'],
});

export default config;
