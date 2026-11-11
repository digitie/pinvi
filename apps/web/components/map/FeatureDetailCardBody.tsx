'use client';

import { withOccurrenceKeys } from '@/lib/occurrenceKeys';
import type { ExternalEnrichment, FeatureDetailCard } from '@pinvi/schemas';
import { AlertTriangle, Clock, ExternalLink, Globe, Loader2, MapPin, Phone } from 'lucide-react';
import type { ReactNode } from 'react';

/**
 * Feature 상세 detail-card 본문(TDR, ADR-056, F5). kind별 일반 사용자 노출 필드만 렌더하고, 옵트인
 * 외부 enrichment(카카오/네이버, display-only)를 attribution + back-link과 함께 보여준다. 순수 표현
 * 컴포넌트(데이터 로딩은 `useFeatureDetailCard`가 담당).
 */
export interface FeatureDetailCardBodyProps {
  card: FeatureDetailCard;
  /** enrichment(providers) 요청이 이미 걸렸는지 — true면 결과/로딩을 보여준다. */
  enrichmentRequested?: boolean;
  /** enrichment 재조회 진행 중. */
  enriching?: boolean;
  /** "더 보기"를 눌렀을 때(place kind에서만 노출). */
  onLoadEnrichment?: () => void;
  testId?: string;
}

function Row({
  icon,
  children,
  testId,
}: {
  icon: ReactNode;
  children: ReactNode;
  testId?: string;
}) {
  return (
    <div className="flex items-start gap-2 text-sm text-ink" data-testid={testId}>
      <span className="mt-0.5 shrink-0 text-muted" aria-hidden="true">
        {icon}
      </span>
      <span className="min-w-0">{children}</span>
    </div>
  );
}

const PROVIDER_LABEL: Record<ExternalEnrichment['provider'], string> = {
  kakao: '카카오',
  naver: '네이버 검색',
};

function EnrichmentRow({ row }: { row: ExternalEnrichment }) {
  const label = PROVIDER_LABEL[row.provider];
  return (
    <li
      className="rounded-sm border border-hairline p-2.5"
      data-testid={`feature-detail-enrichment-${row.provider}`}
      data-matched={row.matched ? 'true' : 'false'}
    >
      <div className="flex items-center justify-between gap-2">
        {/* attribution 필수(ADR-054 M19) */}
        <span className="text-xs font-semibold text-muted">{label}</span>
        {row.provider_url && (
          <a
            href={row.provider_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-legal-link hover:underline"
            data-testid={`feature-detail-enrichment-${row.provider}-link`}
          >
            지도에서 보기
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </a>
        )}
      </div>
      {row.matched ? (
        <div className="mt-1 space-y-0.5">
          {row.name && <p className="truncate text-sm text-ink">{row.name}</p>}
          {row.address && <p className="truncate text-xs text-body">{row.address}</p>}
          {row.phone && <p className="text-xs text-body">{row.phone}</p>}
        </div>
      ) : (
        <p className="mt-1 text-xs text-muted">일치하는 외부 정보 없음</p>
      )}
    </li>
  );
}

export function FeatureDetailCardBody(...args: Parameters<typeof useFeatureDetailCardBodyModel>) {
  const viewModel = useFeatureDetailCardBodyModel(...args);
  if (viewModel.renderBranch === 'render0')
    return <FeatureDetailCardBodyView0 viewModel={viewModel} />;
  return null;
}

function useFeatureDetailCardBodyModel({
  card,
  enrichmentRequested = false,
  enriching = false,
  onLoadEnrichment,
  testId = 'feature-detail-card-body',
}: FeatureDetailCardBodyProps) {
  return {
    renderBranch: 'render0' as const,
    card,
    enriching,
    enrichmentRequested,
    onLoadEnrichment,
    testId,
  };
}

type FeatureDetailCardBodyView0Model = Extract<
  ReturnType<typeof useFeatureDetailCardBodyModel>,
  { renderBranch: 'render0' }
>;
function FeatureDetailCardBodyView0({ viewModel }: { viewModel: FeatureDetailCardBodyView0Model }) {
  return <FeatureDetailCardBodyView0Part0 viewModel={viewModel} />;
}

function FeatureDetailCardBodyView0Part0({
  viewModel,
}: {
  viewModel: FeatureDetailCardBodyView0Model;
}) {
  const { testId, card } = viewModel;
  return (
    <div
      className="space-y-3"
      data-testid={testId}
      data-kind={card.kind}
      data-feature-id={card.feature_id}
    >
      {card.degraded_providers.length > 0 && (
        <p
          className="flex items-center gap-1 text-xs text-muted"
          role="status"
          data-testid={`${testId}-enrichment-degraded`}
        >
          <AlertTriangle className="h-3 w-3" aria-hidden="true" />
          일부 상세 정보를 불러오지 못했습니다.
        </p>
      )}
      {card.category_label && (
        <p className="text-xs font-medium text-muted" data-testid={`${testId}-category`}>
          {card.category_label}
        </p>
      )}
      {card.address_line && (
        <Row icon={<MapPin className="h-4 w-4" />} testId={`${testId}-address`}>
          {card.address_line}
        </Row>
      )}

      {card.kind === 'place' && <PlaceFacts card={card} testId={testId} />}

      {card.kind === 'event' && <EventFacts card={card} testId={testId} />}

      {card.kind === 'notice' && <NoticeFacts card={card} testId={testId} />}

      {card.kind === 'price' && card.items.length > 0 && (
        <FeatureDetailCardBodyView0Part0Part0 viewModel={viewModel} />
      )}

      {card.homepage_url && (
        <Row icon={<Globe className="h-4 w-4" />} testId={`${testId}-homepage`}>
          <a
            href={card.homepage_url}
            target="_blank"
            rel="noopener noreferrer"
            className="break-all text-legal-link hover:underline"
          >
            홈페이지
          </a>
        </Row>
      )}

      {/* 옵트인 외부 enrichment — place kind만(ADR-056). */}
      {card.kind === 'place' && <FeatureDetailCardBodyView0Part0Part1 viewModel={viewModel} />}
    </div>
  );
}

function FeatureDetailCardBodyView0Part0Part0({
  viewModel,
}: {
  viewModel: FeatureDetailCardBodyView0Model;
}) {
  const { testId, card } = viewModel;
  if (card.kind !== 'price') return null;
  return (
    <ul
      className="divide-y divide-hairline rounded-sm border border-hairline"
      data-testid={`${testId}-price`}
    >
      {withOccurrenceKeys(card.items, (item) => JSON.stringify([item.name, item.price])).map(
        ({ item, key }) => (
          <li key={key} className="flex justify-between gap-2 px-3 py-2 text-sm">
            <span className="text-ink">{item.name}</span>
            <span className="text-body">
              {item.price ?? '-'}
              {card.unit ? ` ${card.unit}` : ''}
            </span>
          </li>
        ),
      )}
    </ul>
  );
}

function FeatureDetailCardBodyView0Part0Part1({
  viewModel,
}: {
  viewModel: FeatureDetailCardBodyView0Model;
}) {
  const { enrichmentRequested, onLoadEnrichment, enriching, testId, card } = viewModel;
  return (
    <div className="border-t border-hairline pt-3">
      {!enrichmentRequested ? (
        <button
          type="button"
          onClick={onLoadEnrichment}
          disabled={enriching}
          data-testid={`${testId}-load-enrichment`}
          className="inline-flex min-h-11 items-center gap-1.5 rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft disabled:opacity-50"
        >
          카카오·네이버에서 더 보기
        </button>
      ) : enriching ? (
        <div className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          외부 정보 불러오는 중…
        </div>
      ) : (
        <div className="space-y-2">
          <ul className="space-y-2">
            {card.enrichment.map((row) => (
              <EnrichmentRow key={row.provider} row={row} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function PlaceFacts({
  card,
  testId,
}: {
  card: Extract<FeatureDetailCard, { kind: 'place' }>;
  testId: string;
}) {
  return (
    <>
      {card.phone && (
        <Row icon={<Phone className="h-4 w-4" />} testId={`${testId}-phone`}>
          {card.phone}
        </Row>
      )}
      {card.business_hours && (
        <Row icon={<Clock className="h-4 w-4" />} testId={`${testId}-hours`}>
          {card.business_hours}
        </Row>
      )}
    </>
  );
}

function EventFacts({
  card,
  testId,
}: {
  card: Extract<FeatureDetailCard, { kind: 'event' }>;
  testId: string;
}) {
  return (
    <>
      {(card.start_date || card.end_date) && (
        <Row icon={<Clock className="h-4 w-4" />} testId={`${testId}-period`}>
          {[card.start_date, card.end_date].filter(Boolean).join(' ~ ')}
        </Row>
      )}
      {card.venue && (
        <Row icon={<MapPin className="h-4 w-4" />} testId={`${testId}-venue`}>
          {card.venue}
        </Row>
      )}
    </>
  );
}

function NoticeFacts({
  card,
  testId,
}: {
  card: Extract<FeatureDetailCard, { kind: 'notice' }>;
  testId: string;
}) {
  return (
    <>
      {(card.start_date || card.end_date) && (
        <Row icon={<Clock className="h-4 w-4" />} testId={`${testId}-period`}>
          {[card.start_date, card.end_date].filter(Boolean).join(' ~ ')}
        </Row>
      )}
      {card.body && (
        <p className="whitespace-pre-line text-sm text-ink" data-testid={`${testId}-notice-body`}>
          {card.body}
        </p>
      )}
    </>
  );
}
