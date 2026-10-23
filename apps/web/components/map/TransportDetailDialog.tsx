'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { ApiError, transportApi } from '@pinvi/api-client';
import type {
  FuelPriceHistoryResponse,
  FuelStationItem,
  TransportDetailResponse,
  TransportFreshness,
  TransportItem,
} from '@pinvi/schemas';
import {
  formatFuelPrice,
  fuelProductLabel,
  transportFreshnessAgeSeconds,
  transportFreshnessLabel,
  transportItemTitle,
  transportLayerLabel,
} from '@pinvi/domain';
import { FeatureDetailModal } from '@/components/map/FeatureDetailModal';
import { apiClient } from '@/lib/api';
import { isAbortError } from '@/lib/abort';
import type { TransportDetailTarget } from '@/lib/useTransportLayers';

const HISTORY_DAYS = 30;
const HISTORY_ROWS_PER_PRODUCT = 7;

type Loaded = { data: TransportDetailResponse; receivedAt: number };

function kstText(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3 py-1 text-sm">
      <dt className="w-20 shrink-0 text-muted">{label}</dt>
      <dd className="min-w-0 flex-1 text-ink">{children}</dd>
    </div>
  );
}

function yesNo(value: boolean | null | undefined): string | null {
  if (value == null) return null;
  return value ? '있음' : '없음';
}

function Freshness({
  freshness,
  receivedAt,
  label,
}: {
  freshness: TransportFreshness;
  receivedAt: number;
  label?: string;
}) {
  // 대화상자는 열린 동안만 산다 — 받은 시각 기준 나이로 충분하다(Map age_seconds + 0).
  const text = transportFreshnessLabel(transportFreshnessAgeSeconds(freshness, receivedAt, receivedAt));
  return (
    <p className="text-xs text-muted" data-testid="transport-detail-freshness">
      {label ? `${label} ` : ''}
      {text}
      {freshness.stale && <span className="ml-1 font-semibold text-error-text">오래된 정보</span>}
    </p>
  );
}

function FuelHistory({ featureId }: { featureId: string }) {
  const [history, setHistory] = useState<FuelPriceHistoryResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    transportApi(apiClient)
      .fuelPriceHistory(featureId, { days: HISTORY_DAYS }, { signal: controller.signal })
      .then(setHistory)
      .catch((err: unknown) => {
        if (!isAbortError(err)) setFailed(true);
      });
    return () => controller.abort();
  }, [featureId]);

  if (failed) {
    return <p className="text-sm text-muted">가격 추이를 불러오지 못했습니다.</p>;
  }
  if (!history) {
    return <p className="text-sm text-muted">가격 추이 불러오는 중…</p>;
  }
  if (history.status === 'unavailable' || history.items.length === 0) {
    return (
      <p
        className="text-sm text-muted"
        data-testid="transport-price-history-unavailable"
        data-reason={history.reason ?? ''}
      >
        가격 추이는 아직 제공되지 않습니다.
      </p>
    );
  }
  const byProduct = new Map<string, typeof history.items>();
  for (const point of history.items) {
    const list = byProduct.get(point.product_key) ?? [];
    list.push(point);
    byProduct.set(point.product_key, list);
  }
  return (
    <div className="space-y-2" data-testid="transport-price-history">
      {[...byProduct.entries()].map(([key, points]) => (
        <div key={key}>
          <p className="text-sm font-semibold text-ink">
            {fuelProductLabel(key, points[0]?.product_name)}
          </p>
          <ul className="text-sm">
            {points.slice(0, HISTORY_ROWS_PER_PRODUCT).map((point) => (
              <li key={point.observed_at} className="flex justify-between text-body">
                <span className="text-muted">{kstText(point.observed_at)}</span>
                <span>{formatFuelPrice(point.price)}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
      {history.truncated && <p className="text-xs text-muted">최근 기록만 보입니다.</p>}
    </div>
  );
}

function FuelStationBody({ item }: { item: FuelStationItem }) {
  const [showHistory, setShowHistory] = useState(false);
  const extras = [
    item.is_self ? '셀프' : null,
    item.is_24h ? '24시간' : null,
    item.has_carwash ? '세차' : null,
    item.has_cvs ? '편의점' : null,
    item.has_maintenance ? '정비' : null,
    item.lpg_available ? 'LPG' : null,
  ].filter((x): x is string => x != null);
  return (
    <>
      <div className="rounded-sm border border-hairline p-2" data-testid="transport-fuel-prices">
        {item.prices.length === 0 ? (
          <p className="text-sm text-muted">가격 정보가 없습니다.</p>
        ) : (
          <ul className="text-sm">
            {item.prices.map((price) => (
              <li key={price.product_key} className="flex justify-between py-0.5">
                <span className="text-body">
                  {fuelProductLabel(price.product_key, price.product_name)}
                </span>
                <span className="font-semibold text-ink">{formatFuelPrice(price.price)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <dl>
        {item.brand_name && <Row label="상표">{item.brand_name}</Row>}
        {extras.length > 0 && <Row label="편의">{extras.join(' · ')}</Row>}
      </dl>
      <div>
        {showHistory ? (
          <FuelHistory featureId={item.feature_id} />
        ) : (
          <button
            type="button"
            onClick={() => setShowHistory(true)}
            data-testid="transport-price-history-open"
            className="focus-ring min-h-11 w-full rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
          >
            가격 추이 보기
          </button>
        )}
      </div>
    </>
  );
}

function ItemBody({ item }: { item: TransportItem }) {
  switch (item.layer) {
    case 'fuel_station':
      return <FuelStationBody item={item} />;
    case 'rest_area': {
      const prices = item.fuel_prices;
      return (
        <>
          {prices && (
            <div className="rounded-sm border border-hairline p-2" data-testid="transport-fuel-prices">
              <ul className="text-sm">
                <li className="flex justify-between py-0.5">
                  <span className="text-body">휘발유</span>
                  <span className="font-semibold text-ink">{formatFuelPrice(prices.gasoline_price)}</span>
                </li>
                <li className="flex justify-between py-0.5">
                  <span className="text-body">경유</span>
                  <span className="font-semibold text-ink">{formatFuelPrice(prices.diesel_price)}</span>
                </li>
                {prices.lpg_price != null && (
                  <li className="flex justify-between py-0.5">
                    <span className="text-body">LPG</span>
                    <span className="font-semibold text-ink">{formatFuelPrice(prices.lpg_price)}</span>
                  </li>
                )}
              </ul>
              {prices.oil_company && <p className="text-xs text-muted">{prices.oil_company}</p>}
            </div>
          )}
          <dl>
            {item.route_name && (
              <Row label="노선">
                {item.route_name}
                {item.direction ? ` (${item.direction} 방향)` : ''}
              </Row>
            )}
            {yesNo(item.has_gas_station) && <Row label="주유소">{yesNo(item.has_gas_station)}</Row>}
            {yesNo(item.has_lpg_station) && <Row label="LPG 충전">{yesNo(item.has_lpg_station)}</Row>}
            {yesNo(item.has_ev_charger) && <Row label="전기차 충전">{yesNo(item.has_ev_charger)}</Row>}
          </dl>
        </>
      );
    }
    case 'highway_incident':
      return (
        <dl>
          {item.incident_type && <Row label="유형">{item.incident_type}</Row>}
          {item.process_status && <Row label="처리 상태">{item.process_status}</Row>}
          {item.route_name && (
            <Row label="노선">
              {item.route_name}
              {item.direction ? ` (${item.direction} 방향)` : ''}
            </Row>
          )}
          {item.point_name && <Row label="위치">{item.point_name}</Row>}
          {item.congestion_length != null && <Row label="정체">{item.congestion_length} km</Row>}
          {kstText(item.occurred_at) && <Row label="발생">{kstText(item.occurred_at)}</Row>}
          {item.message && <Row label="내용">{item.message}</Row>}
        </dl>
      );
    case 'airport':
      return (
        <dl>
          <Row label="영문명">{item.name_english}</Row>
          <Row label="코드">
            {item.iata_code}
            {item.icao_code ? ` / ${item.icao_code}` : ''}
          </Row>
          {item.municipality && <Row label="지역">{item.municipality}</Row>}
        </dl>
      );
  }
}

function addressOf(item: TransportItem): string | null {
  if (item.layer === 'highway_incident') return null;
  return item.address.road ?? item.address.jibun ?? null;
}

function phoneOf(item: TransportItem): string | null {
  if (item.layer === 'fuel_station' || item.layer === 'rest_area') return item.phone ?? null;
  return null;
}

export interface TransportDetailDialogProps {
  target: TransportDetailTarget | null;
  onClose: () => void;
}

/** transport 항목 상세(ADR-076 D6). feature 상세 셸(`FeatureDetailModal`)을 그대로 쓴다. */
export function TransportDetailDialog({ target, onClose }: TransportDetailDialogProps) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const key = target ? `${target.layer}:${target.featureId}` : null;
  const [prevKey, setPrevKey] = useState(key);
  if (key !== prevKey) {
    setPrevKey(key);
    setLoaded(null);
    setError(null);
  }

  useEffect(() => {
    if (!target) return;
    const controller = new AbortController();
    transportApi(apiClient)
      .detail(target.layer, target.featureId, { signal: controller.signal })
      .then((data) => setLoaded({ data, receivedAt: Date.now() }))
      .catch((err: unknown) => {
        if (isAbortError(err)) return;
        setError(
          err instanceof ApiError && err.status === 404
            ? '이 항목은 더 이상 제공되지 않습니다.'
            : '교통 정보를 일시적으로 불러올 수 없습니다.',
        );
      });
    return () => controller.abort();
  }, [target]);

  if (!target) return null;
  const item = loaded?.data.item ?? null;
  const address = item ? addressOf(item) : null;
  const phone = item ? phoneOf(item) : null;
  return (
    <FeatureDetailModal
      open
      title={item ? transportItemTitle(item) : target.title}
      subtitle={transportLayerLabel(target.layer)}
      loading={!loaded && !error}
      error={error ?? undefined}
      onClose={onClose}
      testId="transport-detail"
      footer={
        loaded ? (
          <div className="space-y-0.5">
            <Freshness freshness={loaded.data.freshness} receivedAt={loaded.receivedAt} />
            {loaded.data.fuel_price_freshness && (
              <Freshness
                freshness={loaded.data.fuel_price_freshness}
                receivedAt={loaded.receivedAt}
                label="유가"
              />
            )}
            <p>출처: 한국석유공사·한국도로공사·한국공항공사(kor-travel-map 경유)</p>
          </div>
        ) : null
      }
    >
      {item && (
        <div className="space-y-3" data-layer={item.layer}>
          <ItemBody item={item} />
          {(address || phone) && (
            <dl>
              {address && <Row label="주소">{address}</Row>}
              {phone && (
                <Row label="전화">
                  <a className="underline" href={`tel:${phone}`}>
                    {phone}
                  </a>
                </Row>
              )}
            </dl>
          )}
        </div>
      )}
    </FeatureDetailModal>
  );
}
