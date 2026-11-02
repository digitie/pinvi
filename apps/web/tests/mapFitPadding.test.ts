import { describe, expect, it } from 'vitest';
import { MAP_FIT_PADDING, fitPaddingForOverlay } from '@/lib/mapFitPadding';

// 2026-11-02 prod e2e — 여행 지도의 fitBounds가 사방 64px만 띄워, 가장 북쪽 장소(영월 고씨굴) 핀이
// 왼쪽 위 장소 검색창 밑에 숨었다(데스크톱·모바일). 위쪽 여백은 오버레이 아래로 내려야 한다.
const rect = (top: number, height: number) => ({ top, bottom: top + height, height });

describe('fitPaddingForOverlay', () => {
  it('오버레이가 없으면 사방 기본 여백', () => {
    expect(fitPaddingForOverlay(rect(200, 700), null)).toEqual({
      top: MAP_FIT_PADDING,
      right: MAP_FIT_PADDING,
      bottom: MAP_FIT_PADDING,
      left: MAP_FIT_PADDING,
    });
  });

  it('위쪽 여백은 오버레이 아래 + 간격(데스크톱: 지도 위 12px부터 64px 높이 검색창)', () => {
    const padding = fitPaddingForOverlay(rect(207, 693), rect(219, 64));
    expect(padding.top).toBe(219 + 64 - 207 + 24);
    expect(padding.bottom).toBe(MAP_FIT_PADDING);
  });

  it('오버레이가 지도보다 크면 위쪽 여백은 지도 높이의 60%로 묶는다(fitBounds가 실패하지 않게)', () => {
    const padding = fitPaddingForOverlay(rect(0, 400), rect(0, 390));
    expect(padding.top).toBe(240);
  });

  it('지도 크기를 아직 모르면 기본 여백', () => {
    expect(fitPaddingForOverlay(null, rect(0, 100)).top).toBe(MAP_FIT_PADDING);
    expect(fitPaddingForOverlay(rect(0, 0), rect(0, 100)).top).toBe(MAP_FIT_PADDING);
  });
});
