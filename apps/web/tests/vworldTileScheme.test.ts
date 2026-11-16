import { describe, expect, it } from 'vitest';
// vworld-map-web는 exports map이 없어 dist 내부 모듈을 직접 부를 수 있다 — 타일 URL 해석은 maplibre 의존이 없는
// 순수 함수다.
import { parseVWorldTileRequest } from 'vworld-map-web/dist/vworldTileRequest.js';

// 2026-11-16 PC(Firefox·Safari) 바탕지도 누락: vworld-map-web 1.0.3 handler는 `URL.protocol` setter로
// vworld:→https: 전환을 시도했고, WHATWG URL은 그 전환을 무시해 `vworld://`를 그대로 fetch했다. 1.0.4(upstream
// maplibre-vworld-react #33)가 스킴을 문자열로 바꾼다 — vendor한 판이 그 수정을 담고 있는지 지킨다.
describe('vendored vworld-map-web 타일 스킴', () => {
  it('setter로는 바뀌지 않는다(jsdom·Firefox·Safari 공통 표준 동작)', () => {
    const url = new URL('vworld://api.vworld.kr/req/wmts/1.0.0/K/Base/8/100/218.png');
    url.protocol = 'https:';
    expect(url.protocol).toBe('vworld:');
  });

  it('vendored 판은 vworld:// 타일을 https로 바꾸고 fallback 전용 파라미터를 뺀다', () => {
    expect(
      parseVWorldTileRequest(
        'vworld://api.vworld.kr/req/wmts/1.0.0/K/Base/8/100/218.png?label=VWorld+tile&mapId=m1',
      ),
    ).toEqual({
      url: 'https://api.vworld.kr/req/wmts/1.0.0/K/Base/8/100/218.png',
      fallbackUrl: null,
      label: 'VWorld tile',
      mapId: 'm1',
    });
  });
});
