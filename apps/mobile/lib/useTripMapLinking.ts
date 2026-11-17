import { useCallback, useMemo, useRef, useState } from 'react';
import type { HostInstance, ScrollViewInstance } from 'react-native';
import type { TripMapPoint } from '@pinvi/domain';
import type { TripMapFocus } from '../components/TripMap';

/**
 * 여행 지도 ↔ 일정 목록 연동 상태(여행 상세·공유 화면 공용).
 *
 * - 목록 → 지도: 그 장소를 고르고 지도 가운데로(접혀 있으면 펼치며 그 장소로 연다). 같은 장소를 다시 눌러도.
 * - 지도 → 목록: 그 줄을 강조하고 보이는 곳까지 스크롤한다(지도 시점은 그대로).
 */
export function useTripMapLinking(points: readonly TripMapPoint[]) {
  const [mapCollapsed, setMapCollapsed] = useState(false);
  const [selectedPoiId, setSelectedPoiId] = useState<string | null>(null);
  const [focus, setFocus] = useState<TripMapFocus | null>(null);
  const scrollRef = useRef<ScrollViewInstance>(null);
  const contentRef = useRef<HostInstance>(null);
  const rowRefs = useRef(new Map<string, HostInstance>());
  const pointById = useMemo(() => new Map(points.map((p) => [p.poiId, p])), [points]);

  const selectFromList = useCallback(
    (poiId: string) => {
      setSelectedPoiId(poiId);
      if (!pointById.has(poiId)) return;
      setMapCollapsed(false);
      setFocus((prev) => ({ poiId, seq: (prev?.seq ?? 0) + 1 }));
    },
    [pointById],
  );

  const selectFromMap = useCallback((poiId: string) => {
    setSelectedPoiId(poiId);
    const row = rowRefs.current.get(poiId);
    const content = contentRef.current;
    if (!row || !content) return;
    row.measureLayout(
      content,
      (_x, y) => scrollRef.current?.scrollTo({ y: Math.max(0, y - 12), animated: true }),
      () => undefined,
    );
  }, []);

  const registerRow = useCallback((poiId: string, node: HostInstance | null) => {
    if (node) rowRefs.current.set(poiId, node);
    else rowRefs.current.delete(poiId);
  }, []);

  const toggleMap = useCallback(() => setMapCollapsed((prev) => !prev), []);

  return {
    pointById,
    mapCollapsed,
    toggleMap,
    selectedPoiId,
    focus,
    selectFromList,
    selectFromMap,
    registerRow,
    scrollRef,
    contentRef,
  };
}
