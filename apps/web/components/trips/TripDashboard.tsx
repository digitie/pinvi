'use client';

import { useEffect, useMemo, useState } from 'react';
import { CalendarDays, Loader2, MapPin, Plus, RefreshCw } from 'lucide-react';
import { ApiError, tripApi, type TripBucket } from '@tripmate/api-client';
import type { TripCreate, TripResponse, TripStatus } from '@tripmate/schemas';
import { apiClient } from '@/lib/api';

const STATUS_LABEL: Record<TripStatus, string> = {
  draft: '초안',
  planned: '예정',
  in_progress: '진행 중',
  completed: '완료',
  archived: '보관',
};

const BUCKETS: { value: TripBucket; label: string }[] = [
  { value: 'all', label: '전체' },
  { value: 'future', label: '예정' },
  { value: 'past', label: '지난 여행' },
];

function formatDate(value: string | null): string {
  if (!value) {
    return '미정';
  }
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(new Date(value));
}

function isPastTrip(trip: TripResponse): boolean {
  if (!trip.end_date) {
    return false;
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return new Date(`${trip.end_date}T00:00:00`) < today;
}

function visibleTrips(trips: TripResponse[], bucket: TripBucket): TripResponse[] {
  if (bucket === 'all') {
    return trips;
  }
  return trips.filter((trip) => (bucket === 'past' ? isPastTrip(trip) : !isPastTrip(trip)));
}

export function TripDashboard() {
  const [trips, setTrips] = useState<TripResponse[]>([]);
  const [bucket, setBucket] = useState<TripBucket>('all');
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState('');
  const [regionHint, setRegionHint] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const filteredTrips = useMemo(() => visibleTrips(trips, bucket), [bucket, trips]);
  const upcomingCount = useMemo(() => trips.filter((trip) => !isPastTrip(trip)).length, [trips]);
  const draftCount = useMemo(() => trips.filter((trip) => trip.status === 'draft').length, [trips]);

  const loadTrips = async () => {
    setLoading(true);
    setError(null);
    try {
      const items = await tripApi(apiClient).list({ limit: 50 });
      setTrips(items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '여행 목록을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadTrips();
  }, []);

  const onCreate = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      setError('여행 제목을 입력하세요.');
      return;
    }
    setCreating(true);
    setError(null);
    setMessage(null);
    const body: TripCreate = {
      title: trimmedTitle,
      description: null,
      region_hint: regionHint.trim() || null,
      start_date: startDate || null,
      end_date: endDate || null,
      visibility: 'private',
      companions: [],
    };
    try {
      const created = await tripApi(apiClient).create(body);
      setTrips((current) => [created, ...current]);
      setTitle('');
      setRegionHint('');
      setStartDate('');
      setEndDate('');
      setMessage('새 여행을 만들었습니다.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '여행을 만들지 못했습니다.');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-3 border-b border-hairline pb-5 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-normal text-primary">Trips</p>
          <h1 className="mt-1 text-2xl font-bold text-ink md:text-3xl">여행</h1>
        </div>
        <button
          type="button"
          onClick={() => void loadTrips()}
          className="inline-flex h-10 w-fit items-center gap-2 rounded-sm border border-hairline bg-white px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
          disabled={loading}
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          )}
          새로고침
        </button>
      </header>

      <section className="grid grid-cols-1 gap-3 md:grid-cols-3" aria-label="여행 요약">
        <div className="rounded-sm border border-hairline bg-white p-4">
          <p className="text-xs font-semibold uppercase tracking-normal text-muted">전체</p>
          <p className="mt-2 text-2xl font-bold text-ink">{trips.length}</p>
        </div>
        <div className="rounded-sm border border-hairline bg-white p-4">
          <p className="text-xs font-semibold uppercase tracking-normal text-muted">예정</p>
          <p className="mt-2 text-2xl font-bold text-ink">{upcomingCount}</p>
        </div>
        <div className="rounded-sm border border-hairline bg-white p-4">
          <p className="text-xs font-semibold uppercase tracking-normal text-muted">초안</p>
          <p className="mt-2 text-2xl font-bold text-ink">{draftCount}</p>
        </div>
      </section>

      {message && (
        <p className="rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text">{message}</p>
      )}
      {error && (
        <p
          className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text"
          data-testid="trips-error"
        >
          {error}
        </p>
      )}

      <section className="rounded-sm border border-hairline bg-white p-4">
        <form onSubmit={onCreate} className="grid gap-3 md:grid-cols-[1.5fr_1fr_1fr_1fr_auto]">
          <label className="space-y-1 text-sm font-semibold text-ink">
            제목
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className="h-10 w-full rounded-sm border border-hairline px-3 text-sm font-normal text-ink outline-none focus:border-primary"
              maxLength={200}
              placeholder="부산 2박 3일"
            />
          </label>
          <label className="space-y-1 text-sm font-semibold text-ink">
            지역
            <input
              value={regionHint}
              onChange={(event) => setRegionHint(event.target.value)}
              className="h-10 w-full rounded-sm border border-hairline px-3 text-sm font-normal text-ink outline-none focus:border-primary"
              maxLength={120}
              placeholder="부산"
            />
          </label>
          <label className="space-y-1 text-sm font-semibold text-ink">
            시작일
            <input
              type="date"
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
              className="h-10 w-full rounded-sm border border-hairline px-3 text-sm font-normal text-ink outline-none focus:border-primary"
            />
          </label>
          <label className="space-y-1 text-sm font-semibold text-ink">
            종료일
            <input
              type="date"
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
              className="h-10 w-full rounded-sm border border-hairline px-3 text-sm font-normal text-ink outline-none focus:border-primary"
            />
          </label>
          <button
            type="submit"
            className="mt-6 inline-flex h-10 items-center justify-center gap-2 rounded-sm bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50 md:mt-auto"
            disabled={creating}
            data-testid="trip-create-submit"
          >
            {creating ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Plus className="h-4 w-4" aria-hidden="true" />
            )}
            만들기
          </button>
        </form>
      </section>

      <section className="space-y-4">
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="여행 필터">
          {BUCKETS.map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => setBucket(item.value)}
              className={
                bucket === item.value
                  ? 'h-10 rounded-sm bg-ink px-4 text-sm font-semibold text-white'
                  : 'h-10 rounded-sm border border-hairline bg-white px-4 text-sm font-semibold text-ink hover:bg-surface-soft'
              }
              role="tab"
              aria-selected={bucket === item.value}
            >
              {item.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="flex min-h-48 items-center justify-center rounded-sm border border-hairline bg-white text-sm text-muted">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
            불러오는 중...
          </div>
        ) : filteredTrips.length === 0 ? (
          <div className="flex min-h-48 flex-col items-center justify-center rounded-sm border border-hairline bg-white px-4 text-center">
            <CalendarDays className="h-8 w-8 text-muted" aria-hidden="true" />
            <p className="mt-3 text-sm font-semibold text-ink">표시할 여행이 없습니다.</p>
            <p className="mt-1 text-xs text-muted">첫 여행을 만들면 이곳에 나타납니다.</p>
          </div>
        ) : (
          <div
            className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3"
            data-testid="trip-list"
          >
            {filteredTrips.map((trip) => (
              <article
                key={trip.trip_id}
                className="rounded-sm border border-hairline bg-white p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="truncate text-lg font-bold text-ink">{trip.title}</h2>
                    <p className="mt-1 flex items-center gap-1 text-sm text-muted">
                      <MapPin className="h-4 w-4 shrink-0" aria-hidden="true" />
                      <span className="truncate">
                        {trip.region_hint ?? trip.primary_region_code ?? '지역 미정'}
                      </span>
                    </p>
                  </div>
                  <span className="shrink-0 rounded-sm bg-surface-soft px-2 py-1 text-xs font-semibold text-muted">
                    {STATUS_LABEL[trip.status]}
                  </span>
                </div>
                <p className="mt-4 text-sm text-body">
                  {formatDate(trip.start_date)} - {formatDate(trip.end_date)}
                </p>
                {trip.description && (
                  <p className="mt-2 line-clamp-2 text-sm text-muted">{trip.description}</p>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
