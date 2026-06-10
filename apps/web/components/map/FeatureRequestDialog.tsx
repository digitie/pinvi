'use client';

import { useState } from 'react';
import { CheckCircle2, Loader2, MapPin } from 'lucide-react';
import { ApiError, featureApi } from '@tripmate/api-client';
import type { FeatureSuggestionKind } from '@tripmate/schemas';
import { apiClient } from '@/lib/api';
import { buildNewPlaceRequest, type NewPlaceForm } from '@/lib/featureRequest';

export interface FeatureRequestDialogProps {
  coord: { lon: number; lat: number };
  onClose: () => void;
  onSubmitted?: () => void;
}

const KINDS: { value: FeatureSuggestionKind; label: string }[] = [
  { value: 'place', label: '장소' },
  { value: 'event', label: '이벤트' },
];

export function FeatureRequestDialog({ coord, onClose, onSubmitted }: FeatureRequestDialogProps) {
  const [form, setForm] = useState<NewPlaceForm>({
    kind: 'place',
    title: '',
    categories: '',
    note: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const update = (patch: Partial<NewPlaceForm>) => setForm((prev) => ({ ...prev, ...patch }));

  const submit = async () => {
    if (!form.title.trim()) {
      setError('이름을 입력하세요.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await featureApi(apiClient).request(buildNewPlaceRequest(form, coord));
      setDone(true);
      onSubmitted?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '제안 등록에 실패했습니다.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="장소 제안"
      data-testid="feature-request-dialog"
    >
      <div className="w-full max-w-md space-y-4 rounded-md border border-hairline bg-white p-5 shadow-lg">
        <h2 className="text-base font-bold text-ink">이 위치 장소 제안</h2>
        <p className="flex items-center gap-1 text-xs text-muted">
          <MapPin className="h-3.5 w-3.5" aria-hidden="true" />
          {coord.lat.toFixed(5)}, {coord.lon.toFixed(5)}
        </p>

        {done ? (
          <div className="space-y-3">
            <p className="flex items-center gap-2 rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text">
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              제안이 접수됐습니다. 관리자 검토 후 반영됩니다.
            </p>
            <div className="flex justify-end">
              <button
                type="button"
                onClick={onClose}
                className="h-9 rounded-sm bg-primary px-4 text-sm font-semibold text-white"
              >
                닫기
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="flex gap-2" role="radiogroup" aria-label="종류">
              {KINDS.map((k) => (
                <button
                  key={k.value}
                  type="button"
                  role="radio"
                  aria-checked={form.kind === k.value}
                  onClick={() => update({ kind: k.value })}
                  className={
                    form.kind === k.value
                      ? 'h-9 flex-1 rounded-sm bg-ink text-sm font-semibold text-white'
                      : 'h-9 flex-1 rounded-sm border border-hairline bg-white text-sm font-semibold text-ink hover:bg-surface-soft'
                  }
                >
                  {k.label}
                </button>
              ))}
            </div>

            <label className="block text-sm font-semibold text-ink">
              이름
              <input
                value={form.title}
                onChange={(event) => update({ title: event.target.value })}
                maxLength={200}
                placeholder="예: 해운대 블루라인파크"
                className="mt-1 h-9 w-full rounded-sm border border-hairline px-2 text-sm font-normal text-ink outline-none focus:border-primary"
              />
            </label>
            <label className="block text-sm font-semibold text-ink">
              카테고리(쉼표 구분, 선택)
              <input
                value={form.categories}
                onChange={(event) => update({ categories: event.target.value })}
                placeholder="카페, 디저트"
                className="mt-1 h-9 w-full rounded-sm border border-hairline px-2 text-sm font-normal text-ink outline-none focus:border-primary"
              />
            </label>
            <label className="block text-sm font-semibold text-ink">
              메모(선택)
              <textarea
                value={form.note}
                onChange={(event) => update({ note: event.target.value })}
                maxLength={2000}
                rows={3}
                className="mt-1 w-full rounded-sm border border-hairline px-2 py-1 text-sm font-normal text-ink outline-none focus:border-primary"
              />
            </label>

            {error && (
              <p className="rounded-sm bg-error-bg px-3 py-2 text-xs text-error-text">{error}</p>
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="h-9 rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
              >
                취소
              </button>
              <button
                type="button"
                onClick={() => void submit()}
                disabled={submitting || !form.title.trim()}
                data-testid="feature-request-submit"
                className="inline-flex h-9 items-center gap-1 rounded-sm bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50"
              >
                {submitting && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                제안하기
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
