import { describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useAbortableLoad } from '@/lib/useAbortableLoad';

// 2026-11-02 prod 점검: 마커 선택을 바꿔도 직전 상세·날씨 요청이 취소되지 않아(날씨 ~31s)
// 브라우저 연결 슬롯을 붙잡았다. 선택이 바뀌면 직전 요청의 signal이 abort돼야 한다.
describe('useAbortableLoad', () => {
  it('키가 바뀌면 직전 요청을 취소하고, 취소된 결과는 버린다', async () => {
    const signals: Record<string, AbortSignal> = {};
    const resolvers: Record<string, (value: string) => void> = {};
    const load = vi.fn(
      (key: string, signal: AbortSignal) =>
        new Promise<string>((resolve) => {
          signals[key] = signal;
          resolvers[key] = resolve;
        }),
    );
    const onLoad = vi.fn();

    const { rerender, unmount } = renderHook(
      ({ id }: { id: string | null }) => useAbortableLoad(id, load, onLoad),
      { initialProps: { id: 'a' as string | null } },
    );
    expect(signals.a?.aborted).toBe(false);

    rerender({ id: 'b' });
    expect(signals.a?.aborted).toBe(true);
    expect(signals.b?.aborted).toBe(false);

    await act(async () => {
      resolvers.a?.('stale');
      resolvers.b?.('fresh');
    });
    expect(onLoad).toHaveBeenCalledTimes(1);
    expect(onLoad).toHaveBeenCalledWith('fresh');

    unmount();
    expect(signals.b?.aborted).toBe(true);
  });

  it('키가 없으면 요청하지 않는다', () => {
    const load = vi.fn(() => Promise.resolve('x'));
    renderHook(() => useAbortableLoad(null, load, vi.fn()));
    expect(load).not.toHaveBeenCalled();
  });
});
