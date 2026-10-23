'use client';

import { ClusterLayer, MakiMarker } from '@/components/map/vworldPrimitives';
import type { TransportDetailTarget, TransportMapPoint } from '@/lib/useTransportLayers';

export interface TransportMarkersProps {
  points: TransportMapPoint[];
  selectedId?: string | null;
  onSelect: (target: TransportDetailTarget) => void;
}

/**
 * transport 마커 layer(ADR-076) — `VWorldMap` 자식으로 둔다. feature 마커와 별개 layer이고, 누르면
 * 중간 팝업 없이 상세 대화상자를 연다(transport id는 feature 상세로 가지 않는다 — D7).
 */
export function TransportMarkers({ points, selectedId, onSelect }: TransportMarkersProps) {
  return (
    <ClusterLayer
      points={points}
      radius={40}
      maxZoom={14}
      renderMarker={(point) => {
        const p = point as TransportMapPoint;
        return (
          <MakiMarker
            key={p.id}
            lngLat={p.lngLat}
            icon={p.icon}
            color={p.color}
            title={p.title}
            selected={p.id === selectedId}
            ariaLabel={p.title}
            onClick={() => onSelect({ layer: p.layer, featureId: p.featureId, title: p.title })}
          />
        );
      }}
    />
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
        >
          {p.title}
        </span>
      ))}
    </div>
  );
}
