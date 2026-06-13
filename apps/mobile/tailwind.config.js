// 디자인 토큰은 웹과 동일하게 @pinvi/design-tokens의 Tailwind preset에서 가져온다
// (frontend.md §3.5). NativeWind preset과 함께 적용한다.
const pinviPreset = require('@pinvi/design-tokens/tailwind-preset');

/** @type {import('tailwindcss').Config} */
module.exports = {
  presets: [require('nativewind/preset'), pinviPreset],
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {},
  },
  plugins: [],
};
