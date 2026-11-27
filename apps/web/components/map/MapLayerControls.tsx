'use client';

import type { TransportDetailTarget, TransportLayersState } from '@/lib/useTransportLayers';
import { ChevronUp, Layers } from 'lucide-react';
import { useId, useState } from 'react';
import { TransportLayerStatus, TransportLayerToggles } from './TransportLayerControls';

export interface MapLayerControlsProps {
  /** 교통 레이어(주유소·교통 돌발). 기능이 꺼져 있으면(`visible=false`) 그 체크박스를 그리지 않는다. */
  transport: TransportLayersState | null;
  onOpenTransportDetail: (target: TransportDetailTarget) => void;
  /** 교통 돌발 목록을 접어 둔다(여행 지도, #729). */
  collapseIncidents?: boolean;
  /**
   * 패널 전체를 접을 수 있게 한다(전체 화면 탐색 지도). 처음에는 펼쳐 둔다 — 접으면 '레이어' 버튼 하나만 남고
   * 켠 레이어는 그대로 지도에 그려진다.
   */
  collapsible?: boolean;
  className?: string;
}

/**
 * 지도 레이어 패널 — 주유소·교통 돌발 체크박스를 한 줄에 두고, 그 아래에 켠 레이어의 상태를 보인다
 * (소유자 결정 2026-11-16 교통 정보 합침, 2026-11-27 쓰임이 적은 경로·영역 레이어 제거). 그릴 레이어가
 * 없으면 아무것도 그리지 않는다.
 *
 * `data-map-fit-panel`: 여행 지도 맞춤이 이 패널 밑에 든 핀을 피한다(돌발 목록은 transient로 뺀다).
 */
export function MapLayerControls({
  transport,
  onOpenTransportDetail,
  collapseIncidents = false,
  collapsible = false,
  className = '',
}: MapLayerControlsProps) {
  const [collapsed, setCollapsed] = useState(false);
  const bodyId = useId();
  const showTransport = transport?.visible === true;
  if (!transport || !showTransport) return null;
  if (collapsible && collapsed) {
    return (
      <section
        aria-label="지도 레이어"
        data-map-overlay=""
        data-testid="map-layer-controls"
        data-collapsed="true"
        className={`w-fit ${className}`}
      >
        <button
          type="button"
          aria-expanded={false}
          onClick={() => setCollapsed(false)}
          data-testid="map-layer-controls-toggle"
          className="focus-ring flex min-h-11 items-center gap-1.5 rounded-sm border border-hairline bg-canvas px-3 text-xs font-semibold text-ink shadow-card hover:bg-surface-soft"
        >
          <Layers className="size-4" aria-hidden="true" />
          레이어
        </button>
      </section>
    );
  }
  return (
    <section
      aria-label="지도 레이어"
      data-map-overlay=""
      data-map-fit-panel=""
      data-testid="map-layer-controls"
      data-collapsed={collapsible ? 'false' : undefined}
      className={`rounded-sm border border-hairline bg-canvas p-2 text-xs text-ink shadow-card ${className}`}
    >
      <div className="flex items-start gap-1">
        <div
          id={bodyId}
          className="flex min-w-0 flex-1 flex-wrap gap-x-3"
          role="group"
          aria-label="지도 레이어 표시"
        >
          <TransportLayerToggles state={transport} />
        </div>
        {collapsible && (
          <button
            type="button"
            aria-expanded={true}
            aria-controls={bodyId}
            aria-label="지도 레이어 접기"
            title="지도 레이어 접기"
            onClick={() => setCollapsed(true)}
            data-testid="map-layer-controls-toggle"
            className="focus-ring -my-1 -mr-1 flex size-11 shrink-0 items-center justify-center rounded-sm text-muted hover:bg-surface-soft hover:text-ink"
          >
            <ChevronUp className="size-4" aria-hidden="true" />
          </button>
        )}
      </div>
      <TransportLayerStatus
        state={transport}
        onOpenDetail={onOpenTransportDetail}
        collapseIncidents={collapseIncidents}
      />
    </section>
  );
}
