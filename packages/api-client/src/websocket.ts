export const TRIP_REALTIME_CLOSE_CODES = {
  unauthorized: 4401,
  permissionDenied: 4403,
  badMessage: 4400,
  connectionLimit: 4408,
  rateLimited: 4429,
} as const;

export type TripRealtimeStatus =
  | 'idle'
  | 'connecting'
  | 'open'
  | 'closed'
  | 'error'
  | 'refreshing-auth'
  | 'reconnecting'
  | 'permission-denied'
  | 'connection-limited'
  | 'rate-limited';

export type TripRealtimeCloseCategory =
  | 'unauthorized'
  | 'permission-denied'
  | 'bad-message'
  | 'connection-limited'
  | 'rate-limited'
  | 'closed';

export interface TripRealtimeCloseInfo {
  code: number | null;
  reason: string;
  category: TripRealtimeCloseCategory;
  retryable: boolean;
}

export interface TripRealtimeEvent {
  type: string;
  trip_id?: string;
  actor_user_id?: string | null;
  ts?: string;
  version?: number | null;
  payload?: Record<string, unknown>;
}

export interface WebSocketLike {
  readonly readyState: number;
  send(data: string): void;
  close(code?: number, reason?: string): void;
  addEventListener(type: 'open', listener: (event: Event) => void): void;
  addEventListener(type: 'message', listener: (event: { data: unknown }) => void): void;
  addEventListener(type: 'close', listener: (event: TripRealtimeCloseEvent) => void): void;
  addEventListener(type: 'error', listener: (event: Event) => void): void;
  removeEventListener(type: 'open', listener: (event: Event) => void): void;
  removeEventListener(type: 'message', listener: (event: { data: unknown }) => void): void;
  removeEventListener(type: 'close', listener: (event: TripRealtimeCloseEvent) => void): void;
  removeEventListener(type: 'error', listener: (event: Event) => void): void;
}

export type WebSocketCtor = new (url: string) => WebSocketLike;
export interface TripRealtimeCloseEvent {
  code: number;
  reason: string;
  wasClean: boolean;
}

export interface TripRealtimeClientOptions {
  apiBaseUrl: string;
  tripId: string;
  token?: string | null;
  WebSocketCtor?: WebSocketCtor;
  heartbeatIntervalMs?: number;
  reconnectInitialDelayMs?: number;
  reconnectMaxDelayMs?: number;
  /** Fraction of the backoff window to randomize as jitter (0..1). Default 0.25. */
  reconnectJitterRatio?: number;
  /**
   * Cap on consecutive auth-refresh-driven reconnects before giving up, so a server
   * that keeps closing with 4401 even after a "successful" refresh cannot pin the
   * client in a tight reconnect loop. Default 5.
   */
  maxAuthRefreshAttempts?: number;
  /**
   * How long a connection must stay open before the consecutive-auth-refresh counter
   * resets. Prevents an open→4401→open flap from silently resetting the cap. Default 10s.
   */
  authRefreshResetMs?: number;
  /** Injectable RNG for jitter (testing). Default Math.random. */
  random?: () => number;
  onEvent?: (event: TripRealtimeEvent) => void;
  onStatus?: (status: TripRealtimeStatus) => void;
  onClose?: (info: TripRealtimeCloseInfo) => void;
  onAuthRefresh?: (info: TripRealtimeCloseInfo) => Promise<boolean> | boolean;
  onError?: (error: unknown) => void;
}

const OPEN = 1;

export function tripWebSocketUrl(apiBaseUrl: string, tripId: string, token?: string | null): string {
  const url = new URL(apiBaseUrl);
  const protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  const basePath = url.pathname.replace(/\/$/, '');
  const searchParams = new URLSearchParams(url.search);
  if (token) searchParams.set('token', token);
  const query = searchParams.toString();
  return `${protocol}//${url.host}${basePath}/ws/trips/${encodeURIComponent(tripId)}${
    query ? `?${query}` : ''
  }`;
}

export function classifyTripRealtimeClose(event: Partial<TripRealtimeCloseEvent>): TripRealtimeCloseInfo {
  const code = typeof event.code === 'number' ? event.code : null;
  const reason = typeof event.reason === 'string' ? event.reason : '';

  if (code === TRIP_REALTIME_CLOSE_CODES.unauthorized) {
    return { code, reason, category: 'unauthorized', retryable: true };
  }
  if (code === TRIP_REALTIME_CLOSE_CODES.permissionDenied) {
    return { code, reason, category: 'permission-denied', retryable: false };
  }
  if (code === TRIP_REALTIME_CLOSE_CODES.connectionLimit) {
    return { code, reason, category: 'connection-limited', retryable: true };
  }
  if (code === TRIP_REALTIME_CLOSE_CODES.rateLimited) {
    return { code, reason, category: 'rate-limited', retryable: true };
  }
  if (code === TRIP_REALTIME_CLOSE_CODES.badMessage) {
    // A protocol/version mismatch will not be fixed by reconnecting and resending the
    // same frame, so do not auto-retry — surface it instead of looping (T-289).
    return { code, reason, category: 'bad-message', retryable: false };
  }

  return { code, reason, category: 'closed', retryable: code !== 1000 };
}

export class TripRealtimeClient {
  private socket: WebSocketLike | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private authStableTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts = 0;
  private authRefreshAttempts = 0;
  private manualClose = false;
  private viewingDay: number | null = null;
  private authRefreshInFlight = false;

  constructor(private readonly opts: TripRealtimeClientOptions) {}

  connect(): void {
    if (this.socket != null) return;
    // A pending reconnect timer would otherwise open a second socket after this one
    // (re-entrant connect during the reconnect window) — clear it first (T-289).
    this.clearReconnect();
    this.manualClose = false;
    this.openSocket();
  }

  /** Operator-driven reconnect: reset backoff/auth counters and reopen immediately. */
  reconnect(): void {
    this.reconnectAttempts = 0;
    this.authRefreshAttempts = 0;
    this.clearReconnect();
    this.clearAuthStableReset();
    this.stopHeartbeat();
    const existing = this.socket;
    this.detachSocket();
    existing?.close();
    this.manualClose = false;
    this.openSocket();
  }

  disconnect(): void {
    this.manualClose = true;
    this.clearReconnect();
    this.clearAuthStableReset();
    this.stopHeartbeat();
    const socket = this.socket;
    this.detachSocket();
    socket?.close();
    this.emitStatus('closed');
  }

  setViewingDay(dayIndex: number | null): void {
    this.viewingDay = dayIndex;
    this.sendHeartbeat();
  }

  sendPresenceCursor(coord: { lon: number; lat: number }): void {
    this.sendJson({
      type: 'presence.cursor',
      payload: { longitude: coord.lon, latitude: coord.lat },
    });
  }

  private openSocket(): void {
    const globalWebSocket = globalThis.WebSocket as unknown as WebSocketCtor | undefined;
    const Ctor = this.opts.WebSocketCtor ?? globalWebSocket;
    if (Ctor == null) {
      this.emitStatus('error');
      this.opts.onError?.(new Error('WebSocket is not available in this runtime.'));
      return;
    }

    // Defensive: never overwrite a live socket without detaching/closing it first.
    if (this.socket != null) {
      const stale = this.socket;
      this.detachSocket();
      stale.close();
    }

    this.emitStatus('connecting');
    const socket = new Ctor(tripWebSocketUrl(this.opts.apiBaseUrl, this.opts.tripId, this.opts.token));
    this.socket = socket;

    socket.addEventListener('open', this.handleOpen);
    socket.addEventListener('message', this.handleMessage);
    socket.addEventListener('close', this.handleClose);
    socket.addEventListener('error', this.handleError);
  }

  private readonly handleOpen = () => {
    this.reconnectAttempts = 0;
    // Reset the auth-refresh cap only after the connection proves stable, so a rapid
    // open→4401→open flap cannot silently clear the cap (T-289).
    this.scheduleAuthStableReset();
    this.emitStatus('open');
    this.startHeartbeat();
    this.sendHeartbeat();
  };

  private readonly handleMessage = (event: { data: unknown }) => {
    const parsed = this.parseEvent(event.data);
    if (parsed == null) return;

    if (parsed.type === 'ping') {
      this.sendJson({ type: 'pong', payload: {} });
      return;
    }

    this.opts.onEvent?.(parsed);
  };

  private readonly handleClose = (event: TripRealtimeCloseEvent) => {
    const closeInfo = classifyTripRealtimeClose(event);
    this.detachSocket();
    this.stopHeartbeat();
    this.clearAuthStableReset();
    this.opts.onClose?.(closeInfo);

    if (this.manualClose) {
      this.emitStatus('closed');
      return;
    }

    if (closeInfo.category === 'unauthorized') {
      void this.handleUnauthorizedClose(closeInfo);
      return;
    }

    if (closeInfo.category === 'permission-denied') {
      this.emitStatus('permission-denied');
      return;
    }

    if (closeInfo.category === 'bad-message') {
      // Non-retryable protocol error: surface as error, do not reconnect (T-289).
      this.emitStatus('error');
      return;
    }

    if (closeInfo.category === 'connection-limited') {
      this.emitStatus('connection-limited');
      this.scheduleReconnect();
      return;
    }

    if (closeInfo.category === 'rate-limited') {
      this.emitStatus('rate-limited');
      this.scheduleReconnect();
      return;
    }

    if (closeInfo.retryable) {
      this.scheduleReconnect();
      return;
    }

    this.emitStatus('closed');
  };

  private readonly handleError = (event: Event) => {
    this.emitStatus('error');
    this.opts.onError?.(event);
  };

  private parseEvent(data: unknown): TripRealtimeEvent | null {
    try {
      const raw = typeof data === 'string' ? JSON.parse(data) : data;
      if (raw == null || typeof raw !== 'object') return null;
      const event = raw as Record<string, unknown>;
      if (typeof event.type !== 'string') return null;
      return {
        type: event.type,
        trip_id: typeof event.trip_id === 'string' ? event.trip_id : undefined,
        actor_user_id:
          typeof event.actor_user_id === 'string' || event.actor_user_id === null
            ? event.actor_user_id
            : undefined,
        ts: typeof event.ts === 'string' ? event.ts : undefined,
        version: typeof event.version === 'number' || event.version === null ? event.version : undefined,
        payload:
          event.payload != null && typeof event.payload === 'object'
            ? (event.payload as Record<string, unknown>)
            : undefined,
      };
    } catch (error) {
      this.opts.onError?.(error);
      return null;
    }
  }

  private async handleUnauthorizedClose(closeInfo: TripRealtimeCloseInfo): Promise<void> {
    if (this.authRefreshInFlight) return;
    const maxAuthAttempts = this.opts.maxAuthRefreshAttempts ?? 5;
    this.authRefreshAttempts += 1;
    if (this.authRefreshAttempts > maxAuthAttempts) {
      // Refresh keeps "succeeding" but the socket keeps closing 4401 — stop hammering
      // /auth/refresh and the WS endpoint (T-289).
      this.emitStatus('closed');
      return;
    }
    this.authRefreshInFlight = true;
    this.emitStatus('refreshing-auth');
    try {
      const refreshed = (await this.opts.onAuthRefresh?.(closeInfo)) ?? false;
      if (this.manualClose) return;
      if (!refreshed) {
        this.emitStatus('closed');
        return;
      }
      // First refresh reconnects promptly; repeats back off (with jitter) instead of
      // a zero-delay loop.
      const delay = this.authRefreshAttempts <= 1 ? 0 : this.backoffDelay(this.authRefreshAttempts - 1);
      this.scheduleReconnect(delay);
    } catch (error) {
      this.opts.onError?.(error);
      if (!this.manualClose) this.emitStatus('error');
    } finally {
      this.authRefreshInFlight = false;
    }
  }

  private scheduleReconnect(delayOverrideMs?: number): void {
    this.clearReconnect();
    let delay: number;
    if (delayOverrideMs != null) {
      delay = delayOverrideMs;
    } else {
      delay = this.backoffDelay(this.reconnectAttempts);
      this.reconnectAttempts += 1;
    }
    this.emitStatus('reconnecting');
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.openSocket();
    }, delay);
  }

  private backoffDelay(attempt: number): number {
    const initial = this.opts.reconnectInitialDelayMs ?? 1000;
    const max = this.opts.reconnectMaxDelayMs ?? 30_000;
    const base = Math.min(max, initial * 2 ** attempt);
    // Keep the first reconnect deterministic; jitter the rest to avoid a thundering
    // herd after a server restart / rate-limit window (T-289).
    if (attempt <= 0) return base;
    const ratio = this.opts.reconnectJitterRatio ?? 0.25;
    const random = this.opts.random ?? Math.random;
    const jitter = base * ratio * random();
    return Math.max(0, base - jitter);
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => this.sendHeartbeat(), this.opts.heartbeatIntervalMs ?? 5000);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer != null) clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = null;
  }

  private clearReconnect(): void {
    if (this.reconnectTimer != null) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
  }

  private scheduleAuthStableReset(): void {
    this.clearAuthStableReset();
    const resetMs = this.opts.authRefreshResetMs ?? 10_000;
    this.authStableTimer = setTimeout(() => {
      this.authStableTimer = null;
      this.authRefreshAttempts = 0;
    }, resetMs);
  }

  private clearAuthStableReset(): void {
    if (this.authStableTimer != null) clearTimeout(this.authStableTimer);
    this.authStableTimer = null;
  }

  private sendHeartbeat(): void {
    this.sendJson({ type: 'presence.heartbeat', payload: { viewing_day: this.viewingDay } });
  }

  private sendJson(payload: unknown): void {
    if (this.socket?.readyState !== OPEN) return;
    this.socket.send(JSON.stringify(payload));
  }

  private detachSocket(): void {
    const socket = this.socket;
    if (socket == null) return;
    socket.removeEventListener('open', this.handleOpen);
    socket.removeEventListener('message', this.handleMessage);
    socket.removeEventListener('close', this.handleClose);
    socket.removeEventListener('error', this.handleError);
    this.socket = null;
  }

  private emitStatus(status: TripRealtimeStatus): void {
    this.opts.onStatus?.(status);
  }
}
