import type { VWorldViewPadding } from 'vworld-map-rn';

/** MapLibre GL `fitBounds` padding — 숫자 하나 또는 네 면 모두를 가진 객체. */
export type MapLibrePadding = number | { top: number; right: number; bottom: number; left: number };

/**
 * `VWorldMapHandle.fitBounds`의 `paddingPx`(vworld-map-rn 1.0.2부터 숫자 또는 면별 객체, 빠진 면은 0)를
 * MapLibre GL padding으로 바꾼다. 웹 shim이 native와 같은 의미로 맞추게 한다.
 */
export function toMapLibrePadding(padding: VWorldViewPadding | undefined): MapLibrePadding | undefined {
  if (padding === undefined || typeof padding === 'number') return padding;
  return {
    top: padding.top ?? 0,
    right: padding.right ?? 0,
    bottom: padding.bottom ?? 0,
    left: padding.left ?? 0,
  };
}
