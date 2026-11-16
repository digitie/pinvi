import { act, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LIFT_GAP, useLiftAboveObstacle } from '@/lib/useLiftAboveObstacle';

// jsdom에는 ResizeObserver가 없다 — observe 즉시 한 번 부르는 대역(브라우저의 첫 콜백과 같다).
const observers: Array<() => void> = [];
class FakeResizeObserver {
  constructor(private readonly callback: () => void) {
    observers.push(callback);
  }
  observe() {
    this.callback();
  }
  unobserve() {}
  disconnect() {}
}

const rect = (top: number, height: number) =>
  ({ top, bottom: top + height, height, left: 0, right: 390, width: 390, x: 0, y: top }) as DOMRect;

function Probe() {
  const [element, setElement] = useState<HTMLDivElement | null>(null);
  const lift = useLiftAboveObstacle(element);
  return (
    <div ref={setElement} data-testid="probe" data-lift={lift == null ? 'none' : String(lift)} />
  );
}

function Harness({ panel }: { panel: boolean }) {
  return (
    <section data-map-fit-boundary="" data-testid="boundary">
      <Probe />
      {panel && <div data-map-location-avoid="" data-testid="panel" />}
    </section>
  );
}

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', FakeResizeObserver);
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (
    this: Element,
  ) {
    const id = this.getAttribute('data-testid');
    if (id === 'boundary') return rect(0, 844);
    if (id === 'panel') return rect(500, 280);
    return rect(0, 0);
  });
});
afterEach(() => {
  observers.length = 0;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('useLiftAboveObstacle(내 위치 버튼이 장소 패널에 가려지지 않게)', () => {
  it('패널이 없으면 원래 자리(null)', () => {
    render(<Harness panel={false} />);
    expect(screen.getByTestId('probe')).toHaveAttribute('data-lift', 'none');
  });

  it('패널이 있으면 경계 아래 끝에서 패널 위 끝까지 + 간격만큼 올린다', () => {
    render(<Harness panel />);
    expect(screen.getByTestId('probe')).toHaveAttribute('data-lift', String(844 - 500 + LIFT_GAP));
  });

  it('패널이 나중에 나타나고 사라지는 것을 따라간다', async () => {
    const view = render(<Harness panel={false} />);
    expect(screen.getByTestId('probe')).toHaveAttribute('data-lift', 'none');
    view.rerender(<Harness panel />);
    // MutationObserver 콜백은 microtask로 온다.
    await act(async () => {});
    expect(screen.getByTestId('probe')).toHaveAttribute('data-lift', String(844 - 500 + LIFT_GAP));
    view.rerender(<Harness panel={false} />);
    await act(async () => {});
    expect(screen.getByTestId('probe')).toHaveAttribute('data-lift', 'none');
  });
});
