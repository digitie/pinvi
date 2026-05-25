/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // monorepo workspace 패키지 transpile
  transpilePackages: [
    '@tripmate/schemas',
    '@tripmate/api-client',
    '@tripmate/state',
    '@tripmate/design-tokens',
    '@tripmate/hooks',
    '@tripmate/i18n',
  ],
};

export default nextConfig;
