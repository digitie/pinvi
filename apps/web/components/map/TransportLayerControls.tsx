'use client';

import { useId, useState } from 'react';
import type { HighwayIncidentItem, TransportLayer, TransportLayerResult } from '@pinvi/schemas';
import {
  TRANSPORT_LAYER_META,
  TRANSPORT_STATUS_LOADING_TEXT,
  sortIncidentsByRecency,
  transportLayerStatusText,
} from '@pinvi/domain';
import type { TransportDetailTarget, TransportLayersState } from '@/lib/useTransportLayers';

/** 돌발 목록 최대 표시 개수 — 패널이 지도를 덮지 않게. */
const INCIDENT_LIST_MAX = 5;

function layerLine(
  layer: TransportLayer,
  minZoom: number,
  state: Pick<
    TransportLayersState,
    'zoom' | 'results' | 'receivedAt' | 'nowMs' | 'status' | 'hasMap' | 'nearMode' | 'radiusM'
  >,
): string | null {
  // 결과 전에도 줄을 차지한다 — 결과가 와서 줄이 새로 생기면 패널 상시 부분이 자라 여행 지도가 다시
  // 맞춰지고 같은 레이어를 다시 조회한다(#712). 문구 규칙은 모바일 여행 지도와 공용(`@pinvi/domain`).
  return transportLayerStatusText({
    meta: { layer, minZoom },
    layerStatus: state.status?.layers.find((s) => s.layer === layer),
    result: state.results.find((r) => r.layer === layer),
    nearMode: state.nearMode,
    zoom: state.zoom,
    loading: state.hasMap,
    radiusM: state.radiusM,
    receivedAt: state.receivedAt,
    nowMs: state.nowMs,
  });
}

function incidentsOf(results: readonly TransportLayerResult[]): HighwayIncidentItem[] {
  const result = results.find((r) => r.layer === 'highway_incident' && r.status === 'ok');
  if (!result) return [];
  return sortIncidentsByRecency(
    result.items.filter((i): i is HighwayIncidentItem => i.layer === 'highway_incident'),
  );
}

/**
 * 교통 레이어 체크박스(주유소·교통 돌발) — 지도 레이어 패널에서 경로·영역 체크박스와 같은 줄에 놓인다
 * (`MapLayerControls`). `state.visible`이 false면 아무것도 그리지 않는다.
 */
export function TransportLayerToggles({ state }: { state: TransportLayersState }) {
  if (!state.visible) return null;
  return (
    <>
      {TRANSPORT_LAYER_META.map((meta) => (
        <label className="flex min-h-11 cursor-pointer items-center gap-1.5" key={meta.layer}>
          <input
            type="checkbox"
            checked={state.enabled.has(meta.layer)}
            data-testid={`transport-layer-toggle-${meta.layer}`}
            onChange={() => state.toggle(meta.layer)}
          />
          {meta.label}
        </label>
      ))}
    </>
  );
}

export interface TransportLayerStatusProps {
  state: TransportLayersState;
  onOpenDetail: (target: TransportDetailTarget) => void;
  /**
   * 돌발 목록을 접어 두고 '교통 돌발' 상태 줄을 눌러 펴게 한다(여행 지도, #729). 여행 지도는 맞춤이 끝난
   * 뒤 결과가 오므로, 목록이 저절로 펼쳐지면 맞춤이 피한 패널 아래로 자라 핀을 덮는다. 상태 줄은 켠
   * 순간부터 터치 높이(44px)를 차지해, 결과가 와서 버튼이 돼도 패널 상시 높이가 그대로다(#712).
   */
  collapseIncidents?: boolean;
}

/**
 * 켠 교통 레이어의 상태 줄(개수·반경·신선도)과 교통 돌발 목록(ADR-076). `state.visible`이 false(기능 꺼짐·
 * 상태 미확인)이거나 켠 레이어가 없으면 아무것도 그리지 않는다 — 꺼진 동안 지도 화면은 지금과 같다.
 */
export function TransportLayerStatus({
  state,
  onOpenDetail,
  collapseIncidents = false,
}: TransportLayerStatusProps) {
  const listId = useId();
  const incidents = state.enabled.has('highway_incident') ? incidentsOf(state.results) : [];
  const hasIncidents = incidents.length > 0;
  const [expanded, setExpanded] = useState(false);
  // 목록이 비면(레이어 끔·0건·불러올 수 없음) 접는다 — 다음 결과가 왔을 때 목록이 저절로 펼쳐지지 않게.
  const [prevHasIncidents, setPrevHasIncidents] = useState(hasIncidents);
  if (hasIncidents !== prevHasIncidents) {
    setPrevHasIncidents(hasIncidents);
    if (!hasIncidents) setExpanded(false);
  }
  if (!state.visible) return null;
  const enabledMeta = TRANSPORT_LAYER_META.filter((meta) => state.enabled.has(meta.layer));
  if (enabledMeta.length === 0) return null;
  const showList = incidents.length > 0 && (!collapseIncidents || expanded);
  return (
    <div data-testid="transport-layer-status">
      <ul className="mt-1 space-y-0.5">
        {enabledMeta.map((meta) => {
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
            'data-status': result?.status ?? (line === TRANSPORT_STATUS_LOADING_TEXT ? 'loading' : ''),
            'data-reason': result?.reason ?? '',
          };
          if (collapseIncidents && meta.layer === 'highway_incident') {
            // 접기 버튼 높이(44px)를 켠 순간부터 차지한다 — 결과가 와서 버튼이 돼도 상시 높이가 그대로다.
            return (
              // 글자는 다른 상태 줄처럼 위에 붙인다. 오른쪽엔 펼침 표시만 둬 문구 폭을 지킨다 — '오래된 정보'가
              // 잘리지 않게(#712).
              <li key={meta.layer} className="flex min-h-11 items-start text-muted" {...attrs}>
                {hasIncidents ? (
                  <button
                    type="button"
                    aria-expanded={expanded}
                    aria-controls={expanded ? listId : undefined}
                    onClick={() => setExpanded((v) => !v)}
                    data-testid="transport-incident-toggle"
                    className="focus-ring -mx-1 flex min-h-11 w-[calc(100%+0.5rem)] items-start gap-1 rounded-sm px-1 text-left hover:bg-surface-soft"
                  >
                    <span className="line-clamp-2 flex-1">
                      {text}
                      <span className="sr-only"> 목록</span>
                    </span>
                    <span aria-hidden="true" className="shrink-0 whitespace-nowrap text-body">
                      {expanded ? '▴' : '▾'}
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
          <p className="font-semibold text-body">
            {state.nearMode ? '여행 장소 주변' : '이 지역'} 교통 돌발 {incidents.length}건
          </p>
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
