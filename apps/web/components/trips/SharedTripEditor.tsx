'use client';

import { useState } from 'react';
import { ApiError, tripApi } from '@pinvi/api-client';
import type { TripResponse } from '@pinvi/schemas';
import { sharedApiClient } from '@/lib/api';

export function SharedTripEditor({ tripId, token, trip, onSaved }: {
  tripId: string; token: string; trip: TripResponse; onSaved: (trip: TripResponse) => void;
}) {
  const [title, setTitle] = useState(trip.title);
  const [description, setDescription] = useState(trip.description ?? '');
  const [region, setRegion] = useState(trip.region_hint ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [saved, setSaved] = useState(false);
  return (
    <form aria-label="공유 여행 정보 편집" className="space-y-3 rounded-sm border border-hairline p-4"
      onSubmit={async (event) => {
        event.preventDefault();
        if (saving) return;
        setSaving(true); setError(null); setSaved(false); setConflict(false);
        try {
          const result = await tripApi(sharedApiClient).updateShared(tripId, token, trip.version, {
            title: title.trim(), description, region_hint: region || null,
          });
          onSaved(result); setSaved(true);
        } catch (err) {
          setError(err instanceof ApiError ? err.message : '여행 정보를 저장하지 못했습니다.');
          setConflict(err instanceof ApiError && err.status === 409);
        } finally { setSaving(false); }
      }}>
      <h2 className="font-semibold">여행 정보 편집</h2>
      <p className="text-sm text-muted">
        여행 제목·설명·지역을 편집할 수 있습니다.
        로그인이 필요하면 <a className="focus-ring underline" target="_blank" rel="noopener noreferrer"
          href={`/login?next=${encodeURIComponent(`/shared/${tripId}/${token}`)}`}>새 탭에서 로그인</a>한 뒤
        이 화면에서 다시 저장해 주세요. 입력은 유지됩니다.
      </p>
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
      {conflict && (
        <div className="space-y-2">
          <p className="text-sm">다른 사람이 수정했습니다. 최신 정보를 불러오면 입력 중인 내용이 바뀝니다.</p>
          <button type="button" disabled={saving} className="focus-ring min-h-11 border px-3"
            onClick={async () => {
              if (saving) return;
              setSaving(true);
              try {
                const view = await tripApi(sharedApiClient).getShared(tripId, token);
                onSaved(view.trip);
                setTitle(view.trip.title); setDescription(view.trip.description ?? '');
                setRegion(view.trip.region_hint ?? ''); setConflict(false); setError(null);
              } catch (err) {
                setError(err instanceof ApiError ? err.message : '최신 정보를 불러오지 못했습니다.');
              } finally { setSaving(false); }
            }}>최신 정보 불러오기</button>
        </div>
      )}
      {saved && <p role="status">여행 정보를 저장했습니다.</p>}
    </form>
  );
}
