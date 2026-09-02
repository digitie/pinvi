import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

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

const config = [...nextCoreWebVitals, ...nextTypescript, {
  rules: {
    'react/no-unescaped-entities': 'off',
    // Pinvi `(lng, lat)` 좌표 순서 일관 — react-kakao 호환 잔존 코드 방지
    'no-restricted-imports': [
      'error',
      {
        patterns: [
          {
            group: ['*react-kakao-maps-sdk*'],
            message:
              'ADR-015/046 — Kakao Maps SDK 폐기. vworld-map-web 사용 (`docs/integrations/maplibre-vworld.md`).',
          },
        ],
      },
    ],
  }
}, {
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
}, {
  // ── 모달 스택 경계: admin 표면 (T-356) ──
  //
  // admin은 base-ui 기반 `components/admin/ui/{dialog,alert-dialog,popover,tooltip}`을 쓰고,
  // 사용자 표면은 `lib/useModalDialog` + `components/ui/Dialog`를 쓴다. **한 화면에서 섞으면
  // focus trap과 `inert` 스냅샷이 서로를 덮는다** — 두 구현이 각자 body 자식에 inert를 걸고
  // 각자 복원 스냅샷을 들고 있어서, 나중에 닫히는 쪽이 상대의 복원을 무효화한다.
  //
  // DESIGN.md의 "모달 계약" 절이 이 분리를 명문화하지만 문서만으로는 약하다 — 이 저장소는
  // T-356에서 "로컬 4개 게이트를 전부 통과한 회귀"를 두 번 겪었다. 규칙을 실행 가능한
  // 가드로 옮긴다.
  files: ['app/(admin)/**/*.tsx', 'components/admin/**/*.tsx'],
  rules: {
    'no-restricted-imports': [
      'error',
      {
        patterns: [
          {
            group: [
              '**/components/ui/Dialog',
              '**/components/ui/ConfirmDialog',
              '@/components/ui/Dialog',
              '@/components/ui/ConfirmDialog',
            ],
            message:
              'T-356 — admin 모달은 `@/components/admin/ui/dialog`(또는 `alert-dialog`)를 쓴다. ' +
              '사용자 표면 Dialog는 `lib/useModalDialog` 기반이라 base-ui와 focus trap·inert ' +
              '스냅샷이 충돌한다(DESIGN.md 모달 계약).',
          },
          {
            group: ['**/lib/useModalDialog', '@/lib/useModalDialog'],
            message:
              'T-356 — admin은 base-ui가 focus trap을 소유한다. `useModalDialog`를 함께 쓰면 ' +
              '트랩이 두 벌이 된다. `isRestorableFocusTarget` 같은 순수 헬퍼가 필요하면 ' +
              '그 심볼만 직접 import하지 말고 admin 쪽에 복제하거나 공용 유틸로 분리하라.',
          },
        ],
      },
    ],
  },
}, {
  // ── 모달 스택 경계: 사용자 표면 (T-356, 반대 방향) ──
  //
  // 사용자 표면이 admin 컴포넌트나 base-ui를 끌어오면 같은 충돌이 반대로 일어나고, admin 전용
  // 번들(cva/clsx/tailwind-merge/base-ui)이 사용자 표면 코드 스플릿 경계로 새어 들어간다.
  files: ['app/**/*.tsx', 'components/**/*.tsx'],
  ignores: ['app/(admin)/**', 'components/admin/**'],
  rules: {
    'no-restricted-imports': [
      'error',
      {
        patterns: [
          {
            group: ['*react-kakao-maps-sdk*'],
            message:
              'ADR-015/046 — Kakao Maps SDK 폐기. vworld-map-web 사용 (`docs/integrations/maplibre-vworld.md`).',
          },
          {
            group: ['**/components/admin/**', '@/components/admin/**'],
            message:
              'T-356 — admin 컴포넌트는 admin 표면 전용이다. 사용자 표면은 `components/ui/*`와 ' +
              '`lib/useModalDialog`를 쓴다(DESIGN.md Hallmark 잠금 + 모달 계약).',
          },
          {
            group: ['@base-ui/react', '@base-ui/react/**'],
            message:
              'T-356 — base-ui는 admin 오버레이 프리미티브 전용이다. 사용자 표면 모달은 ' +
              '`lib/useModalDialog`가 소유한다.',
          },
        ],
      },
    ],
  },
}, {
  // Playwright fixture 파일의 `use(page)`는 React hook이 아니다 — 이름이 `use*`로 시작한다는
  // 이유만으로 react-hooks/rules-of-hooks가 오탐한다(ESLint 10 + eslint-plugin-react-hooks 7).
  files: ['e2e/**/*.ts'],
  rules: {
    'react-hooks/rules-of-hooks': 'off',
  },
}];

export default config;
