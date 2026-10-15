import { describe, expect, it } from 'vitest';

import {
  weatherUpstreamFromEnv,
  weatherUpstreamRequestOptions,
} from '../e2e/weather-proxy-upstream';

// T-375(ADR-074): live-mutating e2e weather 프록시의 upstream 호스트가 `127.0.0.1` 리터럴이라
// weather가 odroid로 옮긴 뒤 n150에서 ECONNREFUSED가 됐다. 호스트·포트를 env에서 받는다.
describe('weather proxy upstream', () => {
  it('env가 없으면 개발 기본값 127.0.0.1:14101을 쓴다', () => {
    expect(weatherUpstreamFromEnv({})).toEqual({ host: '127.0.0.1', port: 14101 });
  });

  it('PINVI_LIVE_WEATHER_UPSTREAM_HOST를 주면 그 호스트로 포워딩한다', () => {
    const upstream = weatherUpstreamFromEnv({
      PINVI_LIVE_WEATHER_UPSTREAM_HOST: '192.168.1.13',
      PINVI_LIVE_WEATHER_UPSTREAM_PORT: '12201',
    });
    const options = weatherUpstreamRequestOptions(upstream, {
      method: 'GET',
      url: '/v1/weather/markers?location_id=a',
      headers: { host: '127.0.0.1:13702', accept: 'application/json' },
    });
    expect(options.hostname).toBe('192.168.1.13');
    expect(options.port).toBe(12201);
    expect(options.method).toBe('GET');
    expect(options.path).toBe('/v1/weather/markers?location_id=a');
    expect(options.headers).toEqual({ host: '192.168.1.13:12201', accept: 'application/json' });
  });

  it('빈 문자열은 미설정으로 본다', () => {
    expect(
      weatherUpstreamFromEnv({
        PINVI_LIVE_WEATHER_UPSTREAM_HOST: ' ',
        PINVI_LIVE_WEATHER_UPSTREAM_PORT: '',
      }),
    ).toEqual({ host: '127.0.0.1', port: 14101 });
  });

  it('포트가 정수가 아니면 거부한다', () => {
    expect(() => weatherUpstreamFromEnv({ PINVI_LIVE_WEATHER_UPSTREAM_PORT: 'abc' })).toThrow(
      /PINVI_LIVE_WEATHER_UPSTREAM_PORT/,
    );
  });
});
