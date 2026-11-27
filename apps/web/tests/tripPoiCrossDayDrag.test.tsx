import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { TripPoiList } from '@/components/trips/TripPoiList';
import { type PoiDragSource, usePoiDrag } from '@/lib/usePoiDrag';
import type { PoiMoveTarget } from '@pinvi/domain';
import { TripViewPoiSchema } from '@pinvi/schemas';

function makePoi(n: number, title: string) {
  return TripViewPoiSchema.parse({
    poi_id: `00000000-0000-4000-8000-00000000000${n}`,
    feature_id: null,
    sort_order: `a${n}`,
    title,
    feature: {},
    marker_color: null,
    marker_icon: null,
    feature_resolution_state: 'not_linked',
    user_note: null,
    planned_arrival_at: null,
    planned_departure_at: null,
    budget_amount: null,
    actual_amount: null,
    currency: 'KRW',
    user_url: null,
    rise_set: null,
    feature_link_broken_at: null,
    version: 1,
    created_at: '2026-11-03T00:00:00Z',
    updated_at: '2026-11-03T00:00:00Z',
  });
}

const a = makePoi(1, '불국사');
const b = makePoi(2, '석굴암');
const c = makePoi(3, '첨성대');

function Harness({
  onMove,
  onStepMove,
}: {
  onMove: (source: PoiDragSource, target: PoiMoveTarget) => void;
  onStepMove?: (poiId: string, direction: 'up' | 'down') => void;
}) {
  const drag = usePoiDrag(onMove);
  return (
    <>
      <p id="hint">손잡이 설명</p>
      <section data-testid="day-1">
        <TripPoiList
          pois={[a, b]}
          dayIndex={1}
          editable
          drag={drag}
          onStepMove={onStepMove}
          gripHintId="hint"
        />
      </section>
      <section data-testid="day-2">
        <TripPoiList pois={[c]} dayIndex={2} editable drag={drag} gripHintId="hint" />
      </section>
    </>
  );
}

const rows = (day: 1 | 2) =>
  within(screen.getByTestId(`day-${day}`))
    .getByTestId('trip-poi-list')
    .querySelectorAll(':scope > li');

// jsdom에는 DragEvent가 없다 — clientY를 실은 MouseEvent로 같은 이름의 이벤트를 보낸다(React는 이름으로 받는다).
// `types`를 주면 dataTransfer 형식 목록을 흉내 낸다(장소 끌기가 아닌 끌기 판별).
function drag(
  el: Element,
  type: 'dragstart' | 'dragover' | 'drop' | 'dragend',
  clientY = 0,
  types?: string[],
) {
  const event = new MouseEvent(type, { bubbles: true, cancelable: true, clientY });
  if (types) {
    Object.defineProperty(event, 'dataTransfer', { value: { types, dropEffect: 'none' } });
  }
  return fireEvent(el, event);
}

describe('장소 끌어 놓기 — 일자 사이 이동', () => {
  beforeEach(() => {
    // n번째 행은 n*50 ~ n*50+40px(행 사이 10px 여백) — 가운데보다 위는 그 행 앞, 아래는 그 행 뒤.
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
      this: HTMLElement,
    ) {
      const index = Array.from(this.parentElement?.children ?? []).indexOf(this);
      const top = Math.max(index, 0) * 50;
      return {
        top,
        bottom: top + 40,
        left: 0,
        right: 100,
        width: 100,
        height: 40,
        x: 0,
        y: top,
        toJSON: () => ({}),
      };
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it('다른 일자의 행 위쪽 절반에 놓으면 그 행 앞으로 옮긴다', () => {
    const onMove = vi.fn();
    render(<Harness onMove={onMove} />);
    const [source] = rows(1);
    const [target] = rows(2);
    drag(source!, 'dragstart');
    expect(drag(target!, 'dragover', 5)).toBe(false); // preventDefault — 놓을 수 있는 자리
    expect(target).toHaveAttribute('data-drop-indicator', 'before');
    drag(target!, 'drop', 5);
    expect(onMove).toHaveBeenCalledWith(
      { poiId: a.poi_id, dayIndex: 1 },
      { dayIndex: 2, beforePoiId: c.poi_id },
    );
    // 놓은 뒤 표시가 지워진다.
    expect(target).not.toHaveAttribute('data-drop-indicator');
  });

  it('다른 일자의 마지막 행 아래쪽 절반은 그 일자 맨 끝이다', () => {
    const onMove = vi.fn();
    render(<Harness onMove={onMove} />);
    drag(rows(1)[1]!, 'dragstart');
    drag(rows(2)[0]!, 'dragover', 35);
    expect(rows(2)[0]).toHaveAttribute('data-drop-indicator', 'after');
    drag(rows(2)[0]!, 'drop', 35);
    expect(onMove).toHaveBeenCalledWith(
      { poiId: b.poi_id, dayIndex: 1 },
      { dayIndex: 2, beforePoiId: null },
    );
  });

  it('같은 일자 안 이동도 같은 경로다 — 제자리 드롭은 자리 표시를 그리지 않는다', () => {
    const onMove = vi.fn();
    render(<Harness onMove={onMove} />);
    const [first, second] = rows(1);
    drag(second!, 'dragstart');
    drag(first!, 'dragover', 5);
    expect(first).toHaveAttribute('data-drop-indicator', 'before');
    drag(first!, 'drop', 5);
    expect(onMove).toHaveBeenLastCalledWith(
      { poiId: b.poi_id, dayIndex: 1 },
      { dayIndex: 1, beforePoiId: a.poi_id },
    );

    // 첫 행을 자기 아래쪽 절반에 → 바로 다음 장소 앞 = 제자리.
    drag(first!, 'dragstart');
    drag(first!, 'dragover', 35);
    expect(first).not.toHaveAttribute('data-drop-indicator');
    expect(second).not.toHaveAttribute('data-drop-indicator');
    expect(first!.className).toContain('opacity-50');
    drag(first!, 'dragend');
    expect(first!.className ?? '').not.toContain('opacity-50');
  });

  it('행 사이 여백에 놓아도 가까운 틈으로 간다(일자 맨 끝으로 튀지 않는다)', () => {
    const onMove = vi.fn();
    render(<Harness onMove={onMove} />);
    const list = within(screen.getByTestId('day-1')).getByTestId('trip-poi-list');
    drag(rows(2)[0]!, 'dragstart');
    // 45px = 첫 행(0~40)과 둘째 행(50~90) 사이 여백 — 이벤트는 행이 아니라 목록(ol)에 닿는다.
    expect(drag(list, 'dragover', 45)).toBe(false);
    expect(rows(1)[1]).toHaveAttribute('data-drop-indicator', 'before');
    drag(list, 'drop', 45);
    expect(onMove).toHaveBeenCalledWith(
      { poiId: c.poi_id, dayIndex: 2 },
      { dayIndex: 1, beforePoiId: b.poi_id },
    );
  });

  it('장소 끌기가 아닌 끌기(파일·글자)는 막지 않는다', () => {
    const onMove = vi.fn();
    render(<Harness onMove={onMove} />);
    // 시작한 장소 끌기가 없다.
    expect(drag(rows(2)[0]!, 'dragover', 5)).toBe(true);
    drag(rows(2)[0]!, 'drop', 5);
    // 장소 끌기 상태가 남아 있어도(행이 사라져 dragend를 못 받은 경우) 전용 형식이 없는 끌기는 받지 않는다.
    drag(rows(1)[0]!, 'dragstart');
    expect(drag(rows(2)[0]!, 'dragover', 5, ['Files'])).toBe(true);
    expect(onMove).not.toHaveBeenCalled();
    // 전용 형식이 있으면 받는다.
    expect(drag(rows(2)[0]!, 'dragover', 5, ['application/x-pinvi-poi'])).toBe(false);
    // 놓을 자리가 아닌 곳에 놓인 끌기(window까지 올라간 drop)는 끌기 상태를 끝낸다.
    drag(document.body, 'drop', 5, ['text/plain']);
    expect(drag(rows(2)[0]!, 'dragover', 5, ['application/x-pinvi-poi'])).toBe(true);
    expect(onMove).not.toHaveBeenCalled();
  });

  it('장소 줄 버튼에서 Alt+위·아래 화살표로 한 칸 이동을 요청하고 위치·사용법을 설명한다', () => {
    const onStepMove = vi.fn();
    render(<Harness onMove={vi.fn()} onStepMove={onStepMove} />);
    const day1 = within(screen.getByTestId('day-1'));
    const first = day1.getByRole('button', { name: /불국사/ });
    const second = day1.getByRole('button', { name: /석굴암/ });
    expect(second).toHaveAccessibleDescription(/1일차 2번째\..*손잡이 설명/);
    expect(first).toHaveAttribute('aria-keyshortcuts', 'Alt+ArrowUp Alt+ArrowDown');
    // 손잡이는 마우스 전용 표시로 남는다(Firefox는 버튼 위에서 끌기를 시작하지 못한다).
    expect(rows(1)[0]!.querySelector('[title="끌어서 순서 변경"]')).toHaveAttribute(
      'aria-hidden',
      'true',
    );
    fireEvent.keyDown(second, { key: 'ArrowDown', altKey: true });
    fireEvent.keyDown(first, { key: 'ArrowUp', altKey: true });
    // Alt 없는 화살표·다른 키는 이동이 아니다.
    fireEvent.keyDown(first, { key: 'ArrowDown' });
    fireEvent.keyDown(first, { key: 'Enter', altKey: true });
    expect(onStepMove.mock.calls).toEqual([
      [b.poi_id, 'down'],
      [a.poi_id, 'up'],
    ]);
  });

  it('편집할 수 없으면 끌기·손잡이가 없다', () => {
    const drag = { source: null, target: null } as unknown as ReturnType<typeof usePoiDrag>;
    render(<TripPoiList pois={[a]} dayIndex={1} drag={drag} />);
    expect(screen.queryByTitle('끌어서 순서 변경')).toBeNull();
    expect(screen.getByRole('button', { name: /불국사/ })).not.toHaveAttribute('aria-keyshortcuts');
    expect(screen.getByTestId('trip-poi-list').querySelector('li')).toHaveAttribute(
      'draggable',
      'false',
    );
  });
});
