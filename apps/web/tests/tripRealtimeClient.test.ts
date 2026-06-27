import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  TripRealtimeClient,
  tripRealtimeInvalidationKeys,
  tripWebSocketUrl,
  type TripRealtimeCloseEvent,
  type WebSocketLike,
} from '@pinvi/api-client';

type ListenerMap = {
  open: Array<(event: Event) => void>;
  message: Array<(event: MessageEvent) => void>;
  close: Array<(event: TripRealtimeCloseEvent) => void>;
  error: Array<(event: Event) => void>;
};

class FakeWebSocket implements WebSocketLike {
  static instances: FakeWebSocket[] = [];

  readonly sent: unknown[] = [];
  readyState = 0;
  private readonly listeners: ListenerMap = { open: [], message: [], close: [], error: [] };

  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  addEventListener<T extends keyof ListenerMap>(type: T, listener: ListenerMap[T][number]): void {
    this.listeners[type].push(listener as never);
  }

  removeEventListener<T extends keyof ListenerMap>(type: T, listener: ListenerMap[T][number]): void {
    this.listeners[type] = this.listeners[type].filter((item) => item !== listener) as ListenerMap[T];
  }

  send(data: string): void {
    this.sent.push(JSON.parse(data));
  }

  close(code = 1000, reason = ''): void {
    this.readyState = 3;
    this.emitClose(code, reason);
  }

  serverClose(code: number, reason: string): void {
    this.readyState = 3;
    this.emitClose(code, reason);
  }

  open(): void {
    this.readyState = 1;
    this.listeners.open.forEach((listener) => listener(new Event('open')));
  }

  receive(payload: unknown): void {
    this.listeners.message.forEach((listener) =>
      listener(new MessageEvent('message', { data: JSON.stringify(payload) })),
    );
  }

  private emitClose(code: number, reason: string): void {
    const event: TripRealtimeCloseEvent = { code, reason, wasClean: code === 1000 };
    this.listeners.close.forEach((listener) => listener(event));
  }

  static reset(): void {
    FakeWebSocket.instances = [];
  }
}

describe('TripRealtimeClient', () => {
  afterEach(() => {
    vi.useRealTimers();
    FakeWebSocket.reset();
  });

  it('API base URL을 trip WebSocket URL로 변환한다', () => {
    expect(tripWebSocketUrl('http://localhost:12801', 'trip-1')).toBe(
      'ws://localhost:12801/ws/trips/trip-1',
    );
    expect(tripWebSocketUrl('https://api.example.com/v1/', 'trip 1', 'token-1')).toBe(
      'wss://api.example.com/v1/ws/trips/trip%201?token=token-1',
    );
  });

  it('open 직후 heartbeat를 보내고 ping에 pong으로 응답한다', () => {
    FakeWebSocket.reset();
    const client = new TripRealtimeClient({
      apiBaseUrl: 'http://localhost:12801',
      tripId: 'trip-1',
      WebSocketCtor: FakeWebSocket,
      heartbeatIntervalMs: 60_000,
    });

    client.setViewingDay(2);
    client.connect();
    const socket = FakeWebSocket.instances[0];
    expect(socket?.url).toBe('ws://localhost:12801/ws/trips/trip-1');

    socket?.open();
    expect(socket?.sent.at(-1)).toEqual({
      type: 'presence.heartbeat',
      payload: { viewing_day: 2 },
    });

    socket?.receive({ type: 'ping', payload: { ts: 'now' } });
    expect(socket?.sent.at(-1)).toEqual({ type: 'pong', payload: {} });

    client.sendPresenceCursor({ lon: 127.1, lat: 37.5 });
    expect(socket?.sent.at(-1)).toEqual({
      type: 'presence.cursor',
      payload: { longitude: 127.1, latitude: 37.5 },
    });
    client.disconnect();
  });

  it('서버 이벤트를 등록된 handler로 전달한다', () => {
    FakeWebSocket.reset();
    const onEvent = vi.fn();
    const client = new TripRealtimeClient({
      apiBaseUrl: 'http://localhost:12801',
      tripId: 'trip-1',
      WebSocketCtor: FakeWebSocket,
      onEvent,
    });

    client.connect();
    const socket = FakeWebSocket.instances[0];
    socket?.open();
    socket?.receive({
      type: 'poi.created',
      trip_id: 'trip-1',
      actor_user_id: 'user-1',
      payload: { poi_id: 'poi-1' },
    });

    expect(onEvent).toHaveBeenCalledWith({
      type: 'poi.created',
      trip_id: 'trip-1',
      actor_user_id: 'user-1',
      payload: { poi_id: 'poi-1' },
      ts: undefined,
      version: undefined,
    });
    client.disconnect();
  });

  it('4401 close에서 auth refresh 후 즉시 재연결한다', async () => {
    vi.useFakeTimers();
    const statuses: string[] = [];
    const onClose = vi.fn();
    const onAuthRefresh = vi.fn().mockResolvedValue(true);
    const client = new TripRealtimeClient({
      apiBaseUrl: 'http://localhost:12801',
      tripId: 'trip-1',
      WebSocketCtor: FakeWebSocket,
      reconnectInitialDelayMs: 1000,
      onClose,
      onAuthRefresh,
      onStatus: (status) => statuses.push(status),
    });

    client.connect();
    FakeWebSocket.instances[0]?.open();
    FakeWebSocket.instances[0]?.serverClose(4401, 'token_invalid');

    await Promise.resolve();
    await vi.advanceTimersByTimeAsync(0);

    expect(onClose).toHaveBeenCalledWith({
      code: 4401,
      reason: 'token_invalid',
      category: 'unauthorized',
      retryable: true,
    });
    expect(onAuthRefresh).toHaveBeenCalledOnce();
    expect(statuses).toContain('refreshing-auth');
    expect(statuses).toContain('reconnecting');
    expect(FakeWebSocket.instances).toHaveLength(2);
    client.disconnect();
  });

  it('4403 close는 권한 상실 상태로 멈추고 재연결하지 않는다', async () => {
    vi.useFakeTimers();
    const statuses: string[] = [];
    const client = new TripRealtimeClient({
      apiBaseUrl: 'http://localhost:12801',
      tripId: 'trip-1',
      WebSocketCtor: FakeWebSocket,
      reconnectInitialDelayMs: 50,
      onStatus: (status) => statuses.push(status),
    });

    client.connect();
    FakeWebSocket.instances[0]?.open();
    FakeWebSocket.instances[0]?.serverClose(4403, 'permission_denied');
    await vi.advanceTimersByTimeAsync(1000);

    expect(statuses.at(-1)).toBe('permission-denied');
    expect(FakeWebSocket.instances).toHaveLength(1);
    client.disconnect();
  });

  it('4429 close는 제한 상태를 노출하고 backoff 후 재연결한다', async () => {
    vi.useFakeTimers();
    const statuses: string[] = [];
    const client = new TripRealtimeClient({
      apiBaseUrl: 'http://localhost:12801',
      tripId: 'trip-1',
      WebSocketCtor: FakeWebSocket,
      reconnectInitialDelayMs: 50,
      onStatus: (status) => statuses.push(status),
    });

    client.connect();
    FakeWebSocket.instances[0]?.open();
    FakeWebSocket.instances[0]?.serverClose(4429, 'rate_limited');

    expect(statuses).toContain('rate-limited');
    expect(statuses.at(-1)).toBe('reconnecting');
    await vi.advanceTimersByTimeAsync(49);
    expect(FakeWebSocket.instances).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeWebSocket.instances).toHaveLength(2);
    client.disconnect();
  });

  it('manual disconnect는 재연결하지 않는다', async () => {
    vi.useFakeTimers();
    const client = new TripRealtimeClient({
      apiBaseUrl: 'http://localhost:12801',
      tripId: 'trip-1',
      WebSocketCtor: FakeWebSocket,
      reconnectInitialDelayMs: 50,
    });

    client.connect();
    FakeWebSocket.instances[0]?.open();
    client.disconnect();
    await vi.advanceTimersByTimeAsync(1000);

    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it('domain event를 TanStack Query invalidation key로 매핑한다', () => {
    expect(tripRealtimeInvalidationKeys({ type: 'poi.created', trip_id: 'trip-1' })).toEqual([
      ['trips'],
      ['trips', 'detail', 'trip-1'],
    ]);
    expect(tripRealtimeInvalidationKeys({ type: 'comment.created' }, 'trip-1')).toEqual([
      ['trips', 'comments', 'trip-1'],
    ]);
    expect(tripRealtimeInvalidationKeys({ type: 'presence.update', trip_id: 'trip-1' })).toEqual([]);
  });
});
