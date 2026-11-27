'use client';

import { CirclePlaceMarker } from '@/components/map/CirclePlaceMarker';
import { FuelBrandIcon } from '@/components/map/FuelBrandIcon';
import { MakiIcon } from '@/components/map/MakiIcon';
import { ClusterLayer, MakiMarker, Marker } from '@/components/map/vworldPrimitives';
import { markerZIndex } from '@/lib/markerStacking';
import type { TransportDetailTarget, TransportMapPoint } from '@/lib/useTransportLayers';
import { transportLayerLabel, transportMarkerBudget } from '@pinvi/domain';
import { useSyncExternalStore, type CSSProperties } from 'react';

export interface TransportMarkersProps {
  points: TransportMapPoint[];
  selectedId?: string | null;
  onSelect: (target: TransportDetailTarget) => void;
}

/** 교통 돌발 마커 원 지름 — transport·Map 공용 마커 배지(24px 원 + maki 글리프)와 같다. */
export const TRANSPORT_BADGE_SIZE = 24;
const TRANSPORT_BADGE_ICON_SIZE = 14;
/** 화면 예산을 넘었을 때의 묶음 반경(px). 주유소 마커는 로고 + 가격 라벨이라 넓다. */
const DENSE_CLUSTER_RADIUS = 60;
/** 예산을 넘으면 이 줌까지 묶는다(예전과 같은 14 — 줌 15 이상은 늘 펼친다). */
const DENSE_CLUSTER_MAX_ZOOM = 14;
/** transport `clusterAtScale`의 상세 줌(11) 미만은 개수와 무관하게 묶는다 — 교통 돌발은 줌 7부터 온다. */
const ALWAYS_CLUSTER_MAX_ZOOM = 10;

function subscribeResize(callback: () => void) {
  window.addEventListener('resize', callback);
  return () => window.removeEventListener('resize', callback);
}
const viewportArea = () => `${window.innerWidth}x${window.innerHeight}`;

/**
 * 화면 면적 대비 마커가 많을 때만 묶는다(transport `clusterAtScale`). 적으면 전부 펼쳐 가격 라벨을 바로
 * 읽게 한다 — 줌 11~14에서도 몇 곳뿐이면 묶음 거품을 보이지 않는다.
 *
 * 근사: transport는 지도 크기와 화면 안 장소 수로 세지만, 이 layer는 지도 인스턴스 밖(마커 portal)이라 창 크기와
 * 받은 항목 수(주유소+돌발)로 센다. 여행 지도 반경 결과처럼 화면보다 넓은 응답은 조금 더 일찍 묶인다.
 */
function useDenseClustering(count: number): boolean {
  const size = useSyncExternalStore(subscribeResize, viewportArea, () => '0x0');
  const [width, height] = size.split('x').map(Number) as [number, number];
  return count > transportMarkerBudget(width, height);
}

/**
 * transport 마커 layer(ADR-076) — `VWorldMap` 자식으로 둔다. feature 마커와 별개 layer이고, 누르면
 * 중간 팝업 없이 상세 대화상자를 연다(transport id는 feature 상세로 가지 않는다 — D7).
 *
 * 모양은 kor-travel-transport 유가 지도와 같다:
 * - 주유소: 상표 로고 칩(40×24) + 오른쪽 흰 가격 라벨("휘 1,650" 한 줄에 한 유종, 판매 중인 유종만). 글자는
 *   transport의 11px 대신 DESIGN.md 최소 단계 text-xs(12px).
 * - 교통 돌발: 24px 원 배지(roadblock 글리프, Map 팔레트 색). 이름은 hover 제목·접근 이름으로만.
 */
export function TransportMarkers({ points, selectedId, onSelect }: TransportMarkersProps) {
  const dense = useDenseClustering(points.length);
  return (
    <ClusterLayer
      points={points}
      radius={DENSE_CLUSTER_RADIUS}
      // 예산 안이면 줌 11부터 펼친다(supercluster는 maxZoom 이하 줌에서만 묶는다).
      maxZoom={dense ? DENSE_CLUSTER_MAX_ZOOM : ALWAYS_CLUSTER_MAX_ZOOM}
      renderMarker={(point) => {
        const p = point as TransportMapPoint;
        const selected = p.id === selectedId;
        const select = () => onSelect({ layer: p.layer, featureId: p.featureId, title: p.title });
        if (p.layer === 'fuel_station') {
          return <FuelStationMarker key={p.id} point={p} selected={selected} onSelect={select} />;
        }
        if (p.layer === 'highway_incident') {
          return (
            <CirclePlaceMarker
              key={p.id}
              lngLat={p.lngLat}
              color={p.color}
              size={TRANSPORT_BADGE_SIZE}
              icon={<MakiIcon icon={p.icon} size={TRANSPORT_BADGE_ICON_SIZE} />}
              className="transport-map-marker"
              title={p.title}
              selected={selected}
              zIndex={markerZIndex(selected)}
              ariaLabel={`${transportLayerLabel(p.layer)} ${p.title} 상세 보기`}
              interactionId={p.id}
              onClick={select}
            />
          );
        }
        // 휴게소·공항은 지도에서 뺐다(2026-11-16) — 계약상 오면 예전 모양 그대로.
        return (
          <MakiMarker
            key={p.id}
            lngLat={p.lngLat}
            icon={p.icon}
            color={p.color}
            title={p.title}
            selected={selected}
            zIndex={markerZIndex(selected)}
            ariaLabel={p.title}
            interactionId={p.id}
            onClick={select}
          />
        );
      }}
    />
  );
}

function FuelStationMarker({
  point,
  selected,
  onSelect,
}: {
  point: TransportMapPoint;
  selected: boolean;
  onSelect: () => void;
}) {
  const lines = point.priceLines ?? [];
  const brand = point.brand ?? null;
  const ariaLabel = [
    transportLayerLabel(point.layer),
    point.title,
    brand?.name,
    point.priceSpeech || null,
    '상세 보기',
  ]
    .filter(Boolean)
    .join(' ');
  // hover 제목은 두지 않는다 — vworld 툴팁 상자가 바로 옆 가격 라벨을 되풀이한다. 이름은 접근 이름이 싣는다.
  return (
    <Marker
      lngLat={point.lngLat}
      className="transport-map-marker transport-map-marker--fuel"
      selected={selected}
      zIndex={markerZIndex(selected)}
      ariaLabel={ariaLabel}
      interactionId={point.id}
      onClick={onSelect}
    >
      {/* 칩·라벨 모양은 globals.css `.fuel-marker-chip`·`.fuel-marker-price`(마커 예외, 토큰 색). */}
      <span className="fuel-marker-chip" data-testid="fuel-station-marker">
        <FuelBrandIcon brand={brand} decorative />
        {lines.length > 0 && (
          <span
            className="fuel-marker-price"
            // 테두리 = 마커 팔레트 색(transport와 같다). 데이터에서 오는 색이라 CSS 변수로 넘긴다.
            style={{ '--marker-color': point.color } as CSSProperties}
            aria-hidden="true"
            data-testid="fuel-station-marker-price"
          >
            {lines.join('\n')}
          </span>
        )}
      </span>
    </Marker>
  );
}

/** VWorld 키 없는 CI에서도 마커 데이터를 검증할 수 있게 노출한다(지도 밖에 둔다). */
export function TransportMarkerLegend({ points }: { points: TransportMapPoint[] }) {
  return (
    <div className="sr-only" aria-hidden="true" data-testid="transport-marker-legend">
      {points.map((p) => (
        <span
          key={p.id}
          data-testid="transport-marker"
          data-layer={p.layer}
          data-feature-id={p.featureId}
          data-marker-color={p.markerColor}
          data-marker-icon={p.icon}
          data-brand-code={p.brand?.code || undefined}
          data-price-lines={p.priceLines?.join('|') || undefined}
        >
          {p.title}
        </span>
      ))}
    </div>
  );
}
