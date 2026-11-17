import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MapFallback } from '@/components/map/vworldPrimitives';
import { isWebGLAvailable, mapFallbackCopy } from '@/lib/mapFallback';

// 2026-11-17 live e2e: headless Firefox(WebGL 없음)에서 엔진 초기화가 실패했는데 fallback이
// `NEXT_PUBLIC_VWORLD_API_KEY`를 보여 키 문제처럼 읽혔다. 사유별 문구를 고정한다.
vi.mock('next/dynamic', () => ({ default: () => () => null }));

function stubGetContext(result: unknown) {
  return vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation((() => result) as never);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('mapFallbackCopy', () => {
  it('키가 비었을 때만 환경변수 이름을 보인다', () => {
    expect(mapFallbackCopy({ reason: 'missing-api-key' }, true)).toEqual({
      message: 'VWorld API 키가 설정되지 않았습니다.',
      detail: 'NEXT_PUBLIC_VWORLD_API_KEY',
    });
  });

  it('WebGL이 없으면 WebGL을 원인으로 알리고 키 이름은 보이지 않는다', () => {
    const copy = mapFallbackCopy({ reason: 'map-init-error', error: new Error('x') }, false);
    expect(copy.message).toContain('WebGL');
    expect(`${copy.message} ${copy.detail}`).not.toContain('NEXT_PUBLIC_VWORLD_API_KEY');
  });

  it('WebGL이 있는데 엔진이 실패하면 일반 초기화 실패로 알리고 키 이름은 보이지 않는다', () => {
    const copy = mapFallbackCopy({ reason: 'map-init-error', error: new Error('x') }, true);
    expect(copy.message).toBe('지도 엔진을 초기화할 수 없습니다.');
    expect(copy.detail).not.toContain('NEXT_PUBLIC_VWORLD_API_KEY');
  });
});

describe('isWebGLAvailable', () => {
  it('webgl2 컨텍스트가 있으면 true', () => {
    stubGetContext({});
    expect(isWebGLAvailable()).toBe(true);
  });

  it('webgl2·webgl 모두 null이면 false', () => {
    const spy = stubGetContext(null);
    expect(isWebGLAvailable()).toBe(false);
    expect(spy.mock.calls.map(([kind]) => kind)).toEqual(['webgl2', 'webgl']);
  });

  it('getContext가 던지면 false', () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(isWebGLAvailable()).toBe(false);
  });
});

describe('MapFallback', () => {
  it('엔진 초기화 실패 + WebGL 없음 → WebGL 안내', () => {
    stubGetContext(null);
    render(<MapFallback info={{ reason: 'map-init-error', error: new Error('no webgl') }} />);
    const box = screen.getByTestId('vworld-map-fallback');
    expect(box).toHaveAttribute('data-fallback-reason', 'webgl-unavailable');
    expect(box).toHaveTextContent('이 브라우저에서 WebGL을 사용할 수 없어 지도를 표시할 수 없습니다.');
    expect(box).not.toHaveTextContent('NEXT_PUBLIC_VWORLD_API_KEY');
  });

  it('엔진 초기화 실패 + WebGL 있음 → 일반 초기화 실패', () => {
    stubGetContext({});
    render(<MapFallback info={{ reason: 'map-init-error', error: new Error('boom') }} />);
    const box = screen.getByTestId('vworld-map-fallback');
    expect(box).toHaveAttribute('data-fallback-reason', 'map-init-error');
    expect(box).toHaveTextContent('지도 엔진을 초기화할 수 없습니다.');
    expect(box).not.toHaveTextContent('NEXT_PUBLIC_VWORLD_API_KEY');
  });

  it('키 없음 → 키 안내(WebGL은 확인하지 않는다)', () => {
    const spy = stubGetContext(null);
    render(<MapFallback info={{ reason: 'missing-api-key' }} />);
    const box = screen.getByTestId('vworld-map-fallback');
    expect(box).toHaveAttribute('data-fallback-reason', 'missing-api-key');
    expect(box).toHaveTextContent('VWorld API 키가 설정되지 않았습니다.');
    expect(box).toHaveTextContent('NEXT_PUBLIC_VWORLD_API_KEY');
    expect(spy).not.toHaveBeenCalled();
  });
});
