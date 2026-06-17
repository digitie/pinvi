/**
 * 8px base spacing + radii + shadow.
 * DESIGN.md "Shape / Shadows / Spacing" + StyleSeed shadow cap.
 */

export const spacing = {
  0: 0,
  1: 4,
  2: 8,
  3: 12,
  4: 16,
  5: 20,
  6: 24,
  8: 32,
  10: 40,
  12: 48,
  16: 64, // section gap
} as const;

export const radii = {
  sm: 8, // 버튼
  md: 14, // 카드
  lg: 20,
  xl: 32, // 카테고리 strip
  full: 9999, // pill / 원
} as const;

export const shadows = {
  card: '0 0 0 1px rgba(0,0,0,0.02), 0 2px 6px rgba(0,0,0,0.04), 0 4px 8px rgba(0,0,0,0.08)',
} as const;
