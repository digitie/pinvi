'use client';

import type { FeatureGeometryState } from '@/lib/useFeatureGeometry';
import type { TransportDetailTarget, TransportLayersState } from '@/lib/useTransportLayers';
import { GeometryLayerStatus, GeometryLayerToggles } from './FeatureGeometryLayer';
import { TransportLayerStatus, TransportLayerToggles } from './TransportLayerControls';

export interface MapLayerControlsProps {
  /** 경로·영역 레이어. `null`이면 그 체크박스를 그리지 않는다. */
  geometry: FeatureGeometryState | null;
  /** 교통 레이어(주유소·교통 돌발). 기능이 꺼져 있으면(`visible=false`) 그 체크박스를 그리지 않는다. */
  transport: TransportLayersState | null;
  onOpenTransportDetail: (target: TransportDetailTarget) => void;
  /** 교통 돌발 목록을 접어 둔다(여행 지도, #729). */
  collapseIncidents?: boolean;
  className?: string;
}

/**
 * 지도 레이어 패널 — 경로·영역·주유소·교통 돌발 체크박스를 한 줄에 두고, 그 아래에 켠 레이어의 상태를
 * 보인다(소유자 결정 2026-11-16: 교통 정보를 경로·영역과 같은 자리로 합침). 그릴 레이어가 없으면 아무것도
 * 그리지 않는다.
 *
 * `data-map-fit-panel`: 여행 지도 맞춤이 이 패널 밑에 든 핀을 피한다(돌발 목록은 transient로 뺀다).
 */
export function MapLayerControls({
  geometry,
  transport,
  onOpenTransportDetail,
  collapseIncidents = false,
  className = '',
}: MapLayerControlsProps) {
  const showTransport = transport?.visible === true;
  if (!geometry && !showTransport) return null;
  return (
    <section
      aria-label="지도 레이어"
      data-map-overlay=""
      data-map-fit-panel=""
      data-testid="map-layer-controls"
      className={`rounded-sm border border-hairline bg-canvas p-2 text-xs text-ink shadow-card ${className}`}
    >
      <div className="flex flex-wrap gap-x-3" role="group" aria-label="지도 레이어 표시">
        {geometry && <GeometryLayerToggles state={geometry} />}
        {transport && showTransport && <TransportLayerToggles state={transport} />}
      </div>
      {geometry && <GeometryLayerStatus state={geometry} />}
      {transport && showTransport && (
        <TransportLayerStatus
          state={transport}
          onOpenDetail={onOpenTransportDetail}
          collapseIncidents={collapseIncidents}
        />
      )}
    </section>
  );
}
