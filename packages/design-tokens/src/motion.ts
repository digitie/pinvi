/**
 * UI motion tokens.
 *
 * StyleSeed의 named motion 개념을 Pinvi의 절제된 제품 UI에 맞게 숫자 토큰으로
 * 고정한다. 커스텀 motion은 `prefers-reduced-motion` 전역 규칙을 따라야 한다.
 */

export const motion = {
  duration: {
    fast: '100ms',
    normal: '200ms',
    moderate: '300ms',
  },
  easing: {
    default: 'cubic-bezier(0.2, 0, 0, 1)',
    pinvi: 'cubic-bezier(0.2, 0, 0, 1)',
    spring: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
  },
} as const;
