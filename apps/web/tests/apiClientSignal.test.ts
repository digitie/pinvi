import { describe, expect, it } from 'vitest';
import { ApiClient, featureApi, geoApi } from '@pinvi/api-client';

// kor-travel-concierge #111 패턴: 호출부가 넘긴 AbortSignal이 upstream fetch까지 전달되어야
// 취소된 검색이 백엔드에 쌓이지 않는다. fetcher override로 전달 여부를 고정한다.
//
// T-315: 클라이언트가 요청 타임아웃을 걸면서 fetch에 실리는 signal은 호출부 signal과
// 타임아웃을 합친 **파생 signal**이다. 따라서 동일 객체(identity)가 아니라 **취소 전파**를
// 고정한다 — 호출부가 abort하면 upstream signal도 abort돼야 한다.
/** 응답이 오지 않는 fetcher — in-flight 상태에서 취소 전파를 관찰한다. */
function hangingClient() {
  let received: RequestInit | undefined;
  const fetcher = ((_url: string, init?: RequestInit) => {
    received = init;
    return new Promise<Response>((_resolve, reject) => {
      const fail = () => reject(new DOMException('The operation was aborted.', 'AbortError'));
      if (init?.signal?.aborted) {
        fail();
        return;
      }
      init?.signal?.addEventListener('abort', fail);
    });
  }) as unknown as typeof fetch;
  return {
    client: new ApiClient({ baseUrl: 'http://test', fetcher }),
    received: () => received,
  };
}

function recordingClient(options: { timeoutMs?: number } = {}) {
  let received: RequestInit | undefined;
  const fetcher = ((_url: string, init?: RequestInit) => {
    received = init;
    return Promise.resolve(new Response(JSON.stringify({ data: [] }), { status: 200 }));
  }) as unknown as typeof fetch;
  return {
    client: new ApiClient({ baseUrl: 'http://test', fetcher, ...options }),
    received: () => received,
  };
}

async function ignoreSchema(run: () => Promise<unknown>): Promise<void> {
  // signal은 fetch 호출 시점에 기록되므로 응답 schema parse 성공 여부와 무관하다.
  try {
    await run();
  } catch {
    /* 응답 shape는 본 테스트 관심사가 아니다 */
  }
}

describe('api-client AbortSignal 전파 (kor-travel-concierge #111 패턴)', () => {
  it('통합 검색(searchPlaces)이 넘긴 AbortSignal을 upstream fetch로 전달한다', async () => {
    const { client, received } = hangingClient();
    const controller = new AbortController();
    const pending = geoApi(client)
      .searchPlaces({ q: 'busan' }, { signal: controller.signal })
      .catch(() => 'aborted');

    await Promise.resolve();
    const upstream = received()?.signal;
    expect(upstream).toBeInstanceOf(AbortSignal);
    expect(upstream?.aborted).toBe(false);

    controller.abort();
    expect(upstream?.aborted).toBe(true);
    await expect(pending).resolves.toBe('aborted');
  });

  it('feature inBounds도 AbortSignal을 전달한다', async () => {
    const { client, received } = hangingClient();
    const controller = new AbortController();
    const pending = featureApi(client)
      .inBounds({ bbox: '1,2,3,4', zoom: 12 }, { signal: controller.signal })
      .catch(() => 'aborted');

    await Promise.resolve();
    controller.abort();
    expect(received()?.signal?.aborted).toBe(true);
    await expect(pending).resolves.toBe('aborted');
  });

  it('signal을 주지 않아도 타임아웃 signal은 실린다(요청이 영구히 매달리지 않게)', async () => {
    const { client, received } = recordingClient();
    await ignoreSchema(() => geoApi(client).searchPlaces({ q: 'busan' }));
    expect(received()?.signal).toBeInstanceOf(AbortSignal);
  });

  it('타임아웃을 끄면 signal을 실지 않는다(기존 동작)', async () => {
    const { client, received } = recordingClient({ timeoutMs: 0 });
    await ignoreSchema(() => geoApi(client).searchPlaces({ q: 'busan' }));
    expect(received()?.signal == null).toBe(true);
  });
});
