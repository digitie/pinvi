'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, featureApi } from '@pinvi/api-client';
import type { FeaturesInBoundsResponse } from '@pinvi/schemas';
import type { MapLibreMap } from 'vworld-map-web';
import { apiClient } from '@/lib/api';
import { isAbortError } from '@/lib/abort';
import { boundsToBbox, clampZoom } from '@/lib/featureBounds';
import {
  geometryBounds,
  geometryQueryKey,
  geometryZoomEligible,
  isGeometryFeature,
  type GeometryFeature,
  type GeometryKind,
} from '@/lib/featureGeometry';

const EMPTY: GeometryFeature[] = [];
const TTL_MS = 60_000;
const CACHE_MAX = 32;
const DEBOUNCE_MS = 250;
type Viewport = { bbox: string; zoom: number; eligible: boolean };
type Result = { key: string; data?: FeaturesInBoundsResponse; error?: string; loading: boolean };
export type GeometrySelection = { feature: GeometryFeature; anchor: [number, number] };

export function useFeatureGeometry({
  active,
  hiddenFeatureIds,
  category,
  onSelect,
}: {
  active: boolean;
  hiddenFeatureIds?: ReadonlySet<string>;
  category?: string;
  onSelect?: (feature: GeometryFeature) => void;
}) {
  const [kinds, setKinds] = useState<GeometryKind[]>([]);
  const [viewport, setViewport] = useState<Viewport | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [selection, setSelection] = useState<GeometrySelection | null>(null);
  const [reload, setReload] = useState(0);
  const mapRef = useRef<MapLibreMap | null>(null);
  const generation = useRef(0);
  const abort = useRef<AbortController | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cache = useRef(new Map<string, { at: number; data: FeaturesInBoundsResponse }>());

  const cancel = useCallback(() => {
    generation.current += 1;
    abort.current?.abort();
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const onViewportChange = useCallback(
    (map: MapLibreMap) => {
      // 같은 cache key 또는 확대 기준 밖으로 가더라도 이전 응답을 먼저 무효화한다.
      cancel();
      mapRef.current = map;
      const rawZoom = map.getZoom();
      setViewport({
        bbox: boundsToBbox(map.getBounds(), rawZoom),
        zoom: clampZoom(rawZoom),
        eligible: geometryZoomEligible(rawZoom),
      });
    },
    [cancel],
  );

  const toggle = useCallback(
    (kind: GeometryKind, enabled: boolean) => {
      cancel();
      setKinds((current) =>
        enabled
          ? [...current.filter((item) => item !== kind), kind]
          : current.filter((item) => item !== kind),
      );
      if (!enabled) setSelection((current) => (current?.feature.kind === kind ? null : current));
    },
    [cancel],
  );

  const query = useMemo(() => {
    if (!active || !viewport?.eligible || kinds.length === 0) return null;
    return {
      bbox: viewport.bbox,
      zoom: viewport.zoom,
      kinds,
      category,
      key: geometryQueryKey(viewport.bbox, viewport.zoom, kinds, category),
    };
  }, [active, viewport, kinds, category]);

  useEffect(() => {
    cancel();
    if (!query) return;
    const requestId = generation.current;
    const controller = new AbortController();
    abort.current = controller;
    timer.current = setTimeout(async () => {
      const cached = cache.current.get(query.key);
      if (cached && Date.now() - cached.at < TTL_MS) {
        if (generation.current === requestId)
          setResult({ key: query.key, data: cached.data, loading: false });
        return;
      }
      setResult((current) => ({
        key: query.key,
        data: current?.key === query.key ? current.data : undefined,
        loading: true,
      }));
      try {
        const data = await featureApi(apiClient).inBounds(
          {
            bbox: query.bbox,
            zoom: query.zoom,
            kinds: query.kinds,
            category: query.category,
            includeGeometry: true,
            limit: 100,
          },
          { signal: controller.signal },
        );
        if (requestId !== generation.current || controller.signal.aborted) return;
        cache.current.delete(query.key);
        cache.current.set(query.key, { at: Date.now(), data });
        while (cache.current.size > CACHE_MAX) {
          const oldest = cache.current.keys().next().value;
          if (oldest === undefined) break;
          cache.current.delete(oldest);
        }
        setResult({ key: query.key, data, loading: false });
      } catch (error) {
        if (isAbortError(error) || requestId !== generation.current || controller.signal.aborted)
          return;
        setResult({
          key: query.key,
          loading: false,
          error:
            error instanceof ApiError ? error.message : '경로·영역 정보를 불러오지 못했습니다.',
        });
      }
    }, DEBOUNCE_MS);
    return cancel;
  }, [query, reload, cancel]);

  useEffect(() => cancel, [cancel]);

  const data = query && result?.key === query.key ? result : null;
  const items = data?.data?.items;
  const features = useMemo(() => {
    if (!query || !items) return EMPTY;
    return items
      .filter(isGeometryFeature)
      .filter(
        (feature) => kinds.includes(feature.kind) && !hiddenFeatureIds?.has(feature.feature_id),
      );
  }, [query, items, kinds, hiddenFeatureIds]);

  const selectionAllowed =
    active &&
    viewport?.eligible &&
    selection &&
    kinds.includes(selection.feature.kind) &&
    !hiddenFeatureIds?.has(selection.feature.feature_id);
  if (selection && !selectionAllowed) setSelection(null);

  const select = useCallback(
    (feature: GeometryFeature, anchor?: [number, number], focus = false) => {
      if (
        !active ||
        !viewport?.eligible ||
        !kinds.includes(feature.kind) ||
        hiddenFeatureIds?.has(feature.feature_id)
      )
        return;
      const bounds = geometryBounds(feature.geometry);
      if (!bounds) return;
      if (focus && mapRef.current) {
        const camera = mapRef.current.cameraForBounds(bounds, { padding: 48, maxZoom: 16 });
        if (camera) {
          mapRef.current.easeTo({
            ...camera,
            zoom: Math.max(14, camera.zoom ?? 14),
            duration: 250,
          });
        }
      }
      onSelect?.(feature);
      setSelection({
        feature,
        anchor: anchor ?? [(bounds[0][0] + bounds[1][0]) / 2, (bounds[0][1] + bounds[1][1]) / 2],
      });
    },
    [active, viewport?.eligible, kinds, hiddenFeatureIds, onSelect],
  );
  const clearSelection = useCallback(() => setSelection(null), []);
  const retry = useCallback(() => {
    cancel();
    if (query) cache.current.delete(query.key);
    setReload((current) => current + 1);
  }, [cancel, query]);

  return {
    kinds,
    toggle,
    features,
    selection: selectionAllowed ? selection : null,
    select,
    clearSelection,
    onViewportChange,
    retry,
    eligible: viewport?.eligible ?? false,
    loading: Boolean(query && (!data || data.loading)),
    error: data?.error ?? null,
    truncated: data?.data?.truncated ?? false,
  };
}
export type FeatureGeometryState = ReturnType<typeof useFeatureGeometry>;
