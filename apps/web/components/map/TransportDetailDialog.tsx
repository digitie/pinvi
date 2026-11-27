'use client';

import { FeatureDetailModal } from '@/components/map/FeatureDetailModal';
import {
  FuelBrandLine,
  FuelDataSource,
  FuelFacilities,
  FuelPriceList,
} from '@/components/map/FuelStationInfo';
import { isAbortError } from '@/lib/abort';
import { apiClient } from '@/lib/api';
import type { TransportDetailTarget } from '@/lib/useTransportLayers';
import { ApiError, transportApi } from '@pinvi/api-client';
import {
  FUEL_PRODUCT_CODE_BY_KEY,
  fuelBrand,
  fuelDateTime,
  fuelProductLabel,
  fuelStationFacilities,
  fuelStationPriceRows,
  formatFuelPrice,
  isFuelPriceSold,
  restAreaFuelPriceRows,
  transportFreshnessAgeSeconds,
  transportFreshnessLabel,
  transportItemTitle,
  transportLayerLabel,
} from '@pinvi/domain';
import type {
  FuelPriceHistoryResponse,
  FuelStationItem,
  TransportDetailResponse,
  TransportFreshness,
  TransportItem,
} from '@pinvi/schemas';
import { useEffect, useState, type ReactNode } from 'react';

const HISTORY_DAYS = 30;
const HISTORY_ROWS_PER_PRODUCT = 7;
// 일시적인 원천 장애 — 다시 열면 나을 수 있다. 나머지 이유는 "아직 제공되지 않음"이다.
const TRANSIENT_HISTORY_REASONS: ReadonlySet<string> = new Set([
  'upstream_timeout',
  'upstream_unavailable',
]);

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
  const text = transportFreshnessLabel(
    transportFreshnessAgeSeconds(freshness, receivedAt, receivedAt),
  );
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
        {history.reason && TRANSIENT_HISTORY_REASONS.has(history.reason)
          ? '가격 추이를 잠시 불러올 수 없습니다. 잠시 후 다시 시도해 주세요.'
          : '가격 추이는 아직 제공되지 않습니다.'}
      </p>
    );
  }
  // 판매하지 않던 날(가격 null·0)은 점으로 그리지 않는다 — 현재가와 같은 규칙.
  const sold = history.items.filter((point): point is typeof point & { price: number } =>
    isFuelPriceSold(point.price),
  );
  if (sold.length === 0) {
    return (
      // 추이는 왔지만 판매한 날이 없다 — "미제공"과 다르다(오류 아님).
      <p className="text-sm text-muted" data-testid="transport-price-history-empty">
        최근 {HISTORY_DAYS}일 동안 표시할 판매 가격이 없습니다.
      </p>
    );
  }
  const byProduct = new Map<string, typeof sold>();
  // 응답 순서에 기대지 않는다 — 최근 것부터 자른다.
  const sorted = [...sold].sort((a, b) => Date.parse(b.observed_at) - Date.parse(a.observed_at));
  for (const point of sorted) {
    const list = byProduct.get(point.product_key) ?? [];
    list.push(point);
    byProduct.set(point.product_key, list);
  }
  const products = [...byProduct.entries()].sort(([a], [b]) => {
    const ca = FUEL_PRODUCT_CODE_BY_KEY[a] ?? a;
    const cb = FUEL_PRODUCT_CODE_BY_KEY[b] ?? b;
    return ca === cb ? 0 : ca < cb ? -1 : 1;
  });
  return (
    <div className="space-y-2" data-testid="transport-price-history">
      {products.map(([key, points]) => (
        <div key={key}>
          <p className="text-sm font-semibold text-ink">
            {fuelProductLabel(key, points[0]?.product_name)}
          </p>
          <ul className="text-sm">
            {points.slice(0, HISTORY_ROWS_PER_PRODUCT).map((point) => (
              <li key={point.observed_at} className="flex justify-between gap-3 text-body">
                <span className="text-muted">{kstText(point.observed_at)}</span>
                <span className="tabular-nums">{formatFuelPrice(point.price)}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
      {history.truncated && <p className="text-xs text-muted">최근 기록만 보입니다.</p>}
    </div>
  );
}

/** transport `collectionSourceLabel`의 주유소·유가 문구 + 원천 기관. */
const FUEL_SOURCE = '전국 주유소·유가 정보 · 한국석유공사 오피넷';
const REST_AREA_FUEL_SOURCE = '고속도로 휴게소 유가 정보 · 한국도로공사';

function FuelStationBody({ item, nowMs }: { item: FuelStationItem; nowMs: number }) {
  const [showHistory, setShowHistory] = useState(false);
  const rows = fuelStationPriceRows(item.prices, nowMs);
  return (
    <>
      <FuelBrandLine brand={fuelBrand(item.brand_code, item.brand_name)} />
      <FuelPriceList rows={rows} />
      <FuelFacilities facilities={fuelStationFacilities(item)} />
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
      <FuelDataSource source={FUEL_SOURCE} baseUpdatedAt={item.source_last_seen_at} rows={rows} />
    </>
  );
}

function ItemBody(...args: Parameters<typeof useItemBodyModel>) {
  const viewModel = useItemBodyModel(...args);
  if (viewModel.renderBranch === 'render0') return <ItemBodyView0 viewModel={viewModel} />;
  if (viewModel.renderBranch === 'render1') return <ItemBodyView1 viewModel={viewModel} />;
  if (viewModel.renderBranch === 'render2') return <ItemBodyView2 viewModel={viewModel} />;
  if (viewModel.renderBranch === 'render3') return <ItemBodyView3 viewModel={viewModel} />;
  return null;
}

function useItemBodyModel({ item, nowMs }: { item: TransportItem; nowMs: number }) {
  switch (item.layer) {
    case 'fuel_station':
      return { renderBranch: 'render0' as const, item, nowMs };
    case 'rest_area': {
      const prices = item.fuel_prices;
      return { renderBranch: 'render1' as const, item, prices, nowMs };
    }
    case 'highway_incident':
      return { renderBranch: 'render2' as const, item };
    case 'airport':
      return { renderBranch: 'render3' as const, item };
  }
}

type ItemBodyView0Model = Extract<ReturnType<typeof useItemBodyModel>, { renderBranch: 'render0' }>;
function ItemBodyView0({ viewModel }: { viewModel: ItemBodyView0Model }) {
  const { item, nowMs } = viewModel;
  return <FuelStationBody item={item} nowMs={nowMs} />;
}

type ItemBodyView1Model = Extract<ReturnType<typeof useItemBodyModel>, { renderBranch: 'render1' }>;
function ItemBodyView1({ viewModel }: { viewModel: ItemBodyView1Model }) {
  const { item, prices, nowMs } = viewModel;
  const rows = restAreaFuelPriceRows(prices, nowMs);
  return (
    <>
      {prices && (
        <>
          <FuelBrandLine brand={fuelBrand(null, prices.oil_company)} />
          <FuelPriceList rows={rows} />
        </>
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
      {prices && <FuelDataSource source={REST_AREA_FUEL_SOURCE} baseUpdatedAt={null} rows={rows} />}
    </>
  );
}

/** transport `highwayRouteLabel` — "0010 · 경부선". 노선 번호만 있으면 "0010번 고속도로". */
function highwayRouteLabel(
  routeNo: string | null | undefined,
  routeName: string | null | undefined,
) {
  const name = routeName?.trim();
  const no = routeNo?.trim();
  if (name) return no ? `${no} · ${name}` : name;
  return no ? `${no}번 고속도로` : null;
}

type ItemBodyView2Model = Extract<ReturnType<typeof useItemBodyModel>, { renderBranch: 'render2' }>;
function ItemBodyView2({ viewModel }: { viewModel: ItemBodyView2Model }) {
  const { item } = viewModel;
  // transport 도로 돌발 상세와 같은 순서: 노선 배지 → "유형 · 처리 상태" → 내용 → (위치·방향·정체·발생) → 출처.
  const route = highwayRouteLabel(item.route_no, item.route_name);
  const status = [item.incident_type, item.process_status].filter(Boolean).join(' · ');
  const occurred = fuelDateTime(item.occurred_at);
  return (
    <>
      {route && (
        <p className="flex flex-wrap gap-2" data-testid="transport-incident-route">
          <span className="rounded-full bg-surface-strong px-2 py-0.5 text-xs font-semibold text-body">
            {route}
          </span>
        </p>
      )}
      {status && (
        <p className="text-sm font-semibold text-ink" data-testid="transport-incident-status">
          {status}
        </p>
      )}
      {item.message && (
        <p
          className="text-sm text-body [overflow-wrap:anywhere]"
          data-testid="transport-incident-message"
        >
          {item.message}
        </p>
      )}
      <dl>
        {item.point_name && <Row label="위치">{item.point_name}</Row>}
        {item.direction && <Row label="방향">{item.direction} 방향</Row>}
        {item.congestion_length != null && <Row label="정체">{item.congestion_length} km</Row>}
        {occurred && <Row label="발생">{occurred}</Row>}
      </dl>
    </>
  );
}

type ItemBodyView3Model = Extract<ReturnType<typeof useItemBodyModel>, { renderBranch: 'render3' }>;
function ItemBodyView3({ viewModel }: { viewModel: ItemBodyView3Model }) {
  const { item } = viewModel;
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
export function TransportDetailDialog(...args: Parameters<typeof useTransportDetailDialogModel>) {
  const viewModel = useTransportDetailDialogModel(...args);
  if (viewModel.renderBranch === 'render0') return <TransportDetailDialogView0 />;
  if (viewModel.renderBranch === 'render1')
    return <TransportDetailDialogView1 viewModel={viewModel} />;
  return null;
}

function useTransportDetailDialogModel({ target, onClose }: TransportDetailDialogProps) {
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

  if (!target) return { renderBranch: 'render0' as const };
  const item = loaded?.data.item ?? null;
  const address = item ? addressOf(item) : null;
  const phone = item ? phoneOf(item) : null;
  return { renderBranch: 'render1' as const, address, error, item, loaded, onClose, phone, target };
}
function TransportDetailDialogView0() {
  return null;
}

type TransportDetailDialogView1Model = Extract<
  ReturnType<typeof useTransportDetailDialogModel>,
  { renderBranch: 'render1' }
>;
function TransportDetailDialogView1({ viewModel }: { viewModel: TransportDetailDialogView1Model }) {
  const { address, error, item, loaded, onClose, phone, target } = viewModel;
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
          <ItemBody item={item} nowMs={loaded?.receivedAt ?? 0} />
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
