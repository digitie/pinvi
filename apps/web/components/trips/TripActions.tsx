'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Copy, Loader2, Trash2 } from 'lucide-react';
import { ApiError, tripApi } from '@pinvi/api-client';
import { apiClient } from '@/lib/api';

export interface TripActionsProps {
  tripId: string;
}

export function TripActions({ tripId }: TripActionsProps) {
  const router = useRouter();
  const [busy, setBusy] = useState<'copy' | 'delete' | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const copy = async () => {
    setBusy('copy');
    setError(null);
    try {
      const res = await tripApi(apiClient).copy(tripId);
      router.push(`/trips/${res.trip.trip_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '복사에 실패했습니다.');
      setBusy(null);
    }
  };

  const remove = async () => {
    setBusy('delete');
    setError(null);
    try {
      await tripApi(apiClient).delete(tripId);
      router.push('/trips');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '삭제에 실패했습니다.');
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-col items-end gap-1" data-testid="trip-actions">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => void copy()}
          disabled={busy !== null}
          className="inline-flex h-8 items-center gap-1 rounded-sm border border-hairline bg-white px-2.5 text-xs font-semibold text-ink hover:bg-surface-soft disabled:opacity-50"
        >
          {busy === 'copy' ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <Copy className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          복사
        </button>
        {confirming ? (
          <span className="inline-flex items-center gap-1">
            <button
              type="button"
              onClick={() => void remove()}
              disabled={busy !== null}
              data-testid="trip-delete-confirm"
              className="inline-flex h-8 items-center gap-1 rounded-sm bg-error-text px-2.5 text-xs font-semibold text-white disabled:opacity-50"
            >
              {busy === 'delete' && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
              삭제 확인
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="h-8 rounded-sm border border-hairline px-2.5 text-xs font-semibold text-ink hover:bg-surface-soft"
            >
              취소
            </button>
          </span>
        ) : (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            disabled={busy !== null}
            className="inline-flex h-8 items-center gap-1 rounded-sm border border-hairline bg-white px-2.5 text-xs font-semibold text-muted hover:bg-error-bg hover:text-error-text disabled:opacity-50"
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
            삭제
          </button>
        )}
      </div>
      {error && (
        <p role="alert" className="rounded-sm bg-error-bg px-2 py-1 text-xs text-error-text">
          {error}
        </p>
      )}
    </div>
  );
}
