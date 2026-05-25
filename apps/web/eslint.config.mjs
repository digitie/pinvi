// Next.js + TypeScript ESLint config.
// `next lint`가 본 파일을 자동 선택.

import { FlatCompat } from '@eslint/eslintrc';

const compat = new FlatCompat({
  baseDirectory: import.meta.url,
});

const config = [
  ...compat.config({
    extends: ['next/core-web-vitals', 'next/typescript'],
    rules: {
      'react/no-unescaped-entities': 'off',
      // TripMate `(lng, lat)` 좌표 순서 일관 — react-kakao 호환 잔존 코드 방지
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['*react-kakao-maps-sdk*'],
              message:
                'ADR-015 — Kakao Maps SDK 폐기. maplibre-vworld 사용 (`docs/integrations/maplibre-vworld.md`).',
            },
          ],
        },
      ],
    },
  }),
];

export default config;
