import type { IncomingHttpHeaders, RequestOptions } from 'node:http';

// live-mutating e2e weather 프록시의 upstream(실제 `kor-travel-weather`) 주소 — T-375, ADR-074.
// 호스트와 포트를 둘 다 env에서 받는다. 기본값 `127.0.0.1:14101`은 weather standalone
// compose(개발) 기준이다. 운영 weather는 n150이 아니라 odroid라(2026-10-15 `192.168.1.13:12201`,
// Manager compose가 정본) n150에서 돌릴 때는 runbook(`docs/runbooks/live-mutating-e2e.md`)대로
// `PINVI_LIVE_WEATHER_UPSTREAM_HOST`·`PINVI_LIVE_WEATHER_UPSTREAM_PORT`를 준다. 값을 이 파일에
// 박지 않는다 — 호스트가 또 바뀌어도 코드 변경이 없게 한다.

export type WeatherUpstream = { host: string; port: number };

export function weatherUpstreamFromEnv(env: NodeJS.ProcessEnv): WeatherUpstream {
  const host = env.PINVI_LIVE_WEATHER_UPSTREAM_HOST?.trim() || '127.0.0.1';
  const rawPort = env.PINVI_LIVE_WEATHER_UPSTREAM_PORT?.trim() || '14101';
  const port = Number(rawPort);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error(`PINVI_LIVE_WEATHER_UPSTREAM_PORT가 올바른 포트가 아닙니다: ${rawPort}`);
  }
  return { host, port };
}

/** 프록시가 upstream으로 보내는 요청 옵션 — `host` 헤더도 upstream 주소로 바꾼다. */
export function weatherUpstreamRequestOptions(
  upstream: WeatherUpstream,
  request: { method?: string; url?: string; headers: IncomingHttpHeaders },
): RequestOptions {
  return {
    hostname: upstream.host,
    port: upstream.port,
    method: request.method,
    path: request.url,
    headers: { ...request.headers, host: `${upstream.host}:${upstream.port}` },
  };
}
