'use client';

import { useId, useState } from 'react';
import type { HighwayIncidentItem, TransportLayer, TransportLayerResult } from '@pinvi/schemas';
import {
  TRANSPORT_LAYER_META,
  sortIncidentsByRecency,
  transportFreshnessAgeSeconds,
  transportFreshnessLabel,
} from '@pinvi/domain';
import type { TransportDetailTarget, TransportLayersState } from '@/lib/useTransportLayers';

const LOADING_TEXT = '불러오는 중';

/** 돌발 목록 최대 표시 개수 — 패널이 지도를 덮지 않게. */
const INCIDENT_LIST_MAX = 5;

function layerLine(
  layer: TransportLayer,
  minZoom: number,
  state: Pick<
    TransportLayersState,
    'zoom' | 'results' | 'receivedAt' | 'nowMs' | 'status' | 'hasMap'
  >,
): string | null {
  const status = state.status?.layers.find((s) => s.layer === layer);
  if (status && !status.available) return '일시적으로 불러올 수 없음';
  if (state.zoom != null && state.zoom < minZoom) return '확대하면 보여요';
  const result = state.results.find((r) => r.layer === layer);
  // 결과 전에도 줄을 차지한다 — 결과가 와서 줄이 새로 생기면 패널 상시 부분이 자라 여행 지도가 다시
  // 맞춰지고 같은 레이어를 다시 조회한다(#712).
  if (!result) return state.hasMap ? LOADING_TEXT : null;
  if (result.status !== 'ok') return '일시적으로 불러올 수 없음';
  const parts: string[] = [`${result.items.length}곳`];
  if (result.truncated) parts.push('일부만 표시 — 확대하세요');
  if (result.freshness && state.receivedAt != null) {
    parts.push(
      transportFreshnessLabel(
        transportFreshnessAgeSeconds(result.freshness, state.receivedAt, state.nowMs),
      ),
    );
    if (result.freshness.stale) parts.push('오래된 정보');
  }
  return parts.join(' · ');
}

function incidentsOf(results: readonly TransportLayerResult[]): HighwayIncidentItem[] {
  const result = results.find((r) => r.layer === 'highway_incident' && r.status === 'ok');
  if (!result) return [];
  return sortIncidentsByRecency(
    result.items.filter((i): i is HighwayIncidentItem => i.layer === 'highway_incident'),
  );
}

export interface TransportLayerControlsProps {
  state: TransportLayersState;
  onOpenDetail: (target: TransportDetailTarget) => void;
  className?: string;
  /**
   * 돌발 목록을 접어 두고 '교통 돌발' 상태 줄을 눌러 펴게 한다(여행 지도, #729). 여행 지도는 맞춤이 끝난
   * 뒤 결과가 오므로, 목록이 저절로 펼쳐지면 맞춤이 피한 패널 아래로 자라 핀을 덮는다. 상태 줄은 켠
   * 순간부터 터치 높이(44px)를 차지해, 결과가 와서 버튼이 돼도 패널 상시 높이가 그대로다(#712).
   */
  collapseIncidents?: boolean;
}

/**
 * 지도 transport 레이어 토글(ADR-076). `state.visible`이 false(기능 꺼짐·상태 미확인)면 아무것도
 * 그리지 않는다 — 꺼진 동안 지도 화면은 지금과 같다.
 */
export function TransportLayerControls({
  state,
  onOpenDetail,
  className,
  collapseIncidents = false,
}: TransportLayerControlsProps) {
  const listId = useId();
  const incidentLayerOn = state.enabled.has('highway_incident');
  const [expanded, setExpanded] = useState(false);
  // 레이어를 끄면 접는다 — 다시 켰을 때 맞춤 뒤에 목록이 저절로 펼쳐지지 않게.
  const [prevIncidentLayerOn, setPrevIncidentLayerOn] = useState(incidentLayerOn);
  if (incidentLayerOn !== prevIncidentLayerOn) {
    setPrevIncidentLayerOn(incidentLayerOn);
    if (!incidentLayerOn) setExpanded(false);
  }
  if (!state.visible) return null;
  const incidents = incidentLayerOn ? incidentsOf(state.results) : [];
  const showList = incidents.length > 0 && (!collapseIncidents || expanded);
  return (
    // data-map-fit-panel: 여행 지도 맞춤이 이 패널 밑에 든 핀을 피한다(사건 목록은 transient로 뺀다).
    <div
      className={`rounded-sm bg-canvas/95 p-2 text-xs shadow-card ${className ?? ''}`}
      data-testid="transport-layer-controls"
      data-map-fit-panel=""
    >
      <p className="mb-1 text-sm font-semibold text-ink">교통 정보</p>
      <div className="flex flex-wrap gap-1" role="group" aria-label="교통 정보 레이어">
        {TRANSPORT_LAYER_META.map((meta) => {
          const on = state.enabled.has(meta.layer);
          return (
            <button
              key={meta.layer}
              type="button"
              aria-pressed={on}
              onClick={() => state.toggle(meta.layer)}
              data-testid={`transport-layer-toggle-${meta.layer}`}
              className={`focus-ring min-h-11 rounded-full border px-3 text-sm font-semibold ${
                on
                  ? 'border-ink bg-ink text-canvas'
                  : 'border-hairline bg-canvas text-body hover:bg-surface-soft'
              }`}
            >
              {meta.label}
            </button>
          );
        })}
      </div>
      <ul className="mt-1 space-y-0.5">
        {TRANSPORT_LAYER_META.filter((meta) => state.enabled.has(meta.layer)).map((meta) => {
          const line = layerLine(meta.layer, meta.minZoom, state);
          const result = state.results.find((r) => r.layer === meta.layer);
          if (!line) return null;
          const text = (
            <>
              <span className="font-semibold text-body">{meta.label}</span> {line}
            </>
          );
          const attrs = {
            'data-testid': `transport-layer-state-${meta.layer}`,
            'data-status': result?.status ?? (line === LOADING_TEXT ? 'loading' : ''),
            'data-reason': result?.reason ?? '',
          };
          if (collapseIncidents && meta.layer === 'highway_incident') {
            // 접기 버튼 높이(44px)를 켠 순간부터 차지한다 — 결과가 와서 버튼이 돼도 상시 높이가 그대로다.
            return (
              <li key={meta.layer} className="flex min-h-11 items-center text-muted" {...attrs}>
                {incidents.length > 0 ? (
                  <button
                    type="button"
                    aria-expanded={expanded}
                    aria-controls={expanded ? listId : undefined}
                    onClick={() => setExpanded((v) => !v)}
                    data-testid="transport-incident-toggle"
                    className="focus-ring -mx-1 flex min-h-11 w-[calc(100%+0.5rem)] items-center gap-1 rounded-sm px-1 text-left hover:bg-surface-soft"
                  >
                    <span className="line-clamp-2 flex-1">{text}</span>
                    <span className="shrink-0 font-semibold text-body">
                      목록<span aria-hidden="true">{expanded ? ' ▴' : ' ▾'}</span>
                    </span>
                  </button>
                ) : (
                  <span className="line-clamp-2">{text}</span>
                )}
              </li>
            );
          }
          return (
            <li
              key={meta.layer}
              // 두 줄 높이 고정 — 결과 문구 길이로 줄 수가 바뀌면 상시 높이가 바뀌어 다시 맞춘다(#712).
              // 한 줄로 자르면 모바일 폭에서 '오래된 정보'·'일부만 표시'가 잘린다.
              className="line-clamp-2 min-h-[2lh] text-muted"
              {...attrs}
            >
              {text}
            </li>
          );
        })}
      </ul>
      {showList && (
        <div
          id={listId}
          className="mt-2 border-t border-hairline pt-1"
          data-testid="transport-incident-list"
          data-map-fit-transient=""
        >
          <p className="font-semibold text-body">이 지역 교통 돌발 {incidents.length}건</p>
          <ul>
            {incidents.slice(0, INCIDENT_LIST_MAX).map((incident) => (
              <li key={incident.feature_id}>
                <button
                  type="button"
                  className="focus-ring min-h-11 w-full truncate rounded-sm px-1 text-left text-sm text-body hover:bg-surface-soft"
                  onClick={() =>
                    onOpenDetail({
                      layer: 'highway_incident',
                      featureId: incident.feature_id,
                      title: incident.title,
                    })
                  }
                >
                  {incident.title}
                  {incident.process_status ? ` · ${incident.process_status}` : ''}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
