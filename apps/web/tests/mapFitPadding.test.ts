import { describe, expect, it } from 'vitest';
import {
  MAP_FIT_PADDING,
  MIN_EDGE_PADDING,
  MIN_FIT_SPAN,
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
    const padding = fitPaddingForOverlay(rect(0, 600), rect(0, 590), PIN_HEIGHT);
    expect(padding.top).toBe(360);
  });

  describe('낮은 지도 — 맞춤 폭이 MIN_FIT_SPAN보다 좁을 때(#704 후속)', () => {
    const span = (height: number, p: { top: number; bottom: number }) => height - p.top - p.bottom;

    it('아래 여백부터 줄이고, 위 여백은 오버레이 clearance를 지킨다', () => {
      // 데스크톱 낮은 창: 지도 240px, 검색 입력 줄 88~132px. clearance 204 → 60% 상한 144.
      const padding = fitPaddingForOverlay(rect(0, 240), rect(88, 44), PIN_HEIGHT);
      expect(padding.top).toBe(144);
      expect(padding.bottom).toBe(MIN_EDGE_PADDING);
      expect(span(240, padding)).toBeGreaterThan(0);
    });

    it('오버레이가 없으면 아래만 줄여 MIN_FIT_SPAN을 맞추고 위는 기본 여백을 지킨다', () => {
      const padding = fitPaddingForOverlay(rect(0, 200), null, PIN_HEIGHT);
      expect(padding.top).toBe(MAP_FIT_PADDING);
      expect(padding.bottom).toBe(200 - MIN_FIT_SPAN - MAP_FIT_PADDING);
      expect(span(200, padding)).toBe(MIN_FIT_SPAN);
    });

    it('임계 근처에서 위 여백이 튀지 않는다(연속)', () => {
      const tops = [250, 249, 248, 240, 230].map(
        (height) => fitPaddingForOverlay(rect(0, height), rect(88, 44), PIN_HEIGHT).top,
      );
      for (let i = 1; i < tops.length; i += 1) {
        expect(Math.abs(tops[i]! - tops[i - 1]!)).toBeLessThanOrEqual(12);
      }
    });

    it('아래 칩 clearance보다 위 오버레이 clearance를 먼저 지킨다', () => {
      const padding = fitPaddingForOverlay(rect(300, 220), rect(312, 90), PIN_HEIGHT, rect(470, 36));
      // clearance 174 → 60% 상한 132. 아래 칩 clearance 74는 8까지 줄어든다.
      expect(padding.top).toBe(132);
      expect(padding.bottom).toBe(MIN_EDGE_PADDING);
    });

    it('아주 낮은 지도도 위 여백은 핀 머리 높이 이상, 맞춤 폭은 양수', () => {
      for (const height of [120, 100, 80, 72]) {
        const padding = fitPaddingForOverlay(rect(0, height), rect(0, 30), PIN_HEIGHT);
        expect(padding.top).toBeGreaterThanOrEqual(PIN_HEIGHT);
        expect(span(height, padding)).toBeGreaterThan(0);
      }
      // 핀 높이보다도 낮은 지도도 fitBounds 폭은 남긴다.
      for (const height of [60, 40, 20]) {
        expect(span(height, fitPaddingForOverlay(rect(0, height), null, PIN_HEIGHT))).toBeGreaterThan(0);
      }
      const tiny = fitPaddingForOverlay(rect(0, 200), rect(0, 150), PIN_HEIGHT);
      expect(tiny.top).toBeGreaterThanOrEqual(PIN_HEIGHT);
      expect(span(200, tiny)).toBeGreaterThan(0);
    });
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

    // 스택은 max-height + 스크롤 — 보이는 부분(스택 아래 끝)까지만 센다
    stack.getBoundingClientRect = domBox(80, 180);
    expect(fitPanelRect(stack)?.bottom).toBe(260);
  });

  it('핀 상자(앵커 위로 높이, 좌우로 폭/2)가 패널과 겹치는지', () => {
    // 모바일 재현(리뷰 #619): 패널 x 8~264, y 152~288. 가장 북쪽 핀 앵커가 (72, 207).
    const panel = { left: 8, right: 264, top: 152, bottom: 288, height: 136 };
    expect(pinBoxIntersects(72, 207, 27, PIN_HEIGHT, panel)).toBe(true);
    // 패널 오른쪽 바깥(반폭 경계 포함), 패널 위쪽 바깥
    expect(pinBoxIntersects(300, 207, 27, PIN_HEIGHT, panel)).toBe(false);
    expect(pinBoxIntersects(264 + 13.5, 207, 27, PIN_HEIGHT, panel)).toBe(false);
    expect(pinBoxIntersects(264 + 13, 207, 27, PIN_HEIGHT, panel)).toBe(true);
    expect(pinBoxIntersects(72, 150, 27, PIN_HEIGHT, panel)).toBe(false);
    // 핀 머리까지 패널 아래
    expect(pinBoxIntersects(72, 288 + PIN_HEIGHT + 1, 27, PIN_HEIGHT, panel)).toBe(false);
  });

  it('지도 크기를 아직 모르면 기본 여백', () => {
    expect(fitPaddingForOverlay(null, rect(0, 100), PIN_HEIGHT).top).toBe(MAP_FIT_PADDING);
    expect(fitPaddingForOverlay(rect(0, 0), rect(0, 100), PIN_HEIGHT).top).toBe(MAP_FIT_PADDING);
  });
});

describe('하단 통계 칩 맞춤 여백', () => {
  it('핀 꼬리를 통계 칩 위로 띄우며 위쪽 여백도 보존한다', () => {
    const surface = rect(0, 800);
    const stats = rect(700, 36);
    const padding = fitPaddingForOverlay(surface, rect(88, 44), PIN_HEIGHT, stats);
    expect(padding.top).toBe(132 + PIN_HEIGHT + OVERLAY_GAP);
    expect(surface.bottom - padding.bottom).toBeLessThanOrEqual(stats.top - OVERLAY_GAP);
  });

  it('상하 오버레이가 높아도 fitBounds에 양수 높이를 남긴다', () => {
    const padding = fitPaddingForOverlay(rect(0, 400), rect(0, 390), PIN_HEIGHT, rect(200, 150));
    expect(padding.top + padding.bottom).toBeLessThan(400);
  });
});

it('검색 아래 경로·영역 컨트롤과 교통 패널 사이의 숨은 핀도 피한다', () => {
  const stack = document.createElement('div');
  const geometry = document.createElement('div');
  const transport = document.createElement('div');
  geometry.setAttribute('data-map-fit-panel', '');
  transport.setAttribute('data-map-fit-panel', '');
  geometry.getBoundingClientRect = domBox(152, 54);
  transport.getBoundingClientRect = domBox(214, 152);
  stack.append(geometry, transport);
  const panel = fitPanelRect(stack)!;
  expect(panel.top).toBe(152);
  expect(panel.bottom).toBe(366);
  // 실제 2핀 mobile 회귀: 꼬리207은 교통 패널214 위지만 머리는 경로/영역 카드에 가렸다.
  expect(pinBoxIntersects(198, 207, 27, PIN_HEIGHT, panel)).toBe(true);
});
