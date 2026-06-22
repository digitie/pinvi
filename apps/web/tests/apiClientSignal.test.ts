import { describe, expect, it } from 'vitest';
import { ApiClient, featureApi } from '@pinvi/api-client';

// kor-travel-concierge #111 패턴: 호출부가 넘긴 AbortSignal이 upstream fetch까지 전달되어야
// 취소된 검색이 백엔드에 쌓이지 않는다. fetcher override로 전달 여부를 고정한다.
function recordingClient() {
  let received: RequestInit | undefined;
  const fetcher = ((_url: string, init?: RequestInit) => {
    received = init;
    return Promise.resolve(new Response(JSON.stringify({ data: [] }), { status: 200 }));
  }) as unknown as typeof fetch;
  return {
    client: new ApiClient({ baseUrl: 'http://test', fetcher }),
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
  it('feature search가 넘긴 AbortSignal을 upstream fetch로 전달한다', async () => {
    const { client, received } = recordingClient();
    const controller = new AbortController();
    await featureApi(client).search({ q: 'busan' }, { signal: controller.signal });
    expect(received()?.signal).toBe(controller.signal);
  });

  it('feature inBounds도 AbortSignal을 전달한다', async () => {
    const { client, received } = recordingClient();
    const controller = new AbortController();
    await ignoreSchema(() =>
      featureApi(client).inBounds({ bbox: '1,2,3,4', zoom: 12 }, { signal: controller.signal }),
    );
    expect(received()?.signal).toBe(controller.signal);
  });

  it('signal을 주지 않으면 fetch에 signal이 실리지 않는다(기존 동작 유지)', async () => {
    const { client, received } = recordingClient();
    await featureApi(client).search({ q: 'busan' });
    expect(received()?.signal == null).toBe(true);
  });
});
