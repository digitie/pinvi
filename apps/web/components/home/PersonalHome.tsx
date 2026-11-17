'use client';

import { buttonClassName } from '@/components/ui/button-styles';
import { apiClient } from '@/lib/api';
import { SIDO_TOTAL, nextTripBadge } from '@/lib/personalHome';
import { formatTripDate, formatTripDateRange } from '@/lib/tripDateLabels';
import { userApi } from '@pinvi/api-client';
import type { HomeTripCard, HomeVisitedPlace, UserHome } from '@pinvi/schemas';
import { CalendarDays, ChevronRight, MapPin } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';

/* Hallmark · genre: modern-minimal · macrostructure: Workbench(app) · design-system: DESIGN.md · designed-as-app
 * 참조: Google 지도 '내 장소/타임라인', 네이버·카카오맵 'MY' — 다음 여행 1장 → 통계 열 → 목록(예정·최근·장소·지역).
 * stat: rating-display-card의 ink 통계 열(큰 숫자 + 작은 라벨, 카드 4장 금지) · accent: 다음 여행 D-day 1곳만 Rausch
 * state: 로딩=skeleton · 오류=원인+다시 시도(role=alert) · 빈 상태=첫 여행 만들기
 */

function tripDates(trip: Pick<HomeTripCard, 'start_date' | 'end_date'>): string {
  if (!trip.start_date) return '날짜 미정';
  if (!trip.end_date || trip.end_date === trip.start_date) return formatTripDate(trip.start_date);
  return formatTripDateRange(trip.start_date, trip.end_date);
}

function tripMeta(trip: HomeTripCard): string {
  const region = trip.region_name ?? trip.region_hint;
  return [tripDates(trip), region, `장소 ${trip.place_count}곳`].filter(Boolean).join(' · ');
}

export function PersonalHome() {
  // 결과를 요청 차수(revision)에 묶는다 — effect 안에서 동기 setState 없이 로딩·재시도를 파생한다.
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<{ revision: number; home?: UserHome } | null>(null);

  useEffect(() => {
    let cancelled = false;
    userApi(apiClient)
      .getHome()
      .then(
        (home) => {
          if (!cancelled) setResult({ revision, home });
        },
        () => {
          // 401은 apiClient가 로그인 화면으로 보낸다(onUnauthorized). 나머지는 원인 + 다시 시도.
          if (!cancelled) setResult({ revision });
        },
      );
    return () => {
      cancelled = true;
    };
  }, [revision]);

  const settled = result?.revision === revision;
  const home = settled ? (result?.home ?? null) : null;
  const error = settled && !result?.home;

  return (
    <div className="mx-auto w-full max-w-3xl space-y-8 pb-6" data-testid="personal-home">
      <header className="flex items-end justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight text-ink">내 여행</h1>
        <Link
          href="/trips"
          className="focus-ring inline-flex min-h-11 items-center gap-1 rounded-sm text-sm font-semibold text-muted hover:text-ink"
          data-testid="home-all-trips"
        >
          모든 여행
          <ChevronRight className="size-4" aria-hidden="true" />
        </Link>
      </header>

      {error ? (
        <div
          role="alert"
          className="rounded-sm border border-hairline bg-canvas p-4"
          data-testid="home-error"
        >
          <p className="text-sm font-semibold text-ink">홈을 불러오지 못했습니다.</p>
          <p className="mt-1 text-sm text-muted">
            네트워크나 서버 상태를 확인한 뒤 다시 시도해 주세요.
          </p>
          <button
            type="button"
            onClick={() => setRevision((value) => value + 1)}
            className={buttonClassName({ variant: 'secondary', className: 'mt-3' })}
          >
            다시 시도
          </button>
        </div>
      ) : home == null ? (
        <HomeSkeleton />
      ) : (
        <HomeBody home={home} />
      )}
    </div>
  );
}

function HomeSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" aria-live="polite" data-testid="home-loading">
      <span className="sr-only">홈을 불러오는 중…</span>
      <div className="h-28 animate-pulse rounded-sm border border-hairline bg-surface-soft" />
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[0, 1, 2, 3].map((cell) => (
          <div key={cell} className="h-14 animate-pulse rounded-sm bg-surface-soft" />
        ))}
      </div>
    </div>
  );
}

function HomeBody({ home }: { home: UserHome }) {
  const { stats } = home;
  const empty = stats.trip_count === 0;
  return (
    <>
      {home.next_trip ? (
        <NextTrip trip={home.next_trip} />
      ) : (
        <section
          className="rounded-sm border border-hairline bg-canvas p-5"
          data-testid="home-next-trip-empty"
        >
          <p className="text-sm font-semibold text-ink">
            {empty ? '아직 여행이 없습니다.' : '예정된 여행이 없습니다.'}
          </p>
          <p className="mt-1 text-sm text-muted">
            지도에서 장소를 고르고 일자에 담아 다음 여행을 계획해 보세요.
          </p>
          <Link
            href="/trips"
            className={buttonClassName({ variant: 'secondary', className: 'mt-4' })}
          >
            새 여행 만들기
          </Link>
        </section>
      )}

      <section aria-labelledby="home-stats-heading" data-testid="home-stats">
        <h2 id="home-stats-heading" className="sr-only">
          여행 통계
        </h2>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-5 border-y border-hairline py-5 sm:grid-cols-4">
          <Stat
            testId="home-stat-trips"
            label="다녀온 여행"
            value={stats.completed_trip_count}
            unit="번"
          />
          <Stat
            testId="home-stat-days"
            label="여행한 날"
            value={stats.travel_day_count}
            unit="일"
          />
          <Stat
            testId="home-stat-places"
            label="다녀온 장소"
            value={stats.visited_place_count}
            unit="곳"
          />
          <Stat
            testId="home-stat-regions"
            label="다녀온 지역"
            value={stats.region_count}
            unit={`/${SIDO_TOTAL}`}
          />
        </dl>
        <p className="mt-2 text-sm text-muted" data-testid="home-stat-summary">
          {`전체 여행 ${stats.trip_count}개 · 예정 ${stats.upcoming_trip_count + stats.ongoing_trip_count}개 · 날짜 미정 ${stats.undated_trip_count}개`}
        </p>
      </section>

      {home.regions.length > 0 ? (
        <section aria-labelledby="home-regions-heading" data-testid="home-regions">
          <h2 id="home-regions-heading" className="text-base font-semibold text-ink">
            다녀온 지역
          </h2>
          <ul className="m-0 mt-3 flex list-none flex-wrap gap-2 p-0">
            {home.regions.map((region) => (
              <li
                key={region.code}
                className="inline-flex min-h-9 items-center gap-2 rounded-full border border-hairline px-3 text-sm text-ink"
              >
                <span className="font-semibold">{region.name}</span>
                <span className="text-muted tabular-nums">
                  {region.place_count > 0 ? `${region.place_count}곳` : `여행 ${region.trip_count}`}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <TripList
        id="home-upcoming"
        title="계획 중인 여행"
        trips={home.upcoming_trips}
        emptyText={null}
      />
      <TripList
        id="home-recent"
        title="최근 다녀온 여행"
        trips={home.recent_trips}
        emptyText={empty ? null : '여행 날짜가 지나면 다녀온 여행으로 모입니다.'}
      />
      <PlaceList places={home.recent_places} />
    </>
  );
}

function NextTrip({ trip }: { trip: HomeTripCard }) {
  const badge = nextTripBadge(trip);
  return (
    <section aria-labelledby="home-next-trip-heading" data-testid="home-next-trip">
      <h2 id="home-next-trip-heading" className="sr-only">
        {trip.phase === 'ongoing' ? '지금 여행 중' : '다음 여행'}
      </h2>
      <Link
        href={`/trips/${trip.trip_id}`}
        className="focus-ring block rounded-sm border border-hairline bg-canvas p-5 hover:shadow-card"
      >
        <p className="m-0 flex items-center gap-2 text-sm font-semibold text-muted">
          <CalendarDays className="size-4" aria-hidden="true" />
          {trip.phase === 'ongoing' ? '지금 여행 중' : '다음 여행'}
          {badge ? (
            <span
              className="ml-auto rounded-full bg-primary px-2.5 py-0.5 text-sm font-semibold text-on-primary tabular-nums"
              data-testid="home-next-trip-badge"
            >
              {badge}
            </span>
          ) : null}
        </p>
        <p className="mt-2 text-xl font-bold tracking-tight text-ink">{trip.title}</p>
        <p className="mt-1 text-sm text-body">{tripMeta(trip)}</p>
      </Link>
    </section>
  );
}

function Stat({
  label,
  value,
  unit,
  testId,
}: {
  label: string;
  value: number;
  unit: string;
  testId: string;
}) {
  return (
    <div data-testid={testId}>
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="m-0 mt-1 flex items-baseline gap-0.5 text-ink">
        <span className="text-3xl font-bold leading-none tracking-tight tabular-nums">{value}</span>
        <span className="text-sm font-semibold text-muted">{unit}</span>
      </dd>
    </div>
  );
}

function TripList({
  id,
  title,
  trips,
  emptyText,
}: {
  id: string;
  title: string;
  trips: HomeTripCard[];
  emptyText: string | null;
}) {
  if (trips.length === 0 && emptyText == null) return null;
  return (
    <section aria-labelledby={`${id}-heading`} data-testid={id}>
      <h2 id={`${id}-heading`} className="text-base font-semibold text-ink">
        {title}
      </h2>
      {trips.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{emptyText}</p>
      ) : (
        <ul className="m-0 mt-2 list-none divide-y divide-hairline p-0">
          {trips.map((trip) => (
            <li key={trip.trip_id}>
              <Link
                href={`/trips/${trip.trip_id}`}
                className="focus-ring flex min-h-14 items-center gap-3 rounded-sm py-2 hover:bg-surface-soft"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold text-ink">{trip.title}</span>
                  <span className="block truncate text-sm text-muted">{tripMeta(trip)}</span>
                </span>
                {trip.phase === 'upcoming' && trip.days_until != null ? (
                  <span className="shrink-0 text-sm font-semibold text-ink tabular-nums">
                    {nextTripBadge(trip)}
                  </span>
                ) : null}
                <ChevronRight className="size-4 shrink-0 text-muted" aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function PlaceList({ places }: { places: HomeVisitedPlace[] }) {
  if (places.length === 0) return null;
  return (
    <section aria-labelledby="home-places-heading" data-testid="home-places">
      <h2 id="home-places-heading" className="text-base font-semibold text-ink">
        최근 다녀온 장소
      </h2>
      <ul className="m-0 mt-2 list-none divide-y divide-hairline p-0">
        {places.map((place) => (
          <li key={place.poi_id}>
            <Link
              href={`/trips/${place.trip_id}`}
              className="focus-ring flex min-h-14 items-center gap-3 rounded-sm py-2 hover:bg-surface-soft"
            >
              <MapPin className="size-4 shrink-0 text-muted" aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-semibold text-ink">{place.name}</span>
                <span className="block truncate text-sm text-muted">
                  {[formatTripDate(place.visited_on), place.region_name, place.trip_title]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
