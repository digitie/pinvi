import { describe, expect, it, vi } from 'vitest';
import { ApiClient, ApiError, isRequestTimeoutError } from '@pinvi/api-client';
import { z } from 'zod';

/**
 * 요청 수명 계약(T-316) — T-315 3차 리뷰가 철회를 요구하며 남긴 5개 요구사항을 여기서 고정한다.
 * ① 타이머는 헤더가 아니라 **body 소비 완료까지** 유지 ② 호출부 abort는 헤더 이후에도 전파
 * ③ 타임아웃은 서버 확정 4xx와 구분 ④ 장시간 호출은 예산을 끌 수 있다 ⑤ 취소가 가능하다.
 */

/** 헤더는 즉시 주고 body는 abort될 때까지 끝나지 않는 응답(멈춘 스트림). */
function stalledBodyFetcher(record?: (init: RequestInit | undefined) => void) {
  return ((_url: string, init?: RequestInit) => {
    record?.(init);
    const stream = new ReadableStream({
      start(controller) {
        const fail = () => controller.error(new DOMException('aborted', 'AbortError'));
        if (init?.signal?.aborted) fail();
        else init?.signal?.addEventListener('abort', fail);
      },
    });
    return Promise.resolve(
      new Response(stream, { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
  }) as unknown as typeof fetch;
}

/** 헤더조차 오지 않는 응답. */
function stalledHeaderFetcher() {
  return ((_url: string, init?: RequestInit) =>
    new Promise<Response>((_resolve, reject) => {
      const fail = () => reject(new DOMException('aborted', 'AbortError'));
      if (init?.signal?.aborted) fail();
      else init?.signal?.addEventListener('abort', fail);
    })) as unknown as typeof fetch;
}

const anySchema = z.unknown();

describe('api-client 요청 수명 계약', () => {
  it('① 헤더가 온 뒤 body가 멈춰도 타임아웃이 발화한다', async () => {
    const client = new ApiClient({
      baseUrl: 'http://test',
      fetcher: stalledBodyFetcher(),
      timeoutMs: 30,
    });
    const err = await client
      .request('/stalled-body', { method: 'GET', schema: anySchema })
      .catch((e: unknown) => e);
    expect(isRequestTimeoutError(err)).toBe(true);
  });

  it('① 헤더가 오지 않는 경우도 타임아웃이 발화한다', async () => {
    const client = new ApiClient({
      baseUrl: 'http://test',
      fetcher: stalledHeaderFetcher(),
      timeoutMs: 30,
    });
    const err = await client
      .request('/stalled-header', { method: 'GET', schema: anySchema })
      .catch((e: unknown) => e);
    expect(isRequestTimeoutError(err)).toBe(true);
  });

  it('② 헤더 수신 **이후**에 호출부가 취소해도 upstream까지 전파된다', async () => {
    let upstream: RequestInit | undefined;
    const client = new ApiClient({
      baseUrl: 'http://test',
      fetcher: stalledBodyFetcher((init) => {
        upstream = init;
      }),
      // 타임아웃과 무관하게 취소가 전파되는지 본다.
      timeoutMs: 0,
    });
    const controller = new AbortController();
    const pending = client
      .request('/stalled-body', { method: 'GET', schema: anySchema, signal: controller.signal })
      .catch((e: unknown) => e);

    // 헤더는 이미 도착했고 body 소비 중인 시점.
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(upstream?.signal?.aborted).toBe(false);

    controller.abort();
    expect(upstream?.signal?.aborted).toBe(true);

    const err = await pending;
    // 호출부 취소는 타임아웃이 아니다.
    expect(isRequestTimeoutError(err)).toBe(false);
  });

  it('③ 타임아웃은 서버가 확정한 4xx와 구분된다(status 0)', async () => {
    const client = new ApiClient({
      baseUrl: 'http://test',
      fetcher: stalledHeaderFetcher(),
      timeoutMs: 20,
    });
    const err = await client
      .request('/slow', { method: 'GET', schema: anySchema })
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(0);
    // status < 500 을 "서버가 확정한 terminal"로 쓰는 호출부(Idempotency-Key 폐기)가
    // 타임아웃을 그렇게 오분류하면 비멱등 요청이 중복 실행된다.
    expect(isRequestTimeoutError(err)).toBe(true);
  });

  it('④ 개별 호출이 예산을 덮어쓴다 — 0이면 끄고, 짧게 주면 그 값이 이긴다', async () => {
    const offClient = new ApiClient({
      baseUrl: 'http://test',
      fetcher: stalledHeaderFetcher(),
      timeoutMs: 20,
    });
    const settled = vi.fn();
    void offClient
      .request('/forever', { method: 'GET', schema: anySchema, timeoutMs: 0 })
      .then(settled, settled);
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(settled).not.toHaveBeenCalled();

    const shortClient = new ApiClient({
      baseUrl: 'http://test',
      fetcher: stalledHeaderFetcher(),
      timeoutMs: 10_000,
    });
    const err = await shortClient
      .request('/short', { method: 'GET', schema: anySchema, timeoutMs: 20 })
      .catch((e: unknown) => e);
    expect(isRequestTimeoutError(err)).toBe(true);
  });

  it('④ timeoutMs는 upstream fetch init으로 새지 않는다', async () => {
    let upstream: RequestInit | undefined;
    const fetcher = ((_url: string, init?: RequestInit) => {
      upstream = init;
      return Promise.resolve(
        new Response(JSON.stringify({ data: null }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }) as unknown as typeof fetch;
    const client = new ApiClient({ baseUrl: 'http://test', fetcher });
    await client.request('/ok', { method: 'GET', schema: z.null(), timeoutMs: 1_000 });
    expect(upstream && 'timeoutMs' in upstream).toBe(false);
  });

  it('예산이 꺼져 있고 호출부 signal도 없으면 upstream에 signal을 싣지 않는다', async () => {
    let upstream: RequestInit | undefined;
    const fetcher = ((_url: string, init?: RequestInit) => {
      upstream = init;
      return Promise.resolve(
        new Response(JSON.stringify({ data: null }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }) as unknown as typeof fetch;
    const client = new ApiClient({ baseUrl: 'http://test', fetcher, timeoutMs: 0 });
    await client.request('/ok', { method: 'GET', schema: z.null() });
    expect(upstream?.signal == null).toBe(true);
  });
});
