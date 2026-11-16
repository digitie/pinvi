'use client';

import { useEffect, useState } from 'react';

/** 지도 경계 안에서 아래쪽 떠 있는 컨트롤이 피해야 할 패널 표시(예: 모바일 장소 정보 패널). */
export const LIFT_OBSTACLE_ATTR = 'data-map-location-avoid';
/** 패널 위 끝과 컨트롤 사이 간격(px). */
export const LIFT_GAP = 8;

/**
 * 같은 지도 경계(`[data-map-fit-boundary]`, 없으면 부모) 안의 `[data-map-location-avoid]` 패널이 보이면,
 * 컨트롤을 그 패널 위로 올릴 `bottom`(px, 경계 아래 끝 기준)을 돌려준다. 패널이 없으면 null(원래 자리).
 *
 * 구글 지도처럼 장소 패널이 아래에서 올라오면 "내 위치" 버튼이 패널 위로 함께 올라간다 — 패널에 가려지지
 * 않는다. 패널이 나타나고 사라지거나 높이가 바뀌는 것(내용이 늦게 채워짐·항목 펼침)을 따라간다.
 */
export function useLiftAboveObstacle(element: HTMLElement | null): number | null {
  const [lift, setLift] = useState<number | null>(null);
  useEffect(() => {
    if (!element || typeof ResizeObserver === 'undefined') return undefined;
    const boundary =
      element.closest('[data-map-fit-boundary]') ?? element.parentElement ?? element;
    let watched: Element | null = null;
    const update = () => {
      const obstacle = boundary.querySelector(`[${LIFT_OBSTACLE_ATTR}]`);
      if (obstacle !== watched) {
        const previous = watched;
        watched = obstacle;
        if (previous) resize.unobserve(previous);
        if (obstacle) resize.observe(obstacle);
      }
      const rect = obstacle?.getBoundingClientRect();
      if (!rect || rect.height <= 0) {
        setLift(null);
        return;
      }
      const bounds = boundary.getBoundingClientRect();
      setLift(Math.round(bounds.bottom - rect.top + LIFT_GAP));
    };
    const resize = new ResizeObserver(update);
    resize.observe(boundary);
    // 패널은 선택에 따라 붙었다 떨어진다 — 경계 안 자식 변화를 본다(첫 측정은 ResizeObserver 첫 콜백).
    const mutations = new MutationObserver(update);
    mutations.observe(boundary, { childList: true, subtree: true });
    return () => {
      resize.disconnect();
      mutations.disconnect();
    };
  }, [element]);
  return lift;
}
