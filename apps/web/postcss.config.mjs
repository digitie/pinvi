/** @type {import('postcss-load-config').Config} */
const config = {
  plugins: {
    // Tailwind v4 — 이 플러그인이 vendor prefix(lightningcss)까지 처리하므로 autoprefixer를 따로 두지 않는다.
    '@tailwindcss/postcss': {},
  },
};

export default config;
