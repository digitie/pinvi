import type { VirtualItem } from '@tanstack/react-virtual';

/**
 * 가상화 스페이서 윈도우 계산 — 보이는 첫/마지막 가상 행 기준으로 위/아래 스페이서 높이를 구한다.
 * 시맨틱 `<table>`에서 absolute/transform 대신 위·아래 스페이서 `<tr>`로 스크롤 높이를 채우기 위한
 * 순수 함수(렌더와 분리해 단위 테스트 가능, node 환경).
 */
export function computeSpacerWindow(
  items: ReadonlyArray<Pick<VirtualItem, 'start' | 'end'>>,
  totalSize: number,
): { paddingTop: number; paddingBottom: number } {
  const first = items[0];
  const last = items[items.length - 1];
  if (!first || !last) {
    return { paddingTop: 0, paddingBottom: 0 };
  }
  return {
    paddingTop: Math.max(0, first.start),
    paddingBottom: Math.max(0, totalSize - last.end),
  };
}
