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
  // Playwright fixture 파일의 `use(page)`는 React hook이 아니다 — 이름이 `use*`로 시작한다는
  // 이유만으로 react-hooks/rules-of-hooks가 오탐한다(ESLint 10 + eslint-plugin-react-hooks 7).
  files: ['e2e/**/*.ts'],
  rules: {
    'react-hooks/rules-of-hooks': 'off',
  },
}];

export default config;
