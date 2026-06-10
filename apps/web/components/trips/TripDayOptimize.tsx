'use client';

import { useState } from 'react';
import { AlertTriangle, Loader2, Route } from 'lucide-react';
import { ApiError, tripApi } from '@tripmate/api-client';
import type { TripDayOptimizeResponse } from '@tripmate/schemas';
import { apiClient } from '@/lib/api';
import { formatDistanceMeters } from '@/lib/distance';

export interface TripDayOptimizeProps {
  tripId: string;
  dayIndex: number;
  poiCount: number;
  onApplied: () => void | Promise<unknown>;
}

export function TripDayOptimize({ tripId, dayIndex, poiCount, onApplied }: TripDayOptimizeProps) {
  const [preview, setPreview] = useState<TripDayOptimizeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (poiCount < 2) return null;

  const runPreview = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await tripApi(apiClient).optimizeDay(tripId, dayIndex, {
        strategy: 'nearest_neighbor',
        persist: false,
      });
      setPreview(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '동선 계산에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const apply = async () => {
    setApplying(true);
    setError(null);
    try {
      await tripApi(apiClient).optimizeDay(tripId, dayIndex, {
        strategy: 'nearest_neighbor',
        persist: true,
      });
      setPreview(null);
      await onApplied();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '적용에 실패했습니다.');
    } finally {
      setApplying(false);
    }
  };

  return (
    <div className="space-y-2" data-testid="trip-day-optimize">
      <button
        type="button"
        onClick={() => void runPreview()}
        disabled={loading}
        className="inline-flex h-9 items-center gap-1 rounded-sm border border-hairline bg-white px-3 text-sm font-semibold text-ink hover:bg-surface-soft disabled:opacity-50"
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        ) : (
          <Route className="h-4 w-4" aria-hidden="true" />
        )}
        동선 최적화
      </button>

      {error && <p className="rounded-sm bg-error-bg px-3 py-2 text-xs text-error-text">{error}</p>}

      {preview && (
        <div className="space-y-2 rounded-sm border border-hairline bg-surface-soft p-3 text-sm">
          <p className="text-ink">
            최단 경로 추정 거리 <strong>{formatDistanceMeters(preview.distance_meters)}</strong> ·
            순서 변경 {preview.moves.length}곳
          </p>
          {preview.warnings.length > 0 && (
            <p className="flex items-start gap-1 text-xs text-error-text">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {preview.warnings.join(' · ')}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setPreview(null)}
              className="h-8 rounded-sm border border-hairline px-3 text-xs font-semibold text-ink hover:bg-white"
            >
              닫기
            </button>
            <button
              type="button"
              onClick={() => void apply()}
              disabled={applying || preview.moves.length === 0}
              className="inline-flex h-8 items-center gap-1 rounded-sm bg-primary px-3 text-xs font-semibold text-white disabled:opacity-50"
            >
              {applying && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
              적용
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
