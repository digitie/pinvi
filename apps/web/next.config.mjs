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
  webpack(config) {
    // vendored VWorld CJS는 require('maplibre-gl')를 사용한다. MapLibre 6은
    // root require export가 없으므로 공개 ESM subpath를 bundler에서 사용한다.
    config.resolve.alias['maplibre-gl$'] = 'maplibre-gl/dist/maplibre-gl.mjs';
    return config;
  },
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
