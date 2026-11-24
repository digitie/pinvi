import { expect, type Locator } from '@playwright/test';

/**
 * 관리자 생성 Dialog 본문이 좁은 화면에서 가로로 넘치지 않는지 잰다.
 *
 * 공통 `DialogContent` grid 칸이 자식 min-content만큼 커지면(ui 0.2.6 암시적 auto 칸) 모달 전체가
 * 가로로 스크롤되고, 칸이 고정돼도(ui 0.2.7 minmax(0,1fr)) 본문 안의 auto grid·폭 없는 입력·
 * 끊을 곳 없는 긴 글은 자기 상자 밖으로 넘친다. 두 경우를 모두 잡도록
 * - 모달·본문 래퍼·검색 결과 목록의 scrollWidth ≤ clientWidth
 * - 본문 안 form·label·입력·버튼·문단 상자가 본문 패딩 안
 * - 버튼·문단·라벨 안 내용이 자기 상자를 넘지 않음(scrollWidth ≤ clientWidth)
 * 을 함께 본다. `required` testid가 측정 대상에 실제로 있었는지도 확인해 빈 측정으로 통과하지 않게 한다.
 */
export async function expectDialogBodyFits(
  dialog: Locator,
  bodyTestId: string,
  required: string[],
): Promise<{ searchSameRow: boolean; fieldsSameRow: boolean }> {
  // 열림 애니메이션(zoom-in-95)이 끝난 뒤 잰다 — scale 중 rect는 scale 안 된 padding과 어긋난다.
  await dialog.evaluate((element) =>
    Promise.all(element.getAnimations({ subtree: true }).map((animation) => animation.finished)),
  );
  const geometry = await dialog.evaluate((content, id) => {
    const body = content.querySelector<HTMLElement>(`[data-testid="${id}"]`);
    if (!body) return null;
    const box = (element: Element) => element.getBoundingClientRect();
    const inner = (element: Element) => {
      const rect = box(element);
      const style = getComputedStyle(element);
      return {
        left: rect.left + parseFloat(style.borderLeftWidth) + parseFloat(style.paddingLeft),
        right: rect.right - parseFloat(style.borderRightWidth) - parseFloat(style.paddingRight),
      };
    };
    const bodyInner = inner(body);
    const contentInner = inner(content);
    const label = (element: Element) =>
      element.getAttribute('data-testid') ?? element.tagName.toLowerCase();
    const measured = [
      ...body.querySelectorAll('form, label, input, select, textarea, button, p, [data-testid]'),
    ];
    const outside = measured
      .map((element) => ({
        what: label(element),
        left: box(element).left,
        right: box(element).right,
      }))
      .filter((item) => item.left < bodyInner.left - 0.5 || item.right > bodyInner.right + 0.5);
    // 입력·선택은 값·placeholder 스크롤 폭을 내므로 상자 위치만 본다.
    const contentOverflow = measured
      .filter((element) => !element.matches('input, select, textarea'))
      .map((element) => ({
        what: label(element),
        overflow: element.scrollWidth - element.clientWidth,
      }))
      // clientWidth·scrollWidth는 정수로 반올림되므로 1px은 허용한다.
      .filter((item) => item.overflow > 1);
    const searchLabel = body.querySelector('input[type="search"]')?.closest('label');
    const searchSubmit = searchLabel?.closest('form')?.querySelector('button[type="submit"]');
    // 두 번째 form(생성 form)의 첫 두 입력 — md 이상 두 열, 미만 한 열.
    const [firstField, secondField] = [...body.querySelectorAll('form:not(:first-of-type) input')];
    return {
      dialogOverflow: content.scrollWidth - content.clientWidth,
      bodyOverflow: body.scrollWidth - body.clientWidth,
      bodyLeft: box(body).left,
      bodyRight: box(body).right,
      contentInner,
      outside,
      contentOverflow,
      seen: measured.map(label),
      searchSameRow:
        !!searchLabel &&
        !!searchSubmit &&
        Math.abs(box(searchLabel).bottom - box(searchSubmit).bottom) < 1 &&
        box(searchSubmit).left >= box(searchLabel).right,
      fieldsSameRow:
        !!firstField && !!secondField && Math.abs(box(firstField).top - box(secondField).top) < 1,
    };
  }, bodyTestId);

  expect(geometry, `본문 ${bodyTestId}`).not.toBeNull();
  const g = geometry!;
  for (const id of required) expect(g.seen, `측정 대상 ${id}`).toContain(id);
  expect(g.dialogOverflow, 'Dialog 가로 스크롤').toBeLessThanOrEqual(0);
  expect(g.bodyLeft).toBeGreaterThanOrEqual(g.contentInner.left - 0.5);
  expect(g.bodyRight).toBeLessThanOrEqual(g.contentInner.right + 0.5);
  expect(g.bodyOverflow, '본문 래퍼 넘침').toBeLessThanOrEqual(0);
  expect(g.outside, '본문 패딩 밖 상자').toEqual([]);
  expect(g.contentOverflow, '자기 상자를 넘는 내용').toEqual([]);
  return { searchSameRow: g.searchSameRow, fieldsSameRow: g.fieldsSameRow };
}
