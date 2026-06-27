import { describe, expect, it, vi } from 'vitest';
import { TripRealtimeClient, tripWebSocketUrl, type WebSocketLike } from '@pinvi/api-client';

type ListenerMap = {
  open: Array<(event: Event) => void>;
  message: Array<(event: MessageEvent) => void>;
  close: Array<(event: Event) => void>;
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

  close(): void {
    this.readyState = 3;
    this.listeners.close.forEach((listener) => listener(new Event('close')));
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

  static reset(): void {
    FakeWebSocket.instances = [];
  }
}

describe('TripRealtimeClient', () => {
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
});
