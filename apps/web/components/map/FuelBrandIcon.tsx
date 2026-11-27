'use client';

import type { FuelBrand } from '@pinvi/domain';
import { Fuel } from 'lucide-react';
import { useState } from 'react';

/**
 * 주유소 상표 로고(오피넷 원본 이미지, 40×24 안에 원래 비율) — kor-travel-transport `FuelBrandIcon`과 같은 표시.
 * 로고가 없는 상표(자가상표·모르는 코드)나 이미지를 못 읽으면 일반 주유기 아이콘을 그린다.
 *
 * `decorative`: 옆에 상표 이름 글자가 이미 있는 자리(상세 머리·마커 버튼의 접근 이름)에서는 대체 글자를
 * 비워 이름을 두 번 읽지 않게 한다.
 */
export function FuelBrandIcon({
  brand,
  decorative = false,
  className = '',
}: {
  brand: FuelBrand | null;
  decorative?: boolean;
  className?: string;
}) {
  const source = brand?.logo ? `/fuel-brands/${brand.logo}` : null;
  const [failed, setFailed] = useState<string | null>(null);
  const name = brand?.name ?? '주유소';
  return (
    <span
      className={`inline-flex h-6 w-10 shrink-0 items-center justify-center ${className}`}
      data-testid="fuel-brand-icon"
      data-brand-code={brand?.code ?? ''}
    >
      {source && failed !== source ? (
        // 제공기관의 작은 원본 로고를 그대로 쓴다 — Next 이미지 변환·외부 요청 없음.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={source}
          alt={decorative ? '' : name}
          width={40}
          height={24}
          className="block h-full w-full object-contain"
          onError={() => setFailed(source)}
        />
      ) : (
        <>
          <Fuel size={18} aria-hidden="true" className="text-body" />
          {!decorative && <span className="sr-only">{name}</span>}
        </>
      )}
    </span>
  );
}
