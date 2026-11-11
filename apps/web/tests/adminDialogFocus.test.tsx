import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useRef, useState } from 'react';
import { Dialog, DialogContent, DialogTitle } from '@/components/admin/ui/dialog';

function ConditionalDialog({ explicitTarget }: { explicitTarget: boolean }) {
  const [open, setOpen] = useState(false);
  const fallback = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button ref={fallback}>목록</button>
      <button onClick={() => setOpen(true)}>열기</button>
      {open ? (
        <Dialog open onOpenChange={setOpen}>
          <DialogContent
            finalFocus={explicitTarget ? fallback : undefined}
            aria-describedby={undefined}
          >
            <DialogTitle>작업</DialogTitle>
            <button onClick={() => setOpen(false)}>취소</button>
          </DialogContent>
        </Dialog>
      ) : null}
    </>
  );
}
afterEach(() => vi.restoreAllMocks());
describe('관리자 Dialog 조건부 마운트의 포커스 복귀', () => {
  it.each([false, true])('DialogTrigger 없이 열고 닫기: 명시적 대상 %s', async (explicitTarget) => {
    vi.spyOn(HTMLElement.prototype, 'getClientRects').mockReturnValue([
      {},
    ] as unknown as DOMRectList);
    const user = userEvent.setup();
    render(<ConditionalDialog explicitTarget={explicitTarget} />);
    await user.click(screen.getByRole('button', { name: '열기' }));
    await user.click(screen.getByRole('button', { name: '취소' }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: explicitTarget ? '목록' : '열기' })).toHaveFocus(),
    );
  });
});
