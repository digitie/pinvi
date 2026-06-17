/**
 * Tailwind preset — `apps/web/tailwind.config.ts`가 import.
 * 모바일 NativeWind (v2)도 동일 preset 사용.
 */

/** @type {import('tailwindcss').Config} */
module.exports = {
  theme: {
    extend: {
      colors: {
        // 브랜드
        primary: {
          DEFAULT: '#ff385c',
          active: '#e00b41',
          disabled: '#ffd1da',
        },
        luxe: '#460479',
        plus: '#92174d',
        // 표면
        canvas: '#ffffff',
        'surface-soft': '#f7f7f7',
        'surface-strong': '#f2f2f2',
        // 보더
        hairline: '#dddddd',
        'hairline-soft': '#ebebeb',
        'border-strong': '#c1c1c1',
        // 텍스트
        ink: '#222222',
        body: '#3f3f3f',
        muted: '#6a6a6a',
        'muted-soft': '#929292',
        'star-rating': '#222222',
        'on-primary': '#ffffff',
        // 시맨틱
        'error-text': '#c13515',
        'error-text-hover': '#b32505',
        'error-bg': '#fdecea',
        'success-text': '#1b873f',
        'success-bg': '#e6f4ea',
        'legal-link': '#428bff',
        scrim: '#000000',
        // 16색 마커
        marker: {
          'p-01': '#E53935',
          'p-02': '#FB8C00',
          'p-03': '#FDD835',
          'p-04': '#7CB342',
          'p-05': '#43A047',
          'p-06': '#00897B',
          'p-07': '#00ACC1',
          'p-08': '#1E88E5',
          'p-09': '#3949AB',
          'p-10': '#8E24AA',
          'p-11': '#D81B60',
          'p-12': '#6D4C41',
          'p-13': '#757575',
          'p-14': '#212121',
          'p-15': '#F4511E',
          'p-16': '#039BE5',
        },
      },
      fontFamily: {
        sans: [
          'Pretendard',
          '"Apple SD Gothic Neo"',
          'system-ui',
          '-apple-system',
          'Roboto',
          'sans-serif',
        ],
        mono: ['"JetBrains Mono"', 'ui-monospace', '"SF Mono"', 'monospace'],
      },
      borderRadius: {
        sm: '8px',
        md: '14px',
        lg: '20px',
        xl: '32px',
      },
      boxShadow: {
        card: '0 0 0 1px rgba(0,0,0,0.02), 0 2px 6px rgba(0,0,0,0.04), 0 4px 8px rgba(0,0,0,0.08)',
      },
      spacing: {
        section: '64px',
      },
      minHeight: {
        touch: '44px',
      },
      minWidth: {
        touch: '44px',
      },
      transitionDuration: {
        fast: '100ms',
        normal: '200ms',
        moderate: '300ms',
      },
      transitionTimingFunction: {
        pinvi: 'cubic-bezier(0.2, 0, 0, 1)',
        spring: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
      },
    },
  },
};
