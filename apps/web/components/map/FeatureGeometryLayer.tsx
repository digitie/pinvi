'use client';

import { useCallback, useMemo, useRef } from 'react';
import type { MapMouseEvent } from 'vworld-map-web';
import type { Feature } from 'geojson';
import { resolveMarkerStyle } from '@pinvi/domain';
import type { GeometryFeature } from '@/lib/featureGeometry';
import type { FeatureGeometryState } from '@/lib/useFeatureGeometry';
import { PolygonArea, Popup, RouteLine } from './vworldPrimitives';

function GeometryItem({
  feature,
  onClick,
}: {
  feature: GeometryFeature;
  onClick: (event: MapMouseEvent) => void;
}) {
  const data = useMemo<Feature>(
    () => ({
      type: 'Feature',
      properties: { feature_id: feature.feature_id },
      geometry: feature.geometry,
    }),
    [feature],
  );
  const color = resolveMarkerStyle({
    upstreamKind: feature.kind,
    upstreamColor: feature.marker_color,
    upstreamIcon: feature.marker_icon,
    upstreamCategory: feature.category,
  }).hex;
  const id = 'pinvi-geometry-' + encodeURIComponent(feature.feature_id);
  if (data.geometry?.type === 'LineString' || data.geometry?.type === 'MultiLineString') {
    return (
      <RouteLine
        id={id}
        data={data as Feature<GeoJSON.LineString | GeoJSON.MultiLineString>}
        color={color}
        width={4}
        onClick={onClick}
      />
    );
  }
  const red = parseInt(color.slice(1, 3), 16);
  const green = parseInt(color.slice(3, 5), 16);
  const blue = parseInt(color.slice(5, 7), 16);
  return (
    <PolygonArea
      id={id}
      data={data as Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon>}
      fillColor={`rgba(${red},${green},${blue},0.18)`}
      outlineColor={color}
      outlineWidth={2}
      onClick={onClick}
    />
  );
}

export function FeatureGeometryLayers({ state }: { state: FeatureGeometryState }) {
  const handledClicks = useRef(new WeakSet<Event>());
  const featuresById = useMemo(
    () => new Map(state.features.map((feature) => [feature.feature_id, feature])),
    [state.features],
  );
  const { select } = state;
  const onClick = useCallback(
    (event: MapMouseEvent) => {
      // 겹친 layer의 위임 이벤트는 각각 발생하므로 실제 최상단 hit를 한 번만 선택한다.
      if (handledClicks.current.has(event.originalEvent)) return;
      handledClicks.current.add(event.originalEvent);
      const layers = state.features
        .flatMap((feature) => {
          const prefix = 'pinvi-geometry-' + encodeURIComponent(feature.feature_id);
          return feature.kind === 'route'
            ? [prefix + '-layer']
            : [prefix + '-fill-layer', prefix + '-line-layer'];
        })
        .filter((id) => event.target.getLayer(id));
      if (layers.length === 0) return;
      const hits = event.target.queryRenderedFeatures(event.point, { layers });
      for (const hit of hits) {
        const feature = featuresById.get(String(hit.properties?.feature_id ?? ''));
        if (!feature) continue;
        select(feature, [event.lngLat.lng, event.lngLat.lat]);
        return;
      }
    },
    [state.features, featuresById, select],
  );
  return (
    <>
      {state.features.map((feature) => (
        <GeometryItem key={feature.feature_id} feature={feature} onClick={onClick} />
      ))}
    </>
  );
}

export function FeatureGeometryControls({
  state,
  className = '',
}: {
  state: FeatureGeometryState;
  className?: string;
}) {
  return (
    <section
      aria-label="경로·영역 레이어"
      data-map-overlay=""
      className={`rounded-sm border border-hairline bg-canvas p-2 text-xs text-ink shadow-card ${className}`}
    >
      <div className="flex flex-wrap gap-3">
        {(['route', 'area'] as const).map((kind) => (
          <label className="flex min-h-9 cursor-pointer items-center gap-1.5" key={kind}>
            <input
              type="checkbox"
              checked={state.kinds.includes(kind)}
              data-testid={`geometry-${kind}-toggle`}
              onChange={(event) => state.toggle(kind, event.target.checked)}
            />
            {kind === 'route' ? '경로 표시' : '영역 표시'}
          </label>
        ))}
      </div>
      {state.kinds.length > 0 && !state.eligible && (
        <p className="text-muted">지도를 14단계 이상 확대하면 표시됩니다.</p>
      )}
      {state.loading && (
        <p role="status" className="text-muted">
          경로·영역을 불러오는 중…
        </p>
      )}
      {state.error && (
        <div role="alert" className="text-error-text">
          <p>{state.error}</p>
          <button type="button" className="focus-ring min-h-9 underline" onClick={state.retry}>
            다시 불러오기
          </button>
        </div>
      )}
      {state.truncated && (
        <p role="status" className="text-muted">
          일부 경로·영역만 표시됩니다. 지도 범위를 좁혀주세요.
        </p>
      )}
      {state.features.length > 0 && (
        <details className="mt-1">
          <summary className="focus-ring min-h-9 cursor-pointer">
            경로·영역 목록 ({state.features.length})
          </summary>
          <ul className="max-h-40 overflow-y-auto">
            {state.features.map((feature) => (
              <li key={feature.feature_id}>
                <button
                  type="button"
                  className="focus-ring min-h-11 w-full rounded-sm px-1 text-left hover:bg-surface-soft"
                  data-testid="geometry-list-item"
                  data-feature-id={feature.feature_id}
                  onClick={() => state.select(feature, undefined, true)}
                >
                  {feature.name} · {feature.kind === 'route' ? '경로' : '영역'}
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

export function FeatureGeometryPopup({
  state,
  onOpenDetail,
}: {
  state: FeatureGeometryState;
  onOpenDetail: (id: string) => void;
}) {
  const selection = state.selection;
  if (!selection) return null;
  return (
    <Popup
      key={selection.revision}
      lngLat={selection.anchor}
      maxWidth="260px"
      closeButton={false}
      onClose={() => state.clearSelection(selection.revision)}
    >
      <div
        className="space-y-2"
        data-map-overlay=""
        data-testid="geometry-popup"
        data-feature-id={selection.feature.feature_id}
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-sm font-semibold text-ink">{selection.feature.name}</p>
            <p className="text-xs text-muted">
              {selection.feature.category_label ||
                (selection.feature.kind === 'route' ? '경로' : '영역')}
            </p>
          </div>
          <button
            type="button"
            aria-label="경로·영역 닫기"
            className="focus-ring text-xs text-muted hover:text-ink"
            onClick={() => state.clearSelection()}
          >
            닫기
          </button>
        </div>
        <button
          type="button"
          data-testid="geometry-detail-open"
          onClick={() => onOpenDetail(selection.feature.feature_id)}
          className="focus-ring min-h-11 w-full rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
        >
          상세보기
        </button>
      </div>
    </Popup>
  );
}
