'use client';

import { PoiWeatherBadge } from '@/components/weather/WeatherBadge';
import { WeatherForecastBody } from '@/components/weather/WeatherForecastPopup';
import { buildMapLinks, openMapLink, type MapLink } from '@/lib/mapLinks';
import {
  useKakaoPhone,
  usePlaceDetails,
  type PlaceDetailsRefreshState,
  type PlaceDetailsState,
} from '@/lib/usePlaceDetails';
import { useMinuteNow, usePoiWeather } from '@/lib/usePoiWeather';
import {
  activeAlerts,
  hasAnyPlaceDetail,
  placeDetailsSourceLine,
  telHref,
  todayHoursLine,
  type WeatherAlert,
} from '@pinvi/domain';
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
import { useId, useMemo, useState, type ReactNode } from 'react';

const LINK_CLASS = 'break-all text-primary underline-offset-2 hover:underline';

type SectionKey = 'weather' | 'hours' | 'memo' | 'links' | 'maps';

interface SectionDef {
  key: SectionKey;
  title: string;
  icon: ReactNode;
  badge?: ReactNode;
  content: ReactNode;
}

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-semibold text-muted">{label}</dt>
      <dd className="text-body">{children}</dd>
    </div>
  );
}

function DetailsList({ details }: { details: PoiPlaceDetails }) {
  return (
    <dl className="space-y-2 text-sm" data-testid="place-info-hours-body">
      {details.opening_hours.length > 0 && (
        <DetailRow label="영업시간">
          <ul data-testid="place-info-opening-hours">
            {details.opening_hours.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </DetailRow>
      )}
      {details.closed_days && (
        <DetailRow label="휴무일">
          <span data-testid="place-info-closed-days">{details.closed_days}</span>
        </DetailRow>
      )}
      {details.phone && (
        <DetailRow label="전화">
          <a
            href={telHref(details.phone)}
            className={`inline-flex items-center gap-1 ${LINK_CLASS}`}
            data-testid="place-info-phone"
          >
            <Phone className="h-3.5 w-3.5" aria-hidden="true" />
            {details.phone}
          </a>
        </DetailRow>
      )}
      {details.website && (
        <DetailRow label="웹사이트">
          <a
            href={details.website}
            target="_blank"
            rel="noopener noreferrer"
            className={`inline-flex max-w-full items-center gap-1 ${LINK_CLASS}`}
            data-testid="place-info-website"
          >
            <Globe className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {details.website}
          </a>
        </DetailRow>
      )}
    </dl>
  );
}

function RefreshMessage({ refreshState }: { refreshState: PlaceDetailsRefreshState }) {
  if (refreshState.status === 'error') {
    return (
      <p
        role="alert"
        className="mt-2 text-xs text-error-text"
        data-testid="place-info-refetch-error"
      >
        {refreshState.message}
      </p>
    );
  }
  if (refreshState.status === 'done') {
    return (
      <p
        role="status"
        className="mt-2 text-xs text-success-text"
        data-testid="place-info-refetch-done"
      >
        장소 정보를 다시 읽어왔습니다.
      </p>
    );
  }
  return null;
}

/**
 * 저장된 전화가 없을 때 Kakao Local에서 표시 시점에 찾은 전화(ADR-054 — 저장하지 않음). 카카오 출처
 * 표시와 카카오맵 back-link를 함께 둔다. 영업 정보 항목을 펼쳤을 때만 마운트된다(요청 절약).
 */
function KakaoPhone({ tripId, poiId }: { tripId: string; poiId: string }) {
  const match = useKakaoPhone(tripId, poiId, true);
  if (!match?.phone) return null;
  return (
    <div className="mt-2 text-sm" data-testid="place-info-kakao-phone">
      <p className="text-xs font-semibold text-muted">전화 (카카오)</p>
      <p className="flex flex-wrap items-center gap-x-2 text-body">
        <a
          href={telHref(match.phone)}
          className={`inline-flex items-center gap-1 ${LINK_CLASS}`}
          data-testid="place-info-kakao-phone-number"
        >
          <Phone className="h-3.5 w-3.5" aria-hidden="true" />
          {match.phone}
        </a>
        {match.provider_url && (
          <a
            href={match.provider_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-muted underline-offset-2 hover:underline"
            data-testid="place-info-kakao-link"
          >
            출처: 카카오맵
          </a>
        )}
      </p>
    </div>
  );
}

function HoursContent({
  tripId,
  poiId,
  state,
  refreshState,
  onRefresh,
}: {
  tripId: string;
  poiId: string;
  state: PlaceDetailsState;
  refreshState: PlaceDetailsRefreshState;
  onRefresh: () => void;
}) {
  const details = state.data;
  const refreshing = refreshState.status === 'loading';
  // 저장된 전화(공공데이터)가 있으면 Kakao를 부르지 않는다.
  const needsKakaoPhone = state.status !== 'loading' && !details?.phone;
  let body: ReactNode;
  if (state.status === 'loading' && !details) {
    body = (
      <p className="flex items-center gap-1 text-sm text-muted" role="status">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> 불러오는 중
      </p>
    );
  } else if (hasAnyPlaceDetail(details)) {
    body = <DetailsList details={details} />;
  } else {
    body = (
      <p className="text-sm text-muted" data-testid="place-info-hours-empty">
        확인된 영업 정보가 없습니다.
      </p>
    );
  }
  return (
    <>
      {body}
      {needsKakaoPhone && <KakaoPhone tripId={tripId} poiId={poiId} />}
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted">
        <span className="min-w-0 flex-1" data-testid="place-info-hours-source">
          {placeDetailsSourceLine(details)}
        </span>
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing || state.status === 'loading'}
          className="inline-flex min-h-11 items-center gap-1 rounded-sm border border-hairline px-3 text-xs font-semibold text-ink hover:bg-surface-soft disabled:opacity-60"
          data-testid="place-info-refetch"
        >
          {refreshing ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          )}
          다시 읽어오기
        </button>
      </div>
      <RefreshMessage refreshState={refreshState} />
    </>
  );
}

function LinksContent({ userUrl, website }: { userUrl: string | null; website: string | null }) {
  const links = [userUrl, website && website !== userUrl ? website : null].filter(
    (value): value is string => Boolean(value),
  );
  if (links.length === 0) return <p className="text-sm text-muted">링크가 없습니다.</p>;
  return (
    <ul className="space-y-1 text-sm">
      {links.map((url) => (
        <li key={url}>
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className={LINK_CLASS}
            data-testid={url === userUrl ? 'place-info-user-url' : undefined}
          >
            {url}
          </a>
        </li>
      ))}
    </ul>
  );
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

function PanelSummary({
  tripId,
  poi,
  name,
  todayHours,
  alerts,
}: {
  tripId: string;
  poi: TripViewPoi;
  name: string;
  todayHours: string | null;
  alerts: WeatherAlert[];
}) {
  const resolutionNotice = featureResolutionNotice(poi.feature_resolution_state);
  return (
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
  );
}

function SectionToggles({
  sections,
  openSection,
  panelId,
  onToggle,
}: {
  sections: SectionDef[];
  openSection: SectionKey | null;
  panelId: string;
  onToggle: (key: SectionKey | null) => void;
}) {
  return (
    <div
      className="mt-2 flex gap-1 overflow-x-auto border-t border-hairline pt-2"
      role="group"
      aria-label="장소 정보 항목"
      data-testid="place-info-sections"
    >
      {sections.map((section) => {
        const expanded = section.key === openSection;
        return (
          <button
            key={section.key}
            type="button"
            aria-expanded={expanded}
            aria-controls={`${panelId}-${section.key}`}
            onClick={() => onToggle(expanded ? null : section.key)}
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
  const todayHours = details ? todayHoursLine(details.opening_hours, now) : null;
  const mapLinks = useMemo(
    () => (coord ? buildMapLinks({ name, lat: coord.lat, lon: coord.lon }) : []),
    [coord, name],
  );

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
        <WeatherForecastBody
          card={card}
          loading={weather.status === 'loading'}
          failed={weather.status === 'error'}
          onRefresh={weather.refresh}
        />
      ),
    },
    {
      key: 'hours',
      title: '영업 정보',
      icon: <Clock className="h-4 w-4" />,
      content: (
        <HoursContent
          tripId={tripId}
          poiId={poi.poi_id}
          state={state}
          refreshState={refreshState}
          onRefresh={refresh}
        />
      ),
    },
    {
      key: 'memo',
      title: '메모',
      icon: <NotebookPen className="h-4 w-4" />,
      content: poi.user_note ? (
        <p className="whitespace-pre-wrap text-sm text-body">{poi.user_note}</p>
      ) : (
        <p className="text-sm text-muted">메모가 없습니다.</p>
      ),
    },
    {
      key: 'links',
      title: '링크',
      icon: <Link2 className="h-4 w-4" />,
      content: <LinksContent userUrl={poi.user_url} website={details?.website ?? null} />,
    },
  ];
  if (mapLinks.length > 0) {
    sections.push({
      key: 'maps',
      title: '지도 앱',
      icon: <MapIcon className="h-4 w-4" />,
      content: (
        <div className="flex gap-2">
          {mapLinks.map((link) => (
            <MapLinkButton key={link.provider} link={link} />
          ))}
        </div>
      ),
    });
  }
  const current = sections.find((section) => section.key === openSection) ?? null;

  return (
    <aside
      className={`rounded-sm border border-hairline bg-canvas p-3 shadow-overlay ${className}`}
      aria-label={`${name} 장소 정보`}
      data-testid="place-info-panel"
    >
      <header className="flex items-start gap-2">
        <PanelSummary
          tripId={tripId}
          poi={poi}
          name={name}
          todayHours={todayHours}
          alerts={alerts}
        />
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
      <SectionToggles
        sections={sections}
        openSection={openSection}
        panelId={panelId}
        onToggle={setOpenSection}
      />
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
