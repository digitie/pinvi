'use client';

import { useState } from 'react';
import { ApiError, tripApi } from '@pinvi/api-client';
import type { TripResponse } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';

export function SharedTripEditor({ tripId, token, trip, onSaved }: {
  tripId: string; token: string; trip: TripResponse; onSaved: (trip: TripResponse) => void;
}) {
  const [title, setTitle] = useState(trip.title);
  const [description, setDescription] = useState(trip.description ?? '');
  const [region, setRegion] = useState(trip.region_hint ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  return (
    <form aria-label="공유 여행 정보 편집" className="space-y-3 rounded-sm border border-hairline p-4"
      onSubmit={async (event) => {
        event.preventDefault();
        if (saving) return;
        setSaving(true); setError(null); setSaved(false);
        try {
          const result = await tripApi(apiClient).updateShared(tripId, token, trip.version, {
            title: title.trim(), description, region_hint: region || null,
          });
          onSaved(result); setSaved(true);
        } catch (err) {
          setError(err instanceof ApiError ? err.message : '여행 정보를 저장하지 못했습니다.');
        } finally { setSaving(false); }
      }}>
      <h2 className="font-semibold">여행 정보 편집</h2>
      <p className="text-sm text-muted">로그인 후 여행 제목·설명·지역을 편집할 수 있습니다.</p>
      <label className="block text-sm">여행 제목
        <input required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)}
          className="mt-1 block min-h-11 w-full rounded-sm border border-hairline px-3" />
      </label>
      <label className="block text-sm">여행 설명
        <textarea value={description} onChange={(e) => setDescription(e.target.value)}
          className="mt-1 block w-full rounded-sm border border-hairline p-3" />
      </label>
      <label className="block text-sm">지역
        <input maxLength={120} value={region} onChange={(e) => setRegion(e.target.value)}
          className="mt-1 block min-h-11 w-full rounded-sm border border-hairline px-3" />
      </label>
      <button disabled={saving || !title.trim()} className="focus-ring min-h-11 rounded-sm bg-cta px-4 text-on-primary disabled:opacity-50">
        {saving ? '저장 중…' : '여행 정보 저장'}
      </button>
      {error && <p role="alert">{error}</p>}
      {saved && <p role="status">여행 정보를 저장했습니다.</p>}
    </form>
  );
}
