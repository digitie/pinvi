/**
 * 지도 맞춤(fitBounds) 여백 — 지도 위 장소 검색 줄과 교통 정보 패널에 핀이 가리지 않게.
 *
 * 2026-11-02 prod e2e: 여행 지도가 사방 64px만 띄워, 가장 북쪽 장소(영월 고씨굴) 핀이 왼쪽 위 장소
 * 검색창 밑에 숨었다(데스크톱·모바일). 위쪽 여백을 검색 줄 아래로 내린다. fitBounds 여백은 핀의
 * 앵커(아래 꼭짓점)를 둘 자리이고 핀 머리는 그 위로 `markerHeight`만큼 솟으므로, 핀 높이도 더한다.
 * 오버레이가 지도보다 크면 fitBounds가 "Map cannot fit"으로 아무 일도 하지 않으므로 지도 높이의
 * 60%로 묶는다.
 *
 * 교통 정보 패널은 왼쪽 열(w-64)이다 — 데스크톱에선 지도 폭의 ~25%, 모바일에선 ~66%를 덮는다. 처음부터
 * 위쪽 여백에 넣으면 패널 밑에 핀이 없을 때도 지도 전체 폭에서 그만큼을 버리므로, 맞춘 뒤 실제로
 * 패널 밑에 핀이 있을 때만 패널 아래까지 한 번 더 맞춘다(`pinBoxIntersects`).
 */

export const MAP_FIT_PADDING = 64;
/** 피할 영역(검색 입력 줄·패널) 아래와 핀 머리 사이 간격 — 입력 줄을 감싼 카드의 안쪽 여백·테두리(≈9px)를 넘는다. */
export const OVERLAY_GAP = 24;
const MAX_TOP_SHARE = 0.6;
/** 맞춤 여백을 뺀 뒤 핀을 펼칠 최소 세로 폭(px). */
export const MIN_FIT_SPAN = 120;
/** 낮은 지도에서 아래 여백을 줄일 하한(px). */
export const MIN_EDGE_PADDING = 8;
/** 어떤 경우에도 fitBounds에 남기는 세로 폭(px) — 0 이하면 maplibre가 맞춤을 거부한다. */
const MIN_HARD_SPAN = 16;

export interface VerticalRect {
  top: number;
  bottom: number;
  height: number;
}

export interface BoxRect extends VerticalRect {
  left: number;
  right: number;
}

/**
 * 맞춤 여백이 늘 피할 영역. 스택 안 `[data-map-fit-anchor]`(장소 검색 입력 줄)를 쓰고, 없으면
 * 스택의 첫 자식(항상 보이는 검색 카드)을 쓴다. 잠깐 펼쳐지는 검색 결과 목록·오류는 넣지 않는다 —
 * 펼쳐진 순간에 다시 맞추면 위쪽 60%를 버리게 된다.
 */
export function fitOverlayRect(stack: Element | null): VerticalRect | null {
  if (!stack) return null;
  const anchor = stack.querySelector('[data-map-fit-anchor]') ?? stack.firstElementChild;
  return anchor ? anchor.getBoundingClientRect() : null;
}

/**
 * 스택 안 경로/영역 컨트롤·교통 정보 패널(`[data-map-fit-panel]`)의 상시 부분. 잠깐 펼쳐지는 사건 목록
 * (`[data-map-fit-transient]`)은 아래 끝에서 뺀다.
 */
export function fitPanelRect(stack: Element | null): BoxRect | null {
  if (!stack) return null;
  const stackRect = stack.getBoundingClientRect();
  const rects = Array.from(stack.querySelectorAll('[data-map-fit-panel]')).flatMap(panel => {
    const rect = panel.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return [];
    const transient = panel.querySelector('[data-map-fit-transient]');
    let bottom = transient ? Math.min(rect.bottom, transient.getBoundingClientRect().top) : rect.bottom;
    if (stackRect.height > 0) bottom = Math.min(bottom, stackRect.bottom);
    return bottom > rect.top ? [{ left: rect.left, right: rect.right, top: rect.top, bottom }] : [];
  });
  if (rects.length === 0) return null;
  const top = Math.min(...rects.map(rect => rect.top));
  const bottom = Math.max(...rects.map(rect => rect.bottom));
  return {
    left: Math.min(...rects.map(rect => rect.left)),
    right: Math.max(...rects.map(rect => rect.right)),
    top, bottom, height: bottom - top,
  };
}

/** 앵커(아래 꼭짓점)가 `(anchorX, anchorY)`인 핀 상자가 `rect`와 겹치는가. */
export function pinBoxIntersects(
  anchorX: number,
  anchorY: number,
  pinWidth: number,
  pinHeight: number,
  rect: BoxRect,
): boolean {
  const left = anchorX - pinWidth / 2;
  const right = anchorX + pinWidth / 2;
  const top = anchorY - pinHeight;
  return left < rect.right && right > rect.left && top < rect.bottom && anchorY > rect.top;
}

export interface FitPadding {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

/**
 * @param markerHeight 핀이 앵커 위로 솟는 높이(px). 핀 머리까지 오버레이 아래에 오게 한다.
 */
export function fitPaddingForOverlay(
  surface: VerticalRect | null,
  overlay: VerticalRect | null,
  markerHeight = 0,
  bottomOverlay: VerticalRect | null = null,
): FitPadding {
  const padding = {
    top: MAP_FIT_PADDING,
    right: MAP_FIT_PADDING,
    bottom: MAP_FIT_PADDING,
    left: MAP_FIT_PADDING,
  };
  if (!surface || surface.height <= 0) return padding;
  let topClearance = 0;
  if (overlay && overlay.height > 0) {
    const clearance = Math.round(
      overlay.bottom - surface.top + Math.max(0, markerHeight) + OVERLAY_GAP,
    );
    topClearance = Math.min(clearance, Math.round(surface.height * MAX_TOP_SHARE));
    padding.top = Math.max(MAP_FIT_PADDING, topClearance);
  }
  if (bottomOverlay && bottomOverlay.height > 0) {
    // 핀 꼬리를 칩 위에 두고, 상하 여백이 지도 높이를 소진하지 않게 제한한다.
    const clearance = Math.round(surface.bottom - bottomOverlay.top + OVERLAY_GAP);
    const cap = Math.max(MAP_FIT_PADDING, surface.height - padding.top - 1);
    padding.bottom = Math.max(MAP_FIT_PADDING, Math.min(clearance, cap));
  }
  // 낮은 지도(낮은 창·높은 상단 패널): 여백이 맞춤 폭을 거의 다 먹으면 (1) 아래 여백부터 줄이고
  // (2) 위 여백은 오버레이 clearance·핀 머리 높이까지만 줄인다 — 그 아래로는 맞춤 폭을 줄인다.
  // (3) 그래도 fitBounds에 남길 폭이 없을 때만 위 여백을 핀 높이까지 깎는다(#704 후속).
  const span = () => surface.height - padding.top - padding.bottom;
  if (span() < MIN_FIT_SPAN) {
    padding.bottom = Math.max(
      Math.min(padding.bottom, MIN_EDGE_PADDING),
      padding.bottom - (MIN_FIT_SPAN - span()),
    );
  }
  if (span() < MIN_FIT_SPAN) {
    const floor = Math.min(padding.top, Math.max(Math.max(0, markerHeight) + OVERLAY_GAP, topClearance));
    padding.top = Math.max(floor, padding.top - (MIN_FIT_SPAN - span()));
  }
  if (span() < MIN_HARD_SPAN) {
    padding.top = Math.max(
      Math.min(padding.top, Math.max(0, markerHeight)),
      surface.height - padding.bottom - MIN_HARD_SPAN,
    );
    if (span() < MIN_HARD_SPAN) {
      padding.bottom = Math.max(0, surface.height - padding.top - MIN_HARD_SPAN);
    }
  }
  return padding;
}

/** 이 지도와 같은 경계 안에 있는 하단 통계 칩의 실제 표시 상자. */
export function fitBottomRect(container: Element): BoxRect | null {
  const chip = container.closest('[data-map-fit-boundary]')?.querySelector('[data-map-fit-bottom]');
  if (!chip) return null;
  const rect = chip.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0 ? rect : null;
}
