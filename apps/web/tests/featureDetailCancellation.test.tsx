import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { FeatureDetailCard } from '@pinvi/schemas';
import { useFeatureDetailCard } from '@/lib/useFeatureDetailCard';

const mocks = vi.hoisted(() => ({ detailCard: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiClient: {} }));
vi.mock('@pinvi/api-client', async () => ({
  ...(await vi.importActual<typeof import('@pinvi/api-client')>('@pinvi/api-client')),
  featureApi: () => ({ detailCard: mocks.detailCard }),
}));
function card(id: string): FeatureDetailCard {
  return {
    kind: 'place',
    feature_id: id,
    name: id,
    coord: null,
    category: null,
    category_label: null,
    address_line: null,
    marker_color: 'P-08',
    marker_icon: 'marker',
    homepage_url: null,
    enrichment: [],
    degraded_providers: [],
    phone: null,
    business_hours: null,
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
beforeEach(() => {
  mocks.detailCard.mockReset();
});
describe('상세 카드 요청 소유권', () => {
  it('abort를 무시하는 이전 요청이 늦게 끝나도 새 장소 결과를 덮지 않는다', async () => {
    const first = deferred<FeatureDetailCard>();
    mocks.detailCard.mockReturnValueOnce(first.promise).mockResolvedValueOnce(card('new'));
    const { result, rerender } = renderHook(({ id }) => useFeatureDetailCard(id), {
      initialProps: { id: 'old' },
    });
    const oldSignal = mocks.detailCard.mock.calls[0]?.[2].signal as AbortSignal | undefined;
    rerender({ id: 'new' });
    await waitFor(() => expect(result.current.card?.feature_id).toBe('new'));
    expect(oldSignal?.aborted).toBe(true);
    await act(async () => {
      first.resolve(card('old'));
      await first.promise;
    });
    expect(result.current.card?.feature_id).toBe('new');
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });
  it('선택 해제 뒤 도착한 결과를 버린다', async () => {
    const pending = deferred<FeatureDetailCard>();
    mocks.detailCard.mockReturnValueOnce(pending.promise);
    const { result, rerender } = renderHook(
      ({ id }: { id: string | null }) => useFeatureDetailCard(id),
      { initialProps: { id: 'old' as string | null } },
    );
    rerender({ id: null });
    await act(async () => {
      pending.resolve(card('old'));
      await pending.promise;
    });
    expect(result.current.card).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });
});
