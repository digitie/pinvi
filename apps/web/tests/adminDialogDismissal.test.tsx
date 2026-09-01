import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Dialog, DialogContent, DialogTitle } from '@/components/admin/ui/dialog';

/**
 * 폼 다이얼로그의 dismissal 정책을 잠근다(T-356 P0).
 *
 * base-ui 기본은 Escape와 바깥 클릭 양쪽으로 닫힌다. 그런데 admin의 생성/운영작업 모달은
 * 전환 전 손수 만든 `role="dialog"` div였고 `onClick`/`onKeyDown`이 **아예 없어** 그 경로가
 * 존재하지 않았다. 닫는 길은 헤더 ×와 푸터 취소뿐이었다.
 *
 * base-ui로 옮기면서 두 경로가 자동으로 생겼고, 호출부가 조건부 마운트라 닫히는 즉시 폼
 * `useState`가 전부 소실된다(POI 생성 모달은 21개). 여백을 한 번 잘못 클릭하거나 IME 조합
 * 취소로 Escape를 누르면 확인 없이 입력이 날아간다.
 *
 * `hasUnsavedInput`은 그 **실수 경로 둘만** 막는다. 명시적 닫기는 그대로 동작해야 한다 —
 * 전부 막으면 사용자가 갇힌다.
 */
function Harness({
  hasUnsavedInput,
  onOpenChange,
}: {
  hasUnsavedInput?: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open hasUnsavedInput={hasUnsavedInput} onOpenChange={onOpenChange}>
      <DialogContent data-testid="panel" viewportProps={{ 'data-testid': 'viewport' }}>
        <DialogTitle>제목</DialogTitle>
        <input aria-label="이름" defaultValue="" />
      </DialogContent>
    </Dialog>
  );
}

describe('admin Dialog — 미저장 폼 입력 보호', () => {
  it('hasUnsavedInput이면 Escape로 닫히지 않는다', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(<Harness hasUnsavedInput onOpenChange={onOpenChange} />);

    await user.click(screen.getByLabelText('이름'));
    await user.keyboard('{Escape}');

    expect(
      onOpenChange.mock.calls.filter(([open]) => open === false),
      'Escape가 닫기를 호출하면 조건부 마운트 호출부에서 폼 입력이 전량 소실된다',
    ).toHaveLength(0);
  });

  it('hasUnsavedInput이면 바깥(viewport 여백) 클릭으로 닫히지 않는다', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(<Harness hasUnsavedInput onOpenChange={onOpenChange} />);

    await user.click(screen.getByTestId('viewport'));

    expect(onOpenChange.mock.calls.filter(([open]) => open === false)).toHaveLength(0);
  });

  it('hasUnsavedInput이어도 입력값은 그대로 남는다 (언마운트되지 않았다는 확인)', async () => {
    const user = userEvent.setup();
    render(<Harness hasUnsavedInput onOpenChange={() => {}} />);

    const input = screen.getByLabelText('이름');
    await user.type(input, '설악산');
    await user.keyboard('{Escape}');

    expect(screen.getByLabelText('이름')).toHaveValue('설악산');
  });

  it('기본값(폼 아님)에서는 Escape로 닫힌다 — 전부 막으면 사용자가 갇힌다', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(<Harness onOpenChange={onOpenChange} />);

    await user.keyboard('{Escape}');

    expect(onOpenChange.mock.calls.some(([open]) => open === false)).toBe(true);
  });
});
