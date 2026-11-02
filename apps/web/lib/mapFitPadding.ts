/**
 * 지도 맞춤(fitBounds) 여백 — 지도 위 오버레이(장소 검색·교통 정보 스택)에 핀이 가리지 않게.
 *
 * 2026-11-02 prod e2e: 여행 지도가 사방 64px만 띄워, 가장 북쪽 장소(영월 고씨굴) 핀이 왼쪽 위 장소
 * 검색창 밑에 숨었다(데스크톱·모바일). 위쪽 여백을 오버레이 아래로 내린다. fitBounds 여백은 핀의
 * 앵커(아래 꼭짓점)를 둘 자리이고 핀 머리는 그 위로 `markerHeight`만큼 솟으므로, 핀 높이도 더한다.
 * 오버레이가 지도보다 크면 fitBounds가 "Map cannot fit"으로 아무 일도 하지 않으므로 지도 높이의
 * 60%로 묶는다.
 */

export const MAP_FIT_PADDING = 64;
/** 오버레이 아래와 핀 머리 사이 간격. */
export const OVERLAY_GAP = 16;
const MAX_TOP_SHARE = 0.6;

interface VerticalRect {
  top: number;
  bottom: number;
  height: number;
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
): FitPadding {
  const padding = {
    top: MAP_FIT_PADDING,
    right: MAP_FIT_PADDING,
    bottom: MAP_FIT_PADDING,
    left: MAP_FIT_PADDING,
  };
  if (!surface || surface.height <= 0 || !overlay || overlay.height <= 0) return padding;
  const clearance = Math.round(overlay.bottom - surface.top + Math.max(0, markerHeight) + OVERLAY_GAP);
  const cap = Math.round(surface.height * MAX_TOP_SHARE);
  padding.top = Math.max(MAP_FIT_PADDING, Math.min(clearance, cap));
  return padding;
}
