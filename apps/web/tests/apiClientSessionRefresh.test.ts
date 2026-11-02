import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import { ApiClient, refreshCookieSession } from '@pinvi/api-client';

// 2026-11-02 prod e2e: access cookie는 10분(`pinvi_access_token_minutes`)인데 웹 클라이언트는
// 401을 받는 즉시 `onUnauthorized`(→ /login)로 보냈다. refresh cookie(7일)는 한 번도 쓰이지 않아
// 로그인 10분 뒤 작업 중이던 사용자가 튕겼다. cookie 모드 클라이언트는 401에서 세션을 한 번
// 갱신하고 원 요청을 1회 재시도해야 한다 — 동시 401은 갱신 하나를 공유한다(회전 경주 방지).

const Item = z.object({ ok: z.boolean() });

interface Call {
  url: string;
  method: string;
}

let baseCounter = 0;
/** 테스트마다 다른 baseUrl — 모듈 수준 single-flight가 테스트 사이에 새지 않게. */
function nextBase(): string {
  baseCounter += 1;
  return `http://api-${baseCounter}.test`;
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const UNAUTHORIZED = { error: { code: 'TOKEN_INVALID', message: '인증 정보가 없습니다.' } };

/**
 * cookie jar를 흉내 내는 fetcher. `/auth/refresh`가 성공하면 이후 요청이 200이 된다.
 * `refreshDelayMs`로 갱신을 붙잡아 두고 동시 401이 같은 갱신을 기다리는지 본다.
 */
function sessionServer(options: { refreshOk?: boolean; refreshDelayMs?: number } = {}) {
  const calls: Call[] = [];
  let sessionValid = false;
  const fetcher = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? 'GET';
    calls.push({ url, method });
    if (url.endsWith('/auth/refresh')) {
      if (options.refreshDelayMs) {
        await new Promise((resolve) => setTimeout(resolve, options.refreshDelayMs));
      }
      if (options.refreshOk === false) return json(401, UNAUTHORIZED);
      sessionValid = true;
      return json(200, { data: { user_id: 'u1' } });
    }
    if (!sessionValid) return json(401, UNAUTHORIZED);
    return json(200, { data: { ok: true } });
  }) as unknown as typeof fetch;
  return {
    calls,
    fetcher,
    refreshCalls: () => calls.filter((c) => c.url.endsWith('/auth/refresh')).length,
  };
}

describe('api-client cookie 세션 자동 갱신', () => {
  it('401이면 세션을 갱신하고 원 요청을 1회 재시도한다', async () => {
    const server = sessionServer();
    const onUnauthorized = vi.fn();
    const client = new ApiClient({ baseUrl: nextBase(), fetcher: server.fetcher, onUnauthorized });

    await expect(client.request('/trips', { schema: Item })).resolves.toEqual({ ok: true });

    expect(server.refreshCalls()).toBe(1);
    expect(server.calls.filter((c) => c.url.endsWith('/trips'))).toHaveLength(2);
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it('동시 401은 갱신 하나를 공유한다(single-flight)', async () => {
    const server = sessionServer({ refreshDelayMs: 20 });
    const client = new ApiClient({ baseUrl: nextBase(), fetcher: server.fetcher });

    const results = await Promise.all([
      client.request('/trips', { schema: Item }),
      client.request('/features/in-bounds', { schema: Item }),
      client.request('/auth/me', { schema: Item }),
    ]);

    expect(results).toEqual([{ ok: true }, { ok: true }, { ok: true }]);
    expect(server.refreshCalls()).toBe(1);
  });

  it('같은 API를 쓰는 다른 인스턴스와 웹소켓 갱신도 같은 갱신을 공유한다', async () => {
    const server = sessionServer({ refreshDelayMs: 20 });
    const base = nextBase();
    const a = new ApiClient({ baseUrl: base, fetcher: server.fetcher });
    const b = new ApiClient({ baseUrl: base, fetcher: server.fetcher });

    const [ra, rb, ws] = await Promise.all([
      a.request('/trips', { schema: Item }),
      b.request('/admin/users', { schema: Item }),
      refreshCookieSession(base, server.fetcher),
    ]);

    expect(ra).toEqual({ ok: true });
    expect(rb).toEqual({ ok: true });
    expect(ws).toBe(true);
    expect(server.refreshCalls()).toBe(1);
  });

  it('갱신이 실패하면 다시 보내지 않고 onUnauthorized를 부르고 오류를 던진다', async () => {
    const server = sessionServer({ refreshOk: false });
    const onUnauthorized = vi.fn();
    const client = new ApiClient({ baseUrl: nextBase(), fetcher: server.fetcher, onUnauthorized });

    await expect(client.request('/trips', { schema: Item })).rejects.toMatchObject({
      status: 401,
      code: 'TOKEN_INVALID',
    });
    expect(server.refreshCalls()).toBe(1);
    // 서버는 실패한 갱신에 두 cookie를 지운다 — 다시 보내 봐야 401이다.
    expect(server.calls.filter((c) => c.url.endsWith('/trips'))).toHaveLength(1);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it('갱신을 기다리는 중 취소되면 401이 아니라 AbortError로 끝나고 로그인 화면으로 보내지 않는다', async () => {
    const server = sessionServer({ refreshDelayMs: 50 });
    const onUnauthorized = vi.fn();
    const client = new ApiClient({ baseUrl: nextBase(), fetcher: server.fetcher, onUnauthorized });
    const controller = new AbortController();

    const pending = client.request('/features/in-bounds', {
      schema: Item,
      signal: controller.signal,
    });
    setTimeout(() => controller.abort(), 10);

    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it('갱신 뒤에 도착한 늦은 401은 다시 갱신하지 않고 그대로 재시도한다', async () => {
    const calls: Call[] = [];
    let sessionValid = false;
    const fetcher = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push({ url, method: init?.method ?? 'GET' });
      if (url.endsWith('/auth/refresh')) {
        sessionValid = true;
        return json(200, { data: { user_id: 'u1' } });
      }
      const validAtSend = sessionValid;
      if (url.endsWith('/slow')) await new Promise((resolve) => setTimeout(resolve, 40));
      return validAtSend ? json(200, { data: { ok: true } }) : json(401, UNAUTHORIZED);
    }) as unknown as typeof fetch;
    const client = new ApiClient({ baseUrl: nextBase(), fetcher });

    const slow = client.request('/slow', { schema: Item });
    await new Promise((resolve) => setTimeout(resolve, 5));
    await expect(client.request('/fast', { schema: Item })).resolves.toEqual({ ok: true });
    await expect(slow).resolves.toEqual({ ok: true });

    expect(calls.filter((c) => c.url.endsWith('/auth/refresh'))).toHaveLength(1);
  });

  it('재시도는 같은 메서드·본문·헤더로 다시 보낸다', async () => {
    const seen: RequestInit[] = [];
    let sessionValid = false;
    const fetcher = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/auth/refresh')) {
        sessionValid = true;
        return json(200, { data: {} });
      }
      seen.push(init ?? {});
      return sessionValid ? json(200, { data: { ok: true } }) : json(401, UNAUTHORIZED);
    }) as unknown as typeof fetch;
    const client = new ApiClient({ baseUrl: nextBase(), fetcher });

    await client.request('/trips/t1/pois', {
      method: 'POST',
      body: JSON.stringify({ title: '하회마을' }),
      headers: { 'Idempotency-Key': 'k1' },
      schema: Item,
    });

    expect(seen).toHaveLength(2);
    expect(seen[1]!.method).toBe('POST');
    expect(seen[1]!.body).toBe(seen[0]!.body);
    expect(seen[1]!.headers).toEqual(seen[0]!.headers);
  });

  it('여러 탭의 갱신은 Web Locks로 줄 세운다', async () => {
    const server = sessionServer();
    const lockNames: string[] = [];
    const locks = {
      request: vi.fn(async (name: string, callback: () => Promise<unknown>) => {
        lockNames.push(name);
        return callback();
      }),
    };
    Object.defineProperty(globalThis.navigator, 'locks', { value: locks, configurable: true });
    try {
      const base = nextBase();
      const client = new ApiClient({ baseUrl: base, fetcher: server.fetcher });
      await expect(client.request('/trips', { schema: Item })).resolves.toEqual({ ok: true });
      expect(lockNames).toEqual([`pinvi-auth-refresh:${base}`]);
      expect(server.refreshCalls()).toBe(1);
    } finally {
      delete (globalThis.navigator as unknown as { locks?: unknown }).locks;
    }
  });

  it('requestNoContent도 같은 규칙을 따른다', async () => {
    const server = sessionServer();
    const onUnauthorized = vi.fn();
    const client = new ApiClient({ baseUrl: nextBase(), fetcher: server.fetcher, onUnauthorized });

    await expect(
      client.requestNoContent('/trips/t1', { method: 'DELETE' }),
    ).resolves.toBeUndefined();
    expect(server.refreshCalls()).toBe(1);
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it.each([
    '/auth/login',
    '/auth/login?next=%2Ftrips',
    '/auth/logout',
    '/auth/register',
    '/auth/verify-email',
    '/auth/verify-email/resend',
  ])('%s의 401은 갱신하지 않는다(자격 증명 확인 경로)', async (path) => {
    const server = sessionServer();
    const onUnauthorized = vi.fn();
    const client = new ApiClient({
      baseUrl: nextBase(),
      fetcher: server.fetcher,
      onUnauthorized,
    });

    await expect(client.request(path, { method: 'POST', schema: Item })).rejects.toMatchObject({
      status: 401,
    });
    expect(server.refreshCalls()).toBe(0);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it('/auth/refresh 자신의 401은 다시 갱신하지 않는다(재귀 방지)', async () => {
    const server = sessionServer({ refreshOk: false });
    const client = new ApiClient({ baseUrl: nextBase(), fetcher: server.fetcher });

    await expect(
      client.request('/auth/refresh', { method: 'POST', schema: Item }),
    ).rejects.toMatchObject({ status: 401 });
    expect(server.refreshCalls()).toBe(1);
  });

  it('token 모드(getAuthToken) 클라이언트는 자체 갱신을 하지 않는다(모바일은 fetcher가 담당)', async () => {
    const server = sessionServer();
    const onUnauthorized = vi.fn();
    const client = new ApiClient({
      baseUrl: nextBase(),
      fetcher: server.fetcher,
      getAuthToken: async () => 'mobile-token',
      onUnauthorized,
    });

    await expect(client.request('/trips', { schema: Item })).rejects.toMatchObject({ status: 401 });
    expect(server.refreshCalls()).toBe(0);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });
});
