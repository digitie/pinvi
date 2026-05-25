/**
 * 타이포 — DESIGN.md "Typography" 톤 + Pretendard (한글 친화) fallback.
 * 자세히는 `docs/architecture/frontend.md` §3.3.
 */

export const fonts = {
  sans: 'Pretendard, "Apple SD Gothic Neo", system-ui, -apple-system, Roboto, sans-serif',
  display: 'Pretendard, "Apple SD Gothic Neo", system-ui, sans-serif',
  mono: '"JetBrains Mono", ui-monospace, "SF Mono", monospace',
} as const;

export const fontSize = {
  xs: 12,
  sm: 14,
  base: 16,
  lg: 18,
  xl: 20,
  '2xl': 24,
  '3xl': 28, // hero h1 — DESIGN.md "28px / 700"
  '4xl': 32,
  '5xl': 40,
} as const;

export const fontWeight = {
  normal: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
} as const;

export const lineHeight = {
  tight: 1.2,
  snug: 1.35,
  normal: 1.5,
  relaxed: 1.7,
} as const;
