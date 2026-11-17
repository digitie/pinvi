'use client';

import { useEffect } from 'react';
import type { MapLibreMap } from '@/components/map/vworldPrimitives';

/**
 * 지도 선택 popup이 지도 위 오버레이(검색·레이어 패널·내 위치 버튼)를 덮지 않게 지도를 살짝 민다 —
 * 구글 지도 InfoWindow의 autoPan과 같은 동작.
 *
 * popup은 앱 패널(z10)보다 위(z20, `.pinvi-map-popup`)라 닫기·상세보기가 패널에 막히지 않는다. 대신 popup이
 * 패널 자리까지 자라면 패널을 덮는다 — 2026-11-17 mobile NEAR-005: '서울역' 검색 선택 popup이 날씨 줄만큼
 * 자라 폭 390 화면의 '주유소' 체크박스를 덮었다(`maplibregl-popup-content … intercepts pointer events`).
 * 쌓임 순서를 뒤집으면 반대로 패널이 popup을 막으므로, 둘이 겹치지 않게 지도를 옮긴다.
 */

export interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface PanShift {
  /** popup(지도 내용)을 오른쪽으로 옮길 px. 음수면 왼쪽. */
  dx: number;
  /** popup(지도 내용)을 아래로 옮길 px. 음수면 위. */
  dy: number;
}

/** 오버레이와 popup 사이에 남길 간격(px). */
export const POPUP_OVERLAY_GAP = 8;
/** 이보다 작은 이동은 하지 않는다(반올림 흔들림으로 pan이 되풀이되지 않게). */
const MIN_SHIFT_PX = 2;

const NO_SHIFT: PanShift = { dx: 0, dy: 0 };

function overlaps(a: Rect, b: Rect, gap: number): boolean {
  return (
    a.left < b.right + gap &&
    a.right + gap > b.left &&
    a.top < b.bottom + gap &&
    a.bottom + gap > b.top
  );
}

function shifted(rect: Rect, { dx, dy }: PanShift): Rect {
  return {
    left: rect.left + dx,
    right: rect.right + dx,
    top: rect.top + dy,
    bottom: rect.bottom + dy,
  };
}

function inside(rect: Rect, surface: Rect): boolean {
  return (
    rect.left >= surface.left - 0.5 &&
    rect.right <= surface.right + 0.5 &&
    rect.top >= surface.top - 0.5 &&
    rect.bottom <= surface.bottom + 0.5
  );
}

/**
 * popup을 오버레이와 겹치지 않게 하는 가장 작은 이동. 겹치지 않으면 0.
 *
 * 겹친 오버레이마다 아래·위·오른쪽·왼쪽으로 비켜 서는 네 후보를 만들고, 옮긴 popup이 지도 안에 남고 어떤
 * 오버레이와도 겹치지 않는 후보 중 이동 거리가 가장 짧은 것을 고른다. 그런 후보가 없으면(지도가 너무 작다)
 * 첫 오버레이 아래로 비켜 서되 지도 밖으로는 밀지 않는다 — 최소한 위쪽 검색·레이어 패널은 비운다.
 */
export function popupClearanceShift(
  popup: Rect,
  overlays: readonly Rect[],
  surface: Rect,
  gap = POPUP_OVERLAY_GAP,
): PanShift {
  const hits = overlays.filter((overlay) => overlaps(popup, overlay, gap));
  if (hits.length === 0) return NO_SHIFT;

  const candidates: PanShift[] = hits.flatMap((overlay) => [
    { dx: 0, dy: overlay.bottom + gap - popup.top },
    { dx: 0, dy: overlay.top - gap - popup.bottom },
    { dx: overlay.right + gap - popup.left, dy: 0 },
    { dx: overlay.left - gap - popup.right, dy: 0 },
  ]);
  const valid = candidates
    .filter((shift) => {
      const moved = shifted(popup, shift);
      return inside(moved, surface) && !overlays.some((overlay) => overlaps(moved, overlay, gap));
    })
    .sort((a, b) => Math.hypot(a.dx, a.dy) - Math.hypot(b.dx, b.dy));
  const best = valid[0];
  if (best) return best;

  const first = hits[0]!;
  const room = Math.max(0, surface.bottom - popup.bottom);
  return { dx: 0, dy: Math.max(0, Math.min(first.bottom + gap - popup.top, room)) };
}

function toRect(rect: DOMRect): Rect {
  return { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom };
}

/**
 * 지도 컨테이너 위에 보이는 오버레이(`[data-map-overlay]`) 상자. popup 자신과 popup 안의 요소, 크기 0인
 * 요소는 뺀다. 오버레이 안의 오버레이(레이어 패널 ⊂ 왼쪽 위 스택)는 바깥 것만 센다.
 */
export function overlayRects(root: ParentNode, popup: Element): Rect[] {
  const all = Array.from(root.querySelectorAll('[data-map-overlay]')).filter(
    (el) => !popup.contains(el) && !el.contains(popup),
  );
  return all
    .filter((el) => !all.some((other) => other !== el && other.contains(el)))
    .flatMap((el) => {
      const rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0 ? [toRect(rect)] : [];
    });
}

/** popup 하나에 허용하는 자동 이동 횟수 — 오버레이가 pan에 따라 커지는 이상한 경우에도 되풀이하지 않는다. */
const MAX_AUTO_PANS = 3;

/**
 * 열린 popup이 오버레이를 덮으면 지도를 옮긴다.
 *
 * - popup이 열린 직후, 크기가 바뀔 때(날씨·상세가 늦게 붙는다), 프로그램 카메라 이동(검색 flyTo)이 끝났을 때
 *   확인한다. 카메라가 움직이는 중에는 옮기지 않는다(flyTo를 끊지 않게) — 끝난 뒤 moveend에서 다시 본다.
 * - 사용자가 지도를 직접 끌거나 확대하면 그 popup에 대해서는 다시 옮기지 않는다(손을 가로채지 않는다).
 *
 * @param getMap 지도 인스턴스(없으면 아무것도 하지 않는다).
 * @param content popup 안 내용 요소(callback ref로 받은 것). `.maplibregl-popup` 조상을 잰다.
 * @param overlayRoot 오버레이를 찾을 범위(지도 화면 래퍼). 없으면 지도 컨테이너의 부모.
 */
export function usePopupClearOfOverlays(
  getMap: () => MapLibreMap | null,
  content: HTMLElement | null,
  overlayRoot?: HTMLElement | null,
): void {
  useEffect(() => {
    const map = getMap();
    if (!map || !content) return;
    let pans = 0;
    let userMoved = false;
    let frame = 0;

    const check = () => {
      frame = 0;
      if (userMoved || pans >= MAX_AUTO_PANS || map.isMoving()) return;
      const popupEl = content.closest('.maplibregl-popup') ?? content;
      const container = map.getContainer();
      const root = overlayRoot ?? container.parentElement ?? container;
      const shift = popupClearanceShift(
        toRect(popupEl.getBoundingClientRect()),
        overlayRects(root, popupEl),
        toRect(container.getBoundingClientRect()),
      );
      if (Math.abs(shift.dx) < MIN_SHIFT_PX && Math.abs(shift.dy) < MIN_SHIFT_PX) return;
      pans += 1;
      // panBy는 "보는 창"을 옮긴다 — 내용을 아래로 dy만큼 내리려면 창을 위로(-dy) 옮긴다.
      map.panBy([-shift.dx, -shift.dy], { duration: 200 });
    };
    const schedule = () => {
      if (frame) cancelAnimationFrame(frame);
      frame = requestAnimationFrame(check);
    };
    const onUserMove = (event?: { originalEvent?: unknown }) => {
      if (event?.originalEvent != null) userMoved = true;
    };
    const onMoveEnd = (event?: { originalEvent?: unknown }) => {
      if (event?.originalEvent != null) {
        userMoved = true;
        return;
      }
      schedule();
    };

    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(schedule);
    observer?.observe(content);
    map.on('dragstart', onUserMove);
    map.on('zoomstart', onUserMove);
    map.on('moveend', onMoveEnd);
    schedule();
    return () => {
      if (frame) cancelAnimationFrame(frame);
      observer?.disconnect();
      map.off('dragstart', onUserMove);
      map.off('zoomstart', onUserMove);
      map.off('moveend', onMoveEnd);
    };
  }, [getMap, content, overlayRoot]);
}
