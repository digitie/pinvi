import { describe, expect, it } from 'vitest';
import {
  MAP_FIT_PADDING,
  OVERLAY_GAP,
  fitOverlayRect,
  fitPaddingForOverlay,
  fitPanelRect,
  pinBoxIntersects,
} from '@/lib/mapFitPadding';

// 2026-11-02 prod e2e — 여행 지도의 fitBounds가 사방 64px만 띄워, 가장 북쪽 장소(영월 고씨굴) 핀이
// 왼쪽 위 장소 검색창 밑에 숨었다(데스크톱·모바일). 위쪽 여백은 오버레이 아래로 내려야 한다.
const rect = (top: number, height: number) => ({ top, bottom: top + height, height });
const PIN_HEIGHT = 48; // 여행 지도 핀 상자: size 27 × 1.5 × 선택 배율 1.18(실지도 측정 ≈49px)
const domBox = (top: number, height: number) => () =>
  ({
    x: 0,
    y: top,
    top,
    left: 0,
    width: 300,
    right: 300,
    height,
    bottom: top + height,
    toJSON: () => ({}),
  }) as DOMRect;

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

  it('피할 영역은 검색 입력 줄 — 교통 패널·검색 결과 목록은 넣지 않는다(리뷰 #619)', () => {
    // 스택: [검색 카드(form + 펼쳐진 결과 목록)] + [교통 패널]. 스택 전체는 80~420px.
    const stack = document.createElement('div');
    const card = document.createElement('div');
    const form = document.createElement('form');
    form.setAttribute('data-map-fit-anchor', '');
    const results = document.createElement('ul');
    card.append(form, results);
    const transport = document.createElement('div');
    stack.append(card, transport);
    stack.getBoundingClientRect = domBox(80, 340);
    card.getBoundingClientRect = domBox(80, 300);
    form.getBoundingClientRect = domBox(88, 44);
    transport.getBoundingClientRect = domBox(388, 32);

    const overlay = fitOverlayRect(stack);
    expect(overlay?.bottom).toBe(132);
    const padding = fitPaddingForOverlay(rect(0, 844), overlay, PIN_HEIGHT);
    expect(padding.top).toBe(132 + PIN_HEIGHT + OVERLAY_GAP);
  });

  it('입력 줄 표시가 없으면 스택의 첫 자식(항상 보이는 카드), 스택이 없으면 null', () => {
    const stack = document.createElement('div');
    const card = document.createElement('div');
    stack.append(card, document.createElement('div'));
    card.getBoundingClientRect = domBox(8, 40);
    expect(fitOverlayRect(stack)?.bottom).toBe(48);
    expect(fitOverlayRect(null)).toBeNull();
    expect(fitOverlayRect(document.createElement('div'))).toBeNull();
  });

  it('교통 패널은 상시 부분만(사건 목록 제외), 없으면 null', () => {
    const stack = document.createElement('div');
    const panel = document.createElement('div');
    panel.setAttribute('data-map-fit-panel', '');
    const incidents = document.createElement('div');
    incidents.setAttribute('data-map-fit-transient', '');
    panel.append(incidents);
    stack.append(document.createElement('div'), panel);
    panel.getBoundingClientRect = domBox(152, 356);
    incidents.getBoundingClientRect = domBox(290, 218);

    expect(fitPanelRect(stack)).toEqual({
      left: 0,
      right: 300,
      top: 152,
      bottom: 290,
      height: 138,
    });
    expect(fitPanelRect(document.createElement('div'))).toBeNull();
    expect(fitPanelRect(null)).toBeNull();
  });

  it('핀 상자(앵커 위로 높이, 좌우로 폭/2)가 패널과 겹치는지', () => {
    // 모바일 재현(리뷰 #619): 패널 x 8~264, y 152~288. 가장 북쪽 핀 앵커가 (72, 207).
    const panel = { left: 8, right: 264, top: 152, bottom: 288, height: 136 };
    expect(pinBoxIntersects(72, 207, 27, PIN_HEIGHT, panel)).toBe(true);
    // 패널 오른쪽 바깥
    expect(pinBoxIntersects(300, 207, 27, PIN_HEIGHT, panel)).toBe(false);
    // 핀 머리까지 패널 아래
    expect(pinBoxIntersects(72, 288 + PIN_HEIGHT + 1, 27, PIN_HEIGHT, panel)).toBe(false);
  });

  it('지도 크기를 아직 모르면 기본 여백', () => {
    expect(fitPaddingForOverlay(null, rect(0, 100), PIN_HEIGHT).top).toBe(MAP_FIT_PADDING);
    expect(fitPaddingForOverlay(rect(0, 0), rect(0, 100), PIN_HEIGHT).top).toBe(MAP_FIT_PADDING);
  });
});
