import { describe, expect, it } from 'vitest';
import {
  overlayRects,
  popupClearanceShift,
  POPUP_OVERLAY_GAP,
  type Rect,
} from '@/lib/popupClearance';

/**
 * 2026-11-17 mobile NEAR-005: '서울역' 검색 선택 popup이 날씨 줄만큼 자라 폭 390 화면의 '주유소' 체크박스를
 * 덮었다. popup은 패널보다 위(z20)라 겹치면 패널을 막는다 — 겹치지 않게 지도를 미는 이동량을 잠근다.
 */
const rect = (left: number, top: number, width: number, height: number): Rect => ({
  left,
  top,
  right: left + width,
  bottom: top + height,
});

// 390x844 모바일 — 지도는 탭바 위까지(0..788), 왼쪽 위 스택(검색+레이어 패널)은 8..328 × 8..150.
const MOBILE_SURFACE = rect(0, 0, 390, 788);
const MOBILE_STACK = rect(8, 8, 320, 142);
const MY_LOCATION = rect(334, 704, 44, 44);

describe('popupClearanceShift', () => {
  it('겹치지 않으면 옮기지 않는다', () => {
    const popup = rect(70, 300, 250, 180);
    expect(popupClearanceShift(popup, [MOBILE_STACK, MY_LOCATION], MOBILE_SURFACE)).toEqual({
      dx: 0,
      dy: 0,
    });
  });

  it('popup이 왼쪽 위 레이어 패널을 덮으면(390px) 패널 아래로 내린다', () => {
    // 지도 가운데 장소 위로 자란 popup의 위 끝이 패널(아래 끝 150) 안 120에 있다.
    const popup = rect(70, 120, 250, 260);
    const shift = popupClearanceShift(popup, [MOBILE_STACK, MY_LOCATION], MOBILE_SURFACE);
    expect(shift).toEqual({ dx: 0, dy: MOBILE_STACK.bottom + POPUP_OVERLAY_GAP - popup.top });
    const moved = rect(popup.left + shift.dx, popup.top + shift.dy, 250, 260);
    expect(moved.top).toBeGreaterThanOrEqual(MOBILE_STACK.bottom + POPUP_OVERLAY_GAP);
  });

  it('데스크톱에서는 더 짧은 쪽(오른쪽)으로 비킨다', () => {
    const surface = rect(0, 0, 1440, 840);
    const stack = rect(12, 12, 320, 160);
    // 패널 오른쪽 끝(332)을 20px 넘게 덮지만 아래로는 100px 넘게 내려야 한다.
    const popup = rect(320, 60, 260, 200);
    const shift = popupClearanceShift(popup, [stack], surface);
    expect(shift).toEqual({ dx: stack.right + POPUP_OVERLAY_GAP - popup.left, dy: 0 });
  });

  it('비킨 자리가 다른 오버레이(내 위치 버튼)와 겹치면 그 후보는 버린다', () => {
    const surface = rect(0, 0, 390, 788);
    // 아래로 내리면 내 위치 버튼과 겹치는 높이의 popup — 위로 비켜야 한다.
    const popup = rect(140, 560, 220, 150);
    const shift = popupClearanceShift(popup, [MY_LOCATION], surface);
    const moved = rect(popup.left + shift.dx, popup.top + shift.dy, 220, 150);
    expect(moved.bottom + POPUP_OVERLAY_GAP).toBeLessThanOrEqual(MY_LOCATION.top + 0.001);
  });

  it('지도가 너무 작으면 지도 밖으로 밀지 않는다(위 패널만 최대한 비운다)', () => {
    const surface = rect(0, 0, 390, 300);
    const popup = rect(20, 100, 340, 180);
    const shift = popupClearanceShift(popup, [MOBILE_STACK], surface);
    expect(shift.dx).toBe(0);
    expect(shift.dy).toBeGreaterThanOrEqual(0);
    expect(popup.bottom + shift.dy).toBeLessThanOrEqual(surface.bottom);
  });
});

describe('overlayRects', () => {
  function box(el: HTMLElement, r: Rect) {
    el.getBoundingClientRect = () =>
      ({
        ...r,
        x: r.left,
        y: r.top,
        width: r.right - r.left,
        height: r.bottom - r.top,
        toJSON: () => r,
      }) as DOMRect;
  }

  it('바깥 오버레이만 세고, popup 안·크기 0인 요소는 뺀다', () => {
    const root = document.createElement('div');
    const stack = document.createElement('div');
    stack.setAttribute('data-map-overlay', '');
    const panel = document.createElement('section');
    panel.setAttribute('data-map-overlay', '');
    stack.append(panel);
    const hidden = document.createElement('div');
    hidden.setAttribute('data-map-overlay', '');
    const popup = document.createElement('div');
    const insidePopup = document.createElement('div');
    insidePopup.setAttribute('data-map-overlay', '');
    popup.append(insidePopup);
    root.append(stack, hidden, popup);
    box(stack, MOBILE_STACK);
    box(panel, rect(8, 60, 320, 90));
    box(hidden, rect(0, 0, 0, 0));
    box(insidePopup, rect(100, 100, 50, 50));

    expect(overlayRects(root, popup)).toEqual([MOBILE_STACK]);
  });
});
