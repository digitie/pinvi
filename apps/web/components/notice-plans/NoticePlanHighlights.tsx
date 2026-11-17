'use client';

import type { AddablePlace } from '@/components/notice-plans/AddPlaceToTripDialog';
import { apiClient } from '@/lib/api';
import { formatEventPeriod, formatNearDistance } from '@/lib/noticePlanHighlights';
import { ApiError, noticePlanApi } from '@pinvi/api-client';
import type {
  NoticePlanCuratedPick,
  NoticePlanEventPick,
  NoticePlanHighlightsResponse,
} from '@pinvi/schemas';
import { CalendarDays, ExternalLink, Plus, Sparkles } from 'lucide-react';
import { useCallback, useEffect, useState, type ReactNode } from 'react';

/* Hallmark · genre: modern-minimal · design-system: DESIGN.md
 * 추천 여행 카드 안에서 펼치는 보조 정보: 기간 중 축제·행사 + 주변 큐레이션 장소(kor-travel-map).
 * 목록은 처음 3건만 보이고 나머지는 '더 보기'로 펼친다. 상태: skeleton · 구역별 불러오기 실패 · 빈 상태.
 */

const VISIBLE_DEFAULT = 3;

const STATUS_LABEL: Record<NoticePlanEventPick['status'], string | null> = {
  ongoing: '진행 중',
  scheduled: '예정',
  ended: null,
  unknown: null,
};

function eventToPlace(event: NoticePlanEventPick): AddablePlace | null {
  if (event.lon == null || event.lat == null) return null;
  return {
    feature_id: event.feature_id,
    name: event.name,
    kind: 'event',
    category: null,
    lon: event.lon,
    lat: event.lat,
    marker_color: event.marker_color,
    marker_icon: event.marker_icon,
    preferred_date: event.start_date,
  };
}

function curatedToPlace(pick: NoticePlanCuratedPick): AddablePlace | null {
  if (pick.lon == null || pick.lat == null) return null;
  return {
    feature_id: pick.feature_id,
    name: pick.name,
    kind: pick.kind,
    category: pick.category,
    lon: pick.lon,
    lat: pick.lat,
  };
}

export interface NoticePlanHighlightsProps {
  planId: string;
  onAddPlace: (place: AddablePlace) => void;
}

export function NoticePlanHighlights({ planId, onAddPlace }: NoticePlanHighlightsProps) {
  const [data, setData] = useState<NoticePlanHighlightsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    noticePlanApi(apiClient)
      .highlights(planId, { signal: controller.signal })
      .then((loaded) => setData(loaded))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof ApiError ? err.message : '주변 정보를 불러오지 못했습니다.');
      });
    return () => controller.abort();
  }, [planId, attempt]);

  const retry = useCallback(() => {
    setError(null);
    setData(null);
    setAttempt((value) => value + 1);
  }, []);

  if (error) {
    return (
      <div className="mt-3 rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text" role="alert">
        {error}{' '}
        <button type="button" onClick={retry} className="focus-ring font-semibold underline">
          다시 시도
        </button>
      </div>
    );
  }

  if (data == null) {
    return (
      <div className="mt-3 space-y-2" aria-busy="true" aria-live="polite">
        <span className="sr-only">주변 축제와 큐레이션을 불러오는 중…</span>
        {[0, 1, 2].map((row) => (
          <div key={row} className="h-10 animate-pulse rounded-sm bg-surface-soft" />
        ))}
      </div>
    );
  }

  const periodLabel =
    data.window_basis === 'plan'
      ? `여행 기간(${formatEventPeriod(data.window_start, data.window_end)})`
      : `앞으로 30일(${formatEventPeriod(data.window_start, data.window_end)})`;
  const regionLabel = data.region_scope === 'sido' ? '같은 시도' : '전국';

  return (
    <div className="mt-3 space-y-4" data-testid={`notice-plan-highlights-${planId}`}>
      <HighlightSection
        testId="notice-plan-events"
        icon={<CalendarDays className="h-4 w-4" aria-hidden="true" />}
        title="기간 중 축제·행사"
        caption={`${periodLabel} · ${regionLabel}`}
        unavailable={data.unavailable.includes('events')}
        emptyText="이 기간에 열리는 축제·행사가 없습니다."
        items={data.events.map((event) => (
          <EventRow key={event.feature_id} event={event} onAddPlace={onAddPlace} />
        ))}
      />
      <HighlightSection
        testId="notice-plan-curated"
        icon={<Sparkles className="h-4 w-4" aria-hidden="true" />}
        title="주변 큐레이션 장소"
        caption="일정 장소 근처의 공개 큐레이션"
        unavailable={data.unavailable.includes('curated')}
        emptyText="근처에 큐레이션 장소가 없습니다."
        items={data.curated.map((pick) => (
          <CuratedRow key={pick.feature_id} pick={pick} onAddPlace={onAddPlace} />
        ))}
      />
    </div>
  );
}

function HighlightSection({
  testId,
  icon,
  title,
  caption,
  unavailable,
  emptyText,
  items,
}: {
  testId: string;
  icon: ReactNode;
  title: string;
  caption: string;
  unavailable: boolean;
  emptyText: string;
  items: ReactNode[];
}) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? items : items.slice(0, VISIBLE_DEFAULT);
  const hidden = items.length - VISIBLE_DEFAULT;
  return (
    <section data-testid={testId} aria-label={title}>
      <h3 className="flex items-center gap-1 text-sm font-semibold text-ink">
        {icon}
        {title}
      </h3>
      <p className="mt-0.5 text-xs text-muted">{caption}</p>
      {unavailable ? (
        <p className="mt-2 rounded-sm bg-surface-soft px-3 py-2 text-sm text-muted">
          지금은 불러올 수 없습니다. 잠시 뒤 다시 열어 주세요.
        </p>
      ) : items.length === 0 ? (
        <p className="mt-2 rounded-sm bg-surface-soft px-3 py-2 text-sm text-muted">{emptyText}</p>
      ) : (
        <>
          <ul className="mt-2 divide-y divide-hairline">{visible}</ul>
          {hidden > 0 ? (
            <button
              type="button"
              onClick={() => setExpanded((value) => !value)}
              aria-expanded={expanded}
              className="focus-ring mt-1 min-h-11 text-sm font-semibold text-ink underline-offset-2 hover:underline"
            >
              {expanded ? '접기' : `${hidden}곳 더 보기`}
            </button>
          ) : null}
        </>
      )}
    </section>
  );
}

function AddButton({ place, name, onAddPlace }: {
  place: AddablePlace | null;
  name: string;
  onAddPlace: (place: AddablePlace) => void;
}) {
  if (place == null) return null;
  return (
    <button
      type="button"
      onClick={() => onAddPlace(place)}
      aria-label={`${name} 내 여행에 추가`}
      className="focus-ring inline-flex min-h-11 shrink-0 items-center gap-1 rounded-sm border border-hairline bg-canvas px-2 text-xs font-semibold text-ink hover:bg-surface-soft"
    >
      <Plus className="h-4 w-4" aria-hidden="true" />
      추가
    </button>
  );
}

function EventRow({
  event,
  onAddPlace,
}: {
  event: NoticePlanEventPick;
  onAddPlace: (place: AddablePlace) => void;
}) {
  const status = STATUS_LABEL[event.status];
  const place = event.venue_name ?? event.address;
  const distance = formatNearDistance(event.distance_m);
  return (
    <li className="flex items-start justify-between gap-3 py-2">
      <div className="min-w-0">
        <p className="text-sm font-semibold text-ink">
          {event.name}
          {status ? (
            <span className="ml-2 rounded-sm bg-surface-soft px-1.5 py-0.5 text-xs font-medium text-muted">
              {status}
            </span>
          ) : null}
        </p>
        <p className="mt-0.5 text-xs text-muted">
          {formatEventPeriod(event.start_date, event.end_date)}
          {place ? ` · ${place}` : ''}
          {distance ? ` · ${distance}` : ''}
        </p>
        {event.summary ? (
          <p className="mt-1 line-clamp-2 text-xs text-body">{event.summary}</p>
        ) : null}
        {event.homepage_url ? (
          <a
            href={event.homepage_url}
            target="_blank"
            rel="noopener noreferrer"
            className="focus-ring mt-1 inline-flex items-center gap-1 text-xs font-semibold text-ink underline"
          >
            홈페이지
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </a>
        ) : null}
      </div>
      <AddButton place={eventToPlace(event)} name={event.name} onAddPlace={onAddPlace} />
    </li>
  );
}

function CuratedRow({
  pick,
  onAddPlace,
}: {
  pick: NoticePlanCuratedPick;
  onAddPlace: (place: AddablePlace) => void;
}) {
  const distance = formatNearDistance(pick.distance_m);
  const summary = pick.themes.find((theme) => theme.summary)?.summary ?? null;
  return (
    <li className="flex items-start justify-between gap-3 py-2">
      <div className="min-w-0">
        <p className="text-sm font-semibold text-ink">{pick.name}</p>
        <p className="mt-0.5 flex flex-wrap gap-1">
          {pick.themes.map((theme) => (
            <span
              key={`${theme.collection_title}:${theme.edition_key}`}
              className="rounded-sm bg-surface-soft px-1.5 py-0.5 text-xs font-medium text-muted"
            >
              {theme.collection_title}
              {theme.edition_key ? ` ${theme.edition_key}` : ''}
            </span>
          ))}
        </p>
        <p className="mt-0.5 text-xs text-muted">
          {pick.address ?? '주소 미상'}
          {distance ? ` · ${distance}` : ''}
        </p>
        {summary ? <p className="mt-1 line-clamp-2 text-xs text-body">{summary}</p> : null}
      </div>
      <AddButton place={curatedToPlace(pick)} name={pick.name} onAddPlace={onAddPlace} />
    </li>
  );
}
