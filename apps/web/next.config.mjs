const DEFAULT_GRAFANA_URL = 'http://localhost:3002';

function grafanaOrigin() {
  try {
    return new URL(process.env.NEXT_PUBLIC_GRAFANA_URL ?? DEFAULT_GRAFANA_URL).origin;
  } catch {
    return DEFAULT_GRAFANA_URL;
  }
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: '/admin/grafana',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: `frame-src 'self' ${grafanaOrigin()}; frame-ancestors 'self';`,
          },
        ],
      },
    ];
  },
  // monorepo workspace 패키지 transpile
  transpilePackages: [
    '@tripmate/schemas',
    '@tripmate/api-client',
    '@tripmate/state',
    '@tripmate/design-tokens',
    '@tripmate/hooks',
    '@tripmate/i18n',
    'maplibre-vworld',
  ],
};

export default nextConfig;
