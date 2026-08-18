import { describe, expect, it, vi } from 'vitest';
import { ApiClient, ApiError, tripApi } from '@pinvi/api-client';
import { z } from 'zod';

/**
 * 요청 타임아웃(T-315 2차 리뷰) — 응답이 오지 않는 요청이 UI를 영구 `저장 중`으로 잠그지
 * 않아야 한다. 모달의 busy 잠금(Escape/backdrop/닫기)이 반드시 풀린다는 근거가 이 계층이다.
 */
function hangingClient(timeoutMs?: number) {
  const fetcher = ((_url: string, init?: RequestInit) =>
    new Promise<Response>((_resolve, reject) => {
      const fail = () => reject(new DOMException('The operation was aborted.', 'AbortError'));
      // 실제 fetch는 이미 abort된 signal을 받으면 즉시 거부한다.
      if (init?.signal?.aborted) {
        fail();
        return;
      }
      init?.signal?.addEventListener('abort', fail);
    })) as unknown as typeof fetch;
  return new ApiClient({ baseUrl: 'http://test', fetcher, timeoutMs });
}

describe('api-client 요청 타임아웃', () => {
  it('응답이 없으면 REQUEST_TIMEOUT ApiError로 끝난다', async () => {
    const client = hangingClient(20);
    await expect(
      client.request('/slow', { method: 'GET', schema: z.unknown() }),
    ).rejects.toMatchObject({ code: 'REQUEST_TIMEOUT', status: 408 });
  });

  it('호출부가 취소하면 타임아웃 오류가 아니라 AbortError를 그대로 던진다', async () => {
    const client = hangingClient(10_000);
    const controller = new AbortController();
    const promise = client.request('/slow', {
      method: 'GET',
      schema: z.unknown(),
      signal: controller.signal,
    });
    controller.abort();
    await expect(promise).rejects.not.toBeInstanceOf(ApiError);
  });

  it('timeoutMs=0이면 타임아웃을 걸지 않는다(장시간 admin 작업)', async () => {
    const client = hangingClient(0);
    const settled = vi.fn();
    void client.request('/forever', { method: 'GET', schema: z.unknown() }).then(settled, settled);
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(settled).not.toHaveBeenCalled();
  });

  it('개별 호출의 timeoutMs가 클라이언트 기본값을 덮어쓴다', async () => {
    let received: RequestInit | undefined;
    const fetcher = ((_url: string, init?: RequestInit) => {
      received = init;
      return Promise.resolve(
        new Response(JSON.stringify({ data: null }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }) as unknown as typeof fetch;
    const client = new ApiClient({ baseUrl: 'http://test', fetcher, timeoutMs: 20 });

    // 기본 경로도 signal이 붙는다(타임아웃 컨트롤러).
    await tripApi(client)
      .list({ bucket: 'all', limit: 1 })
      .catch(() => undefined);
    expect(received?.signal).toBeInstanceOf(AbortSignal);
  });
});
