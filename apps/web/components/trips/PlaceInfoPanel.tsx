'use client';

import { PoiWeatherBadge } from '@/components/weather/WeatherBadge';
import { WeatherForecastBody } from '@/components/weather/WeatherForecastPopup';
import { apiClient } from '@/lib/api';
import { buildMapLinks, openMapLink, type MapLink } from '@/lib/mapLinks';
import { useMinuteNow, usePoiWeather } from '@/lib/usePoiWeather';
import { activeAlerts, kstDateKey } from '@/lib/weatherNow';
import { ApiError, poiApi } from '@pinvi/api-client';
import { featureResolutionNotice } from '@pinvi/domain';
import type { PoiPlaceDetails, TripViewPoi } from '@pinvi/schemas';
import {
  AlertTriangle,
  ChevronDown,
  Clock,
  CloudSun,
  ExternalLink,
  Globe,
  Link2,
  Loader2,
  Map as MapIcon,
  NotebookPen,
  Phone,
  RefreshCw,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useId, useMemo, useState, type ReactNode } from 'react';

const SOURCE_LABELS: Record<string, string> = {
  kor_travel_map: '공공데이터(한국 여행 지도)',
};
const WEEKDAYS = ['일요일', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일'];

type DetailsState =
  | { status: 'loading'; data: PoiPlaceDetails | null }
  | { status: 'ready'; data: PoiPlaceDetails }
  | { status: 'error'; data: null };

type RefreshState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'done' }
  | { status: 'error'; message: string };

/** 장소 영업 정보 — 패널이 열릴 때 한 번 받는다. 실패는 조용히 빈 상태다. */
export function usePlaceDetails(tripId: string, poiId: string) {
  const [state, setState] = useState<DetailsState>({ status: 'loading', data: null });
  const [refreshState, setRefreshState] = useState<RefreshState>({ status: 'idle' });
  useEffect(() => {
    const controller = new AbortController();
    setState({ status: 'loading', data: null });
    setRefreshState({ status: 'idle' });
    poiApi(apiClient)
      .placeDetails(tripId, poiId, { signal: controller.signal })
      .then(
        (data) => {
          if (!controller.signal.aborted) setState({ status: 'ready', data });
        },
        () => {
          if (!controller.signal.aborted) setState({ status: 'error', data: null });
        },
      );
    return () => controller.abort();
  }, [tripId, poiId]);

  const refresh = useCallback(() => {
    setRefreshState({ status: 'loading' });
    poiApi(apiClient)
      .refreshPlaceDetails(tripId, poiId)
      .then(
        (data) => {
          setState({ status: 'ready', data });
          setRefreshState({ status: 'done' });
        },
        (error: unknown) => {
          let message = '장소 정보를 다시 읽어오지 못했습니다. 잠시 뒤 다시 시도해 주세요.';
          if (error instanceof ApiError && error.status === 429) {
            const wait = error.retryAfterSeconds ?? null;
            message = wait
              ? `${wait}초 뒤에 다시 읽어올 수 있습니다.`
              : '잠시 뒤에 다시 읽어올 수 있습니다.';
          } else if (error instanceof ApiError && error.status === 403) {
            message = '이 여행을 편집할 수 있는 사람만 다시 읽어올 수 있습니다.';
          }
          setRefreshState({ status: 'error', message });
        },
      );
  }, [tripId, poiId]);

  return { state, refreshState, refresh };
}

type SectionKey = 'weather' | 'hours' | 'memo' | 'links' | 'maps';

interface SectionDef {
  key: SectionKey;
  title: string;
  icon: ReactNode;
  badge?: ReactNode;
  content: ReactNode;
}

function todayHoursLine(hours: string[], now: number): string | null {
  if (hours.length === 0) return null;
  if (hours.length === 1) return hours[0]!;
  const weekday = WEEKDAYS[new Date(Date.parse(`${kstDateKey(now)}T00:00:00Z`)).getUTCDay()]!;
  return hours.find((line) => line.startsWith(weekday)) ?? null;
}

function MapLinkButton({ link }: { link: MapLink }) {
  return (
    <a
      href={link.web}
      target="_blank"
      rel="noopener noreferrer"
      onClick={(event) => {
        // 모바일은 앱을 먼저 시도한다(없으면 웹). PC는 기본 동작(새 탭)과 같다.
        event.preventDefault();
        openMapLink(link);
      }}
      className="inline-flex min-h-11 flex-1 items-center justify-center gap-1 rounded-sm border border-hairline px-2 text-sm font-semibold text-ink hover:bg-surface-soft"
      data-testid={`place-info-map-${link.provider}`}
    >
      {link.label}
      <ExternalLink className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
    </a>
  );
}

export interface PlaceInfoPanelProps {
  tripId: string;
  poi: TripViewPoi;
  coord: { lon: number; lat: number } | null;
  onClose: () => void;
  className?: string;
}

/**
 * 마커를 눌렀을 때 보이는 장소 정보 — 이름·현재 날씨(아이콘·기온·오늘 최고/최저)·오늘 영업시간·특보를
 * 요약으로 늘 보이고, 날씨 예보·영업 정보·메모·링크·지도 앱 열기는 기본으로 접힌 항목 버튼 한 줄로 둔다
 * (지도를 가리는 면적을 줄인다). 항목은 한 번에 하나만 펼친다.
 */
export function PlaceInfoPanel({
  tripId,
  poi,
  coord,
  onClose,
  className = '',
}: PlaceInfoPanelProps) {
  const name = poi.title ?? '장소';
  const panelId = useId();
  const [openSection, setOpenSection] = useState<SectionKey | null>(null);
  const weather = usePoiWeather(tripId, poi.poi_id);
  const card = 'card' in weather ? weather.card : null;
  const now = useMinuteNow();
  const alerts = useMemo(() => activeAlerts(card, now), [card, now]);
  const { state, refreshState, refresh } = usePlaceDetails(tripId, poi.poi_id);
  const details = state.data;
  const resolutionNotice = featureResolutionNotice(poi.feature_resolution_state);
  const todayHours = details ? todayHoursLine(details.opening_hours, now) : null;
  const mapLinks = useMemo(
    () => (coord ? buildMapLinks({ name, lat: coord.lat, lon: coord.lon }) : []),
    [coord, name],
  );
  const hasDetails =
    details != null &&
    (details.opening_hours.length > 0 || details.closed_days || details.phone || details.website);
  const sources = details
    ? Array.from(new Set(Object.values(details.sources).map((key) => SOURCE_LABELS[key] ?? key)))
    : [];

  const sections: SectionDef[] = [
    {
      key: 'weather',
      title: '날씨·예보',
      icon: <CloudSun className="h-4 w-4" />,
      badge:
        alerts.length > 0 ? (
          <AlertTriangle className="h-4 w-4 text-error-text" aria-label="특보 있음" />
        ) : undefined,
      content: (
        <>
          <WeatherForecastBody
            card={card}
            loading={weather.status === 'loading'}
            failed={weather.status === 'error'}
            onRefresh={weather.refresh}
          />
        </>
      ),
    },
    {
      key: 'hours',
      title: '영업 정보',
      icon: <Clock className="h-4 w-4" />,
      content: (
        <>
          {state.status === 'loading' && !details ? (
            <p className="flex items-center gap-1 text-sm text-muted" role="status">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> 불러오는 중
            </p>
          ) : hasDetails ? (
            <dl className="space-y-2 text-sm" data-testid="place-info-hours-body">
              {details!.opening_hours.length > 0 && (
                <div>
                  <dt className="text-xs font-semibold text-muted">영업시간</dt>
                  <dd>
                    <ul data-testid="place-info-opening-hours">
                      {details!.opening_hours.map((line) => (
                        <li key={line} className="text-body">
                          {line}
                        </li>
                      ))}
                    </ul>
                  </dd>
                </div>
              )}
              {details!.closed_days && (
                <div>
                  <dt className="text-xs font-semibold text-muted">휴무일</dt>
                  <dd className="text-body" data-testid="place-info-closed-days">
                    {details!.closed_days}
                  </dd>
                </div>
              )}
              {details!.phone && (
                <div>
                  <dt className="text-xs font-semibold text-muted">전화</dt>
                  <dd>
                    <a
                      href={`tel:${details!.phone.replace(/[^0-9+]/g, '')}`}
                      className="inline-flex items-center gap-1 text-primary underline-offset-2 hover:underline"
                      data-testid="place-info-phone"
                    >
                      <Phone className="h-3.5 w-3.5" aria-hidden="true" />
                      {details!.phone}
                    </a>
                  </dd>
                </div>
              )}
              {details!.website && (
                <div>
                  <dt className="text-xs font-semibold text-muted">웹사이트</dt>
                  <dd>
                    <a
                      href={details!.website}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex max-w-full items-center gap-1 break-all text-primary underline-offset-2 hover:underline"
                      data-testid="place-info-website"
                    >
                      <Globe className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                      {details!.website}
                    </a>
                  </dd>
                </div>
              )}
            </dl>
          ) : (
            <p className="text-sm text-muted" data-testid="place-info-hours-empty">
              확인된 영업 정보가 없습니다.
            </p>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted">
            <span className="min-w-0 flex-1" data-testid="place-info-hours-source">
              {sources.length > 0 ? `출처: ${sources.join(', ')}` : null}
              {details?.fetched_at
                ? `${sources.length > 0 ? ' · ' : ''}${kstDateKey(Date.parse(details.fetched_at))} 확인`
                : null}
            </span>
            <button
              type="button"
              onClick={refresh}
              disabled={refreshState.status === 'loading' || state.status === 'loading'}
              className="inline-flex min-h-11 items-center gap-1 rounded-sm border border-hairline px-3 text-xs font-semibold text-ink hover:bg-surface-soft disabled:opacity-60"
              data-testid="place-info-refetch"
            >
              {refreshState.status === 'loading' ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
              )}
              다시 읽어오기
            </button>
          </div>
          {refreshState.status === 'error' && (
            <p
              role="alert"
              className="mt-2 text-xs text-error-text"
              data-testid="place-info-refetch-error"
            >
              {refreshState.message}
            </p>
          )}
          {refreshState.status === 'done' && (
            <p
              role="status"
              className="mt-2 text-xs text-success-text"
              data-testid="place-info-refetch-done"
            >
              장소 정보를 다시 읽어왔습니다.
            </p>
          )}
        </>
      ),
    },
    {
      key: 'memo',
      title: '메모',
      icon: <NotebookPen className="h-4 w-4" />,
      content: (
        <>
          {poi.user_note ? (
            <p className="whitespace-pre-wrap text-sm text-body">{poi.user_note}</p>
          ) : (
            <p className="text-sm text-muted">메모가 없습니다.</p>
          )}
        </>
      ),
    },
    {
      key: 'links',
      title: '링크',
      icon: <Link2 className="h-4 w-4" />,
      content: (
        <>
          {poi.user_url || details?.website ? (
            <ul className="space-y-1 text-sm">
              {poi.user_url && (
                <li>
                  <a
                    href={poi.user_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="break-all text-primary underline-offset-2 hover:underline"
                    data-testid="place-info-user-url"
                  >
                    {poi.user_url}
                  </a>
                </li>
              )}
              {details?.website && details.website !== poi.user_url && (
                <li>
                  <a
                    href={details.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="break-all text-primary underline-offset-2 hover:underline"
                  >
                    {details.website}
                  </a>
                </li>
              )}
            </ul>
          ) : (
            <p className="text-sm text-muted">링크가 없습니다.</p>
          )}
        </>
      ),
    },
    {
      key: 'maps',
      title: '지도 앱',
      icon: <MapIcon className="h-4 w-4" />,
      content: (
        <>
          <div className="flex gap-2">
            {mapLinks.map((link) => (
              <MapLinkButton key={link.provider} link={link} />
            ))}
          </div>
        </>
      ),
    },
  ];
  const visibleSections = sections.filter(
    (section) => section.key !== 'maps' || mapLinks.length > 0,
  );
  const current = visibleSections.find((section) => section.key === openSection) ?? null;

  return (
    <aside
      className={`rounded-sm border border-hairline bg-canvas p-3 shadow-overlay ${className}`}
      aria-label={`${name} 장소 정보`}
      data-testid="place-info-panel"
    >
      <header className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-base font-bold text-ink" data-testid="place-info-title">
            {name}
          </h2>
          <div
            className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-body"
            data-testid="place-info-summary"
          >
            <PoiWeatherBadge tripId={tripId} poiId={poi.poi_id} placeName={name} />
            {todayHours && (
              <span className="inline-flex items-center gap-1" data-testid="place-info-today-hours">
                <Clock className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
                {todayHours}
              </span>
            )}
          </div>
          {resolutionNotice && (
            <p className="mt-1 text-xs text-error-text" data-testid="place-info-resolution">
              {resolutionNotice}
            </p>
          )}
          {alerts.length > 0 && (
            <p
              className="mt-1 flex items-center gap-1 text-xs font-semibold text-error-text"
              data-testid="place-info-alert"
            >
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {alerts.map((alert) => alert.title).join(', ')}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex size-11 shrink-0 items-center justify-center rounded-sm text-muted hover:bg-surface-soft hover:text-ink"
          aria-label="장소 정보 닫기"
          data-testid="place-info-close"
        >
          <X className="h-5 w-5" aria-hidden="true" />
        </button>
      </header>

      <div
        className="mt-2 flex gap-1 overflow-x-auto border-t border-hairline pt-2"
        role="group"
        aria-label="장소 정보 항목"
        data-testid="place-info-sections"
      >
        {visibleSections.map((section) => {
          const expanded = section.key === openSection;
          return (
            <button
              key={section.key}
              type="button"
              aria-expanded={expanded}
              aria-controls={`${panelId}-${section.key}`}
              onClick={() => setOpenSection(expanded ? null : section.key)}
              className={`inline-flex min-h-11 shrink-0 items-center gap-1 rounded-sm px-2.5 text-xs font-semibold ${
                expanded ? 'bg-ink text-canvas' : 'bg-surface-soft text-ink hover:bg-hairline'
              }`}
              data-testid={`place-info-${section.key}-toggle`}
            >
              <span aria-hidden="true">{section.icon}</span>
              {section.title}
              {section.badge}
              <ChevronDown
                className={`h-3.5 w-3.5 transition-transform ${expanded ? 'rotate-180' : ''}`}
                aria-hidden="true"
              />
            </button>
          );
        })}
      </div>
      {current && (
        <section
          id={`${panelId}-${current.key}`}
          aria-label={current.title}
          className="mt-2"
          data-testid={`place-info-${current.key}`}
        >
          {current.content}
        </section>
      )}
    </aside>
  );
}
