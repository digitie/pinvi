'use client';

import { FuelBrandIcon } from '@/components/map/FuelBrandIcon';
import { formatFuelPrice, fuelDateTime, type FuelBrand, type FuelPriceRow } from '@pinvi/domain';
import { ChevronRight, ClockAlert } from 'lucide-react';

/**
 * 주유소 정보 블록 — kor-travel-transport 공개 유가 화면(`/public/fuel`) 장소 상세와 같은 정보·순서:
 * 상표(로고 + 이름) → 유종별 현재가(판매 중인 유종만, `1,689원/L`, 7일 넘은 값은 "오래됨") → 편의시설 →
 * 데이터 출처(기준정보 반영·제공기관 공시 시각). 교통 상세의 주유소·휴게소 주유소가 함께 쓴다.
 *
 * 취급하지 않는 유종은 `rows`에 들어오지 않는다(`fuelStationPriceRows`·`restAreaFuelPriceRows`가 거른다) —
 * 여기서도 "판매 안 함"·"-" 행을 만들지 않는다.
 */

export function FuelBrandLine({ brand }: { brand: FuelBrand | null }) {
  if (!brand) return null;
  return (
    <p className="flex min-w-0 items-center gap-2 text-sm text-ink" data-testid="fuel-brand">
      <FuelBrandIcon brand={brand} decorative />
      <span className="min-w-0 truncate font-semibold">{brand.name}</span>
    </p>
  );
}

export function FuelPriceList({ rows }: { rows: readonly FuelPriceRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted" data-testid="transport-fuel-prices" data-empty="true">
        등록된 유효 유가가 없습니다.
      </p>
    );
  }
  // dl에는 이름을 붙일 role이 없다 — 이름은 감싸는 section이 갖는다.
  return (
    <section aria-label="유종별 현재 가격">
      <dl className="rounded-sm border border-hairline px-3" data-testid="transport-fuel-prices">
        {rows.map((row) => {
          const checked = fuelDateTime(row.observedAt);
          return (
            <div
              key={row.key}
              className="flex min-w-0 items-baseline justify-between gap-3 border-b border-hairline py-2 last:border-b-0"
              data-testid="transport-fuel-price"
              data-product={row.key}
            >
              <dt className="min-w-0 text-sm text-body [overflow-wrap:anywhere]">{row.label}</dt>
              <dd className="flex min-w-0 flex-wrap items-center justify-end gap-x-2 gap-y-1">
                {row.old && (
                  <span
                    className="inline-flex items-center gap-1 rounded-full bg-warning-bg px-2 py-0.5 text-xs font-semibold text-warning-text"
                    title={checked ?? undefined}
                    data-testid="transport-fuel-price-old"
                  >
                    <ClockAlert size={14} aria-hidden="true" />
                    오래됨
                  </span>
                )}
                <span className="text-lg font-bold tabular-nums text-ink">
                  {formatFuelPrice(row.price)}
                </span>
                {checked && row.observedAt && (
                  <time className="sr-only" dateTime={row.observedAt}>
                    관측 {checked}
                  </time>
                )}
              </dd>
            </div>
          );
        })}
      </dl>
    </section>
  );
}

/** "셀프 · 세차" — 값이 있을 때만. */
export function FuelFacilities({ facilities }: { facilities: readonly string[] }) {
  if (facilities.length === 0) return null;
  return (
    <p className="text-sm text-body" data-testid="fuel-facilities">
      <span className="text-muted">편의시설</span> · {facilities.join(' · ')}
    </p>
  );
}

/** 데이터 출처 — transport의 "데이터 출처" 안내와 같은 내용(접어 둔다). */
export function FuelDataSource({
  source,
  baseUpdatedAt,
  rows,
}: {
  source: string;
  /** 기준정보(주유소 자체)를 원천에서 마지막으로 본 시각. */
  baseUpdatedAt?: string | null;
  rows: readonly FuelPriceRow[];
}) {
  const base = fuelDateTime(baseUpdatedAt);
  const notices = rows.flatMap((row) => {
    const at = fuelDateTime(row.providerUpdatedAt);
    return at ? [{ key: row.key, text: `${row.label} 제공기관 공시 ${at}` }] : [];
  });
  return (
    <details className="group text-xs text-muted" data-testid="fuel-data-source">
      {/* inline-flex라 기본 ▸ 표시가 사라지므로 펼침 상태를 아이콘으로 보인다. */}
      <summary className="focus-ring inline-flex min-h-11 cursor-pointer list-none items-center gap-1 rounded-sm font-semibold text-body [&::-webkit-details-marker]:hidden">
        <ChevronRight
          size={14}
          aria-hidden="true"
          className="transition-transform duration-fast group-open:rotate-90 motion-reduce:transition-none"
        />
        데이터 출처
      </summary>
      <div className="space-y-0.5 pb-1">
        <p>{source}</p>
        {base && <p>기준정보 반영 {base}</p>}
        {notices.map((notice) => (
          <p key={notice.key}>{notice.text}</p>
        ))}
      </div>
    </details>
  );
}
