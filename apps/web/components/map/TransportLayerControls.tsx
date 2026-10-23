'use client';

import type { HighwayIncidentItem, TransportLayer, TransportLayerResult } from '@pinvi/schemas';
import {
  TRANSPORT_LAYER_META,
  sortIncidentsByRecency,
  transportFreshnessAgeSeconds,
  transportFreshnessLabel,
} from '@pinvi/domain';
import type { TransportDetailTarget, TransportLayersState } from '@/lib/useTransportLayers';

/** 돌발 목록 최대 표시 개수 — 패널이 지도를 덮지 않게. */
const INCIDENT_LIST_MAX = 5;

function layerLine(
  layer: TransportLayer,
  minZoom: number,
  state: Pick<TransportLayersState, 'zoom' | 'results' | 'receivedAt' | 'nowMs' | 'status'>,
): string | null {
  const status = state.status?.layers.find((s) => s.layer === layer);
  if (status && !status.available) return '일시적으로 불러올 수 없음';
  if (state.zoom != null && state.zoom < minZoom) return '확대하면 보여요';
  const result = state.results.find((r) => r.layer === layer);
  if (!result) return null;
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
}

/**
 * 지도 transport 레이어 토글(ADR-076). `state.visible`이 false(기능 꺼짐·상태 미확인)면 아무것도
 * 그리지 않는다 — 꺼진 동안 지도 화면은 지금과 같다.
 */
export function TransportLayerControls({
  state,
  onOpenDetail,
  className,
}: TransportLayerControlsProps) {
  if (!state.visible) return null;
  const incidents = state.enabled.has('highway_incident') ? incidentsOf(state.results) : [];
  return (
    <div
      className={`rounded-sm bg-canvas/95 p-2 text-xs shadow-card ${className ?? ''}`}
      data-testid="transport-layer-controls"
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
          return line ? (
            <li
              key={meta.layer}
              className="text-muted"
              data-testid={`transport-layer-state-${meta.layer}`}
              data-status={result?.status ?? ''}
              data-reason={result?.reason ?? ''}
            >
              <span className="font-semibold text-body">{meta.label}</span> {line}
            </li>
          ) : null;
        })}
      </ul>
      {incidents.length > 0 && (
        <div className="mt-2 border-t border-hairline pt-1" data-testid="transport-incident-list">
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
