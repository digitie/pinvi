'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ApiError, tripApi, type TripListPage } from '@pinvi/api-client';
import { apiClient } from '@/lib/api';

export function TripTrash() {
  const [cursor, setCursor] = useState<string | null>(null);
  const [previous, setPrevious] = useState<(string | null)[]>([]);
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<{ key: string; page?: TripListPage; error?: string } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const key = JSON.stringify([cursor, revision]);

  useEffect(() => {
    let cancelled = false;
    tripApi(apiClient).listPage({ bucket: 'all', trashed: true, limit: 20, cursor: cursor ?? undefined })
      .then((page) => { if (!cancelled) setResult({ key, page }); })
      .catch((err) => { if (!cancelled) setResult({ key, error: err instanceof ApiError ? err.message : '휴지통을 불러오지 못했습니다.' }); });
    return () => { cancelled = true; };
  }, [cursor, key]);

  const loading = result?.key !== key;
  const page = !loading ? result?.page : undefined;
  return <section className="space-y-5">
    <header className="space-y-2">
      <h1 className="text-2xl font-bold text-ink">여행 휴지통</h1>
      <p className="text-sm text-muted">삭제한 여행은 30일 동안 초안으로 복원할 수 있습니다. 기한 이후 정리 작업에서 영구 삭제됩니다. 복원하면 기존 공개 범위와 아직 유효한 공유 링크도 다시 적용됩니다.</p>
      <p className="text-sm text-muted">휴지통의 첨부도 저장 용량에 포함됩니다. 복원해도 사용 용량은 늘어나지 않습니다.</p>
      <Link href="/trips" className="focus-ring inline-flex min-h-11 items-center underline">내 여행으로</Link>
    </header>
    {feedback && <p role="status" className="text-sm text-success-text">{feedback}</p>}
    {actionError && <p role="alert" className="text-sm text-error-text">{actionError}</p>}
    {loading ? <p role="status">휴지통을 불러오는 중…</p>
      : result?.error ? <div role="alert"><p>{result.error}</p><button type="button" onClick={() => setRevision((v) => v + 1)} className="focus-ring min-h-11 underline">다시 시도</button></div>
      : !page?.items.length ? <p>휴지통에 여행이 없습니다.</p>
      : <ul className="divide-y divide-hairline">
        {page.items.map((trip) => <li key={trip.trip_id} className="flex flex-wrap items-center justify-between gap-3 py-4">
          <div><h2 className="font-semibold">{trip.title}</h2>{trip.trash_expires_at && <p className="text-sm text-muted">{trip.can_restore === false ? "보관 기한 만료 또는 정리 중 · 복원 불가" : new Date(trip.trash_expires_at).toLocaleString("ko-KR") + "까지 복원 가능"}</p>}<p className="text-sm text-muted">{trip.start_date ?? '날짜 미정'}{trip.end_date ? ` ~ ${trip.end_date}` : ''}</p></div>
          <button type="button" aria-label={`${trip.title} 복원`} disabled={busyId != null || trip.can_restore === false}
            className="focus-ring min-h-11 rounded-sm border border-hairline px-4 disabled:opacity-50"
            onClick={async () => {
              if (busyId) return;
              setBusyId(trip.trip_id); setFeedback(null); setActionError(null);
              try {
                await tripApi(apiClient).restore(trip.trip_id);
                setFeedback(`"${trip.title}" 여행을 초안으로 복원했습니다.`);
                setCursor(null); setPrevious([]); setRevision((v) => v + 1);
              } catch (err) {
                setActionError(err instanceof ApiError ? err.message : '여행을 복원하지 못했습니다.');
              } finally { setBusyId(null); }
            }}>{busyId === trip.trip_id ? '복원 중…' : '복원'}</button>
        </li>)}
      </ul>}
    <nav aria-label="휴지통 페이지" className="flex gap-3">
      <button type="button" disabled={!previous.length || loading || busyId != null} className="focus-ring min-h-11 px-3 disabled:opacity-50"
        onClick={() => { const pages = [...previous]; setCursor(pages.pop() ?? null); setPrevious(pages); }}>이전</button>
      <button type="button" disabled={!page?.has_more || !page.cursor || loading || busyId != null} className="focus-ring min-h-11 px-3 disabled:opacity-50"
        onClick={() => { if (page?.cursor) { setPrevious((v) => [...v, cursor]); setCursor(page.cursor); } }}>다음</button>
    </nav>
  </section>;
}
