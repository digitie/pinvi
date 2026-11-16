import { readFileSync } from 'node:fs';
import path from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { vworldTileProtocol, vworldTileRequest } from '@/lib/vworldTileProtocol';

// PC(Firefox·Safari) 바탕지도 누락(2026-11-16): vworld-map-web 1.0.3 handler가 `vworld://`를 https로
// 바꾸지 못해 타일 fetch가 전부 실패했다. PinVi가 표준을 지키는 handler로 덮는다.

const TILE =
  'vworld://api.vworld.kr/req/wmts/1.0.0/K/Base/8/100/218.png?label=VWorld+tile&mapId=m1';
const params = { url: TILE, type: 'image' } as Parameters<typeof vworldTileProtocol>[0];

afterEach(() => vi.unstubAllGlobals());

describe('vworld 타일 protocol', () => {
  it('표준 URL은 protocol setter로 vworld→https 전환을 무시한다(라이브러리 handler가 깨진 이유)', () => {
    const u = new URL(TILE);
    u.protocol = 'https:';
    expect(u.protocol).toBe('vworld:');
  });

  it('스킴을 문자열로 바꾸고 fallback 전용 파라미터를 뺀다', () => {
    expect(vworldTileRequest(TILE)).toEqual({
      httpsUrl: 'https://api.vworld.kr/req/wmts/1.0.0/K/Base/8/100/218.png',
      fallbackUrl: null,
      label: 'VWorld tile',
      mapId: 'm1',
    });
  });

  it('https 타일을 받아 그대로 돌려준다', async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(new Uint8Array([1, 2, 3]), { headers: { 'content-type': 'image/png' } }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const res = await vworldTileProtocol(params, new AbortController());
    expect((fetchMock.mock.calls[0] as unknown[])[0]).toBe(
      'https://api.vworld.kr/req/wmts/1.0.0/K/Base/8/100/218.png',
    );
    expect((res.data as ArrayBuffer).byteLength).toBe(3);
  });

  it('커버리지 밖 XML은 오류 이벤트 없이 fallback', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response('<ExceptionReport>서비스 제공영역이 아닙니다</ExceptionReport>', {
            headers: { 'content-type': 'text/xml' },
          }),
      ),
    );
    const onError = vi.fn();
    window.addEventListener('vworld-tile-error', onError);
    const res = await vworldTileProtocol(params, new AbortController());
    window.removeEventListener('vworld-tile-error', onError);
    expect((res.data as ArrayBuffer).byteLength).toBeGreaterThan(0);
    expect(onError).not.toHaveBeenCalled();
  });

  it('실패는 mapId를 실은 이벤트 + fallback, abort는 그대로 던진다', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('network');
      }),
    );
    const onError = vi.fn();
    window.addEventListener('vworld-tile-error', onError);
    await vworldTileProtocol(params, new AbortController());
    window.removeEventListener('vworld-tile-error', onError);
    expect((onError.mock.calls[0]![0] as CustomEvent).detail.mapId).toBe('m1');
    const aborted = new AbortController();
    aborted.abort();
    await expect(vworldTileProtocol(params, aborted)).rejects.toThrow();
  });

  it('지도 엔진을 불러올 때 라이브러리 등록 뒤 이 handler로 덮는다', () => {
    const source = readFileSync(
      path.resolve(__dirname, '../components/map/vworldPrimitives.tsx'),
      'utf8',
    );
    const register = source.indexOf('module.registerVWorldProtocol()');
    const override = source.indexOf("maplibre.addProtocol('vworld', vworldTileProtocol)");
    expect(register).toBeGreaterThan(0);
    expect(override).toBeGreaterThan(register);
  });
});
