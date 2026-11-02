import { describe, expect, it } from 'vitest';
import { MAP_FIT_PADDING, OVERLAY_GAP, fitPaddingForOverlay } from '@/lib/mapFitPadding';

// 2026-11-02 prod e2e — 여행 지도의 fitBounds가 사방 64px만 띄워, 가장 북쪽 장소(영월 고씨굴) 핀이
// 왼쪽 위 장소 검색창 밑에 숨었다(데스크톱·모바일). 위쪽 여백은 오버레이 아래로 내려야 한다.
const rect = (top: number, height: number) => ({ top, bottom: top + height, height });
const PIN_HEIGHT = 41; // 여행 지도 핀: size 27 × 1.5

describe('fitPaddingForOverlay', () => {
  it('오버레이가 없으면 사방 기본 여백', () => {
    expect(fitPaddingForOverlay(rect(200, 700), null, PIN_HEIGHT)).toEqual({
      top: MAP_FIT_PADDING,
      right: MAP_FIT_PADDING,
      bottom: MAP_FIT_PADDING,
      left: MAP_FIT_PADDING,
    });
  });

  it('핀 머리까지 오버레이 아래에 온다(여백은 핀 앵커=아래 꼭짓점 자리)', () => {
    // 데스크톱: 지도가 뷰포트 207px에서 시작, 검색 스택이 219~283px.
    const surface = rect(207, 693);
    const overlay = rect(219, 64);
    const padding = fitPaddingForOverlay(surface, overlay, PIN_HEIGHT);
    const pinHeadTop = surface.top + padding.top - PIN_HEIGHT;
    expect(pinHeadTop).toBeGreaterThanOrEqual(overlay.bottom);
    expect(padding.top).toBe(overlay.bottom - surface.top + PIN_HEIGHT + OVERLAY_GAP);
    expect(padding.bottom).toBe(MAP_FIT_PADDING);
  });

  it('모바일 재현값: 오버레이 80~144px, 지도 0px부터 — 핀 머리가 144px 아래', () => {
    const surface = rect(0, 844);
    const overlay = rect(80, 64);
    const padding = fitPaddingForOverlay(surface, overlay, PIN_HEIGHT);
    expect(surface.top + padding.top - PIN_HEIGHT).toBeGreaterThanOrEqual(overlay.bottom);
  });

  it('오버레이가 지도보다 크면 위쪽 여백은 지도 높이의 60%로 묶는다(fitBounds가 실패하지 않게)', () => {
    const padding = fitPaddingForOverlay(rect(0, 400), rect(0, 390), PIN_HEIGHT);
    expect(padding.top).toBe(240);
  });

  it('지도 크기를 아직 모르면 기본 여백', () => {
    expect(fitPaddingForOverlay(null, rect(0, 100), PIN_HEIGHT).top).toBe(MAP_FIT_PADDING);
    expect(fitPaddingForOverlay(rect(0, 0), rect(0, 100), PIN_HEIGHT).top).toBe(MAP_FIT_PADDING);
  });
});
