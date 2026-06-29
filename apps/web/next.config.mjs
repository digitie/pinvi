const DEFAULT_GRAFANA_URL = 'http://localhost:12205';

function envValue(name, fallback) {
  const value = process.env[name]?.trim();
  return value || fallback;
}

function grafanaOrigin() {
  try {
    return new URL(envValue('NEXT_PUBLIC_GRAFANA_URL', DEFAULT_GRAFANA_URL)).origin;
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
    '@pinvi/schemas',
    '@pinvi/api-client',
    '@pinvi/state',
    '@pinvi/design-tokens',
    '@pinvi/domain',
    '@pinvi/hooks',
    '@pinvi/i18n',
    'vworld-map-core',
    'vworld-map-web',
  ],
};

export default nextConfig;
