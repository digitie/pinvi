'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { Loader2, Send, Star, Trash2 } from 'lucide-react';
import { ApiError, telegramApi } from '@pinvi/api-client';
import type { TelegramTarget } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';

function targetName(target: TelegramTarget): string {
  return target.telegram_label || target.title_snapshot || target.telegram_chat_id;
}

export interface TripTelegramTargetsProps {
  tripId: string;
}

export function TripTelegramTargets({ tripId }: TripTelegramTargetsProps) {
  const [all, setAll] = useState<TelegramTarget[]>([]);
  const [linked, setLinked] = useState<TelegramTarget[]>([]);
  const [selected, setSelected] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const api = telegramApi(apiClient);
      const [allTargets, tripTargets] = await Promise.all([
        api.listTargets(),
        api.listTripTargets(tripId),
      ]);
      setAll(allTargets);
      setLinked(tripTargets);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '알림 대상을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [tripId]);

  useEffect(() => {
    void load();
  }, [load]);

  const linkedIds = new Set(linked.map((t) => t.id));
  const linkable = all.filter((t) => !linkedIds.has(t.id));
  const atLimit = linked.length >= 3;

  const link = async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await telegramApi(apiClient).linkTripTarget(tripId, selected);
      setSelected('');
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.code === 'MAX_TARGETS_REACHED') {
        setError('여행당 최대 3개 대상까지 연결할 수 있습니다.');
      } else {
        setError(err instanceof ApiError ? err.message : '연결에 실패했습니다.');
      }
    } finally {
      setBusy(false);
    }
  };

  const unlink = async (targetId: string) => {
    setBusyId(targetId);
    setError(null);
    try {
      await telegramApi(apiClient).unlinkTripTarget(tripId, targetId);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '연결 해제에 실패했습니다.');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section
      className="space-y-3 rounded-sm border border-hairline bg-white p-4"
      aria-label="Telegram 알림 대상"
      data-testid="trip-telegram-targets"
    >
      <h2 className="flex items-center gap-2 text-sm font-bold text-ink">
        <Send className="h-4 w-4 text-primary" aria-hidden="true" />
        Telegram 알림 대상
      </h2>
      <p className="text-xs text-muted">
        이 여행의 알림을 받을 대상을 연결합니다(최대 3개). 대상 등록은{' '}
        <Link href="/settings/telegram" className="text-primary underline">
          설정 &gt; Telegram 알림
        </Link>
        에서 합니다.
      </p>

      {error && (
        <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-xs text-error-text" data-testid="trip-telegram-error">
          {error}
        </p>
      )}

      {loading ? (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          불러오는 중…
        </p>
      ) : (
        <>
          {all.length === 0 ? (
            <p className="rounded-sm bg-surface-soft px-3 py-2 text-xs text-muted">
              등록된 Telegram 대상이 없습니다. 먼저 설정에서 대상을 등록하세요.
            </p>
          ) : (
            <div className="flex flex-wrap items-end gap-2">
              <label htmlFor="trip-telegram-select" className="text-xs font-semibold text-ink">
                대상 선택
                <select
                  id="trip-telegram-select"
                  value={selected}
                  onChange={(event) => setSelected(event.target.value)}
                  disabled={atLimit || linkable.length === 0}
                  className="mt-1 block h-9 min-w-48 rounded-sm border border-hairline px-2 text-sm font-normal text-ink outline-none focus:border-primary disabled:opacity-50"
                  data-testid="trip-telegram-select"
                >
                  <option value="">
                    {linkable.length === 0 ? '연결 가능한 대상 없음' : '선택하세요'}
                  </option>
                  {linkable.map((t) => (
                    <option key={t.id} value={t.id}>
                      {targetName(t)}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                onClick={() => void link()}
                disabled={busy || !selected || atLimit}
                className="inline-flex h-9 items-center gap-1 rounded-sm bg-primary px-3 text-sm font-semibold text-white disabled:opacity-50"
                data-testid="trip-telegram-link"
              >
                {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                연결
              </button>
              {atLimit && <span className="text-xs text-muted">최대 3개 연결됨</span>}
            </div>
          )}

          {linked.length > 0 && (
            <ul className="space-y-1" data-testid="trip-telegram-list">
              {linked.map((t) => (
                <li
                  key={t.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-sm border border-hairline px-3 py-2 text-sm"
                >
                  <span className="flex items-center gap-2 text-ink">
                    {t.is_default && <Star className="h-3.5 w-3.5 text-primary" aria-label="기본" />}
                    <span className="font-medium">{targetName(t)}</span>
                    <span className="font-mono text-xs text-muted">{t.telegram_chat_id}</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => void unlink(t.id)}
                    disabled={busyId === t.id}
                    aria-label={`${targetName(t)} 연결 해제`}
                    className="inline-flex h-7 items-center gap-1 rounded-sm border border-hairline px-2 text-xs font-semibold text-muted hover:bg-error-bg hover:text-error-text disabled:opacity-50"
                    data-testid={`trip-telegram-unlink-${t.telegram_chat_id}`}
                  >
                    {busyId === t.id ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                    ) : (
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    )}
                    해제
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
