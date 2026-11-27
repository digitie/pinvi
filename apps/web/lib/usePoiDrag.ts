'use client';

import type { PoiMoveTarget } from '@pinvi/domain';
import { type DragEvent, useCallback, useMemo, useRef, useState } from 'react';

/** 끌고 있는 장소 — 어느 일자에서 출발했는지까지. */
export interface PoiDragSource {
  poiId: string;
  dayIndex: number;
}

/**
 * 일정 패널 전체가 함께 쓰는 장소 끌어 놓기 상태(일자 사이 이동, 2026-11-27 소유자 요청).
 *
 * HTML5 DnD를 그대로 쓴다. 끄는 장소는 React 상태(+ ref)로 들고 다녀 다른 일자의 목록·접힌 일자
 * 줄도 같은 끌기를 받는다. `dataTransfer`에는 Firefox가 끌기를 시작하도록 장소 id만 넣는다.
 * 장소 끌기가 아닌 끌기(파일 등)는 건드리지 않는다 — `preventDefault`를 하지 않아 첨부 드롭이 그대로다.
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

/** 행 위쪽 절반이면 그 행 앞, 아래쪽 절반이면 그 행 뒤. */
export function dropPlacement(event: DragEvent): 'before' | 'after' {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
  return event.clientY < rect.top + rect.height / 2 ? 'before' : 'after';
}

function sameTarget(a: PoiMoveTarget | null, b: PoiMoveTarget | null): boolean {
  return a?.dayIndex === b?.dayIndex && a?.beforePoiId === b?.beforePoiId;
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

  const start = useCallback((next: PoiDragSource, event: DragEvent) => {
    sourceRef.current = next;
    setSource(next);
    setTarget(null);
    const transfer = event.dataTransfer;
    if (transfer) {
      transfer.effectAllowed = 'move';
      try {
        transfer.setData('text/plain', next.poiId);
      } catch {
        // 일부 합성 이벤트의 읽기 전용 dataTransfer — 끌기 상태는 ref가 정본이다.
      }
    }
  }, []);

  const over = useCallback((next: PoiMoveTarget, event: DragEvent) => {
    if (sourceRef.current == null) return;
    event.preventDefault();
    event.stopPropagation();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
    setTarget((current) => (sameTarget(current, next) ? current : next));
  }, []);

  const leave = useCallback((dayIndex: number, event: DragEvent) => {
    if (sourceRef.current == null) return;
    const related = event.relatedTarget as Node | null;
    if (related && (event.currentTarget as Node).contains(related)) return;
    setTarget((current) => (current?.dayIndex === dayIndex ? null : current));
  }, []);

  const drop = useCallback(
    (next: PoiMoveTarget, event: DragEvent) => {
      const dragged = sourceRef.current;
      if (dragged == null) return;
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
