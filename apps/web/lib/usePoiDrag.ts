'use client';

import type { PoiMoveTarget } from '@pinvi/domain';
import { type DragEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';

/** 끌고 있는 장소 — 어느 일자에서 출발했는지까지. */
export interface PoiDragSource {
  poiId: string;
  dayIndex: number;
}

/**
 * 장소 끌기 전용 dataTransfer 형식. Firefox는 무엇이든 `setData`해야 끌기를 시작하는데, `text/plain`이면
 * 입력란에 놓을 때 장소 id가 글자로 들어간다 — 입력란이 받지 않는 전용 형식을 쓴다.
 */
export const POI_DRAG_MIME = 'application/x-pinvi-poi';

/**
 * 일정 패널 전체가 함께 쓰는 장소 끌어 놓기 상태(일자 사이 이동, 2026-11-27 소유자 요청).
 *
 * HTML5 DnD를 그대로 쓴다. 끄는 장소는 React 상태(+ ref)로 들고 다녀 다른 일자의 목록·접힌 일자
 * 줄도 같은 끌기를 받는다. 장소 끌기가 아닌 끌기(글자·링크·파일)는 `POI_DRAG_MIME`이 없어 건드리지
 * 않는다 — `preventDefault`를 하지 않으므로 그대로 지나간다.
 */
export interface PoiDrag {
  source: PoiDragSource | null;
  /** 지금 놓으면 갈 자리(표시용). */
  target: PoiMoveTarget | null;
  start: (source: PoiDragSource, event: DragEvent) => void;
  over: (target: PoiMoveTarget, event: DragEvent) => void;
  /** 일자 영역을 벗어났다 — 그 일자를 가리키던 표시를 지운다. */
  leave: (dayIndex: number, event: DragEvent) => void;
  drop: (target: PoiMoveTarget, event: DragEvent) => void;
  end: () => void;
}

/**
 * 세로로 놓인 행들 사이 어디에 놓는가 — 포인터보다 가운데가 아래인 첫 행 앞(그런 행이 없으면 맨 끝).
 * 행 사이 여백도 가까운 틈으로 읽어, 여백에서 놓아도 엉뚱한 자리(일자 맨 끝)로 가지 않는다.
 */
export function rowInsertIndex(rows: ArrayLike<Element>, clientY: number): number {
  for (let index = 0; index < rows.length; index += 1) {
    const rect = rows[index]!.getBoundingClientRect();
    if (clientY < rect.top + rect.height / 2) return index;
  }
  return rows.length;
}

function sameTarget(a: PoiMoveTarget | null, b: PoiMoveTarget | null): boolean {
  return a?.dayIndex === b?.dayIndex && a?.beforePoiId === b?.beforePoiId;
}

/** 이 끌기가 장소 끌기인가 — 형식 목록이 있으면 전용 형식이 있어야 한다(합성 이벤트는 목록이 없다). */
function carriesPoi(event: DragEvent): boolean {
  const types = event.dataTransfer?.types;
  if (!types || types.length === 0) return true;
  return Array.from(types).includes(POI_DRAG_MIME);
}

export function usePoiDrag(
  onMove: (source: PoiDragSource, target: PoiMoveTarget) => void,
): PoiDrag {
  const sourceRef = useRef<PoiDragSource | null>(null);
  const [source, setSource] = useState<PoiDragSource | null>(null);
  const [target, setTarget] = useState<PoiMoveTarget | null>(null);

  const end = useCallback(() => {
    sourceRef.current = null;
    setSource(null);
    setTarget(null);
  }, []);

  // 끄는 행이 끌기 도중 사라지면(다른 사람이 옮기거나 지움) 그 행의 dragend를 React가 받지 못한다.
  // 패널 밖에 놓거나 취소해도 끝나도록 window에서도 끝을 받는다(놓을 자리의 drop은 전파를 멈추고 직접 끝낸다).
  useEffect(() => {
    if (source == null) return;
    window.addEventListener('dragend', end);
    window.addEventListener('drop', end);
    return () => {
      window.removeEventListener('dragend', end);
      window.removeEventListener('drop', end);
    };
  }, [source, end]);

  const start = useCallback((next: PoiDragSource, event: DragEvent) => {
    sourceRef.current = next;
    setSource(next);
    setTarget(null);
    const transfer = event.dataTransfer;
    if (transfer) {
      transfer.effectAllowed = 'move';
      try {
        transfer.setData(POI_DRAG_MIME, next.poiId);
      } catch {
        // 일부 합성 이벤트의 읽기 전용 dataTransfer — 끌기 상태는 ref가 정본이다.
      }
    }
  }, []);

  const over = useCallback((next: PoiMoveTarget, event: DragEvent) => {
    if (sourceRef.current == null || !carriesPoi(event)) return;
    event.preventDefault();
    event.stopPropagation();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
    setTarget((current) => (sameTarget(current, next) ? current : next));
  }, []);

  const leave = useCallback((dayIndex: number, event: DragEvent) => {
    if (sourceRef.current == null) return;
    const related = event.relatedTarget as Node | null;
    // Safari는 drag 이벤트의 relatedTarget을 주지 않는다 — 모르면 지우지 않는다(다음 dragover가 바로잡는다).
    if (!related || (event.currentTarget as Node).contains(related)) return;
    setTarget((current) => (current?.dayIndex === dayIndex ? null : current));
  }, []);

  const drop = useCallback(
    (next: PoiMoveTarget, event: DragEvent) => {
      const dragged = sourceRef.current;
      if (dragged == null || !carriesPoi(event)) return;
      event.preventDefault();
      event.stopPropagation();
      end();
      onMove(dragged, next);
    },
    [end, onMove],
  );

  return useMemo(
    () => ({ source, target, start, over, leave, drop, end }),
    [source, target, start, over, leave, drop, end],
  );
}
