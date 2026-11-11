import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';

describe('ConfirmDialog', () => {
  it('open=false면 아무것도 렌더하지 않는다', () => {
    render(
      <ConfirmDialog open={false} title="삭제할까요?" onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.queryByTestId('confirm-dialog')).not.toBeInTheDocument();
  });

  it('title/description과 children을 렌더한다', () => {
    render(
      <ConfirmDialog
        open
        title="일자를 삭제할까요?"
        description="이 작업은 되돌릴 수 없습니다."
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      >
        <span>POI 3곳이 함께 삭제됩니다.</span>
      </ConfirmDialog>,
    );
    expect(screen.getByTestId('confirm-dialog-title')).toHaveTextContent('일자를 삭제할까요?');
    const description = screen.getByText('이 작업은 되돌릴 수 없습니다.');
    expect(description).toBeInTheDocument();
    expect(screen.getByTestId('confirm-dialog')).toHaveAttribute(
      'aria-describedby',
      description.id,
    );
    expect(screen.getByText('POI 3곳이 함께 삭제됩니다.')).toBeInTheDocument();
  });

  it('확인/취소 버튼이 콜백을 호출한다', () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        open
        title="삭제할까요?"
        confirmLabel="삭제"
        cancelLabel="취소"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    fireEvent.click(screen.getByTestId('confirm-dialog-confirm'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId('confirm-dialog-cancel'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('danger tone은 확인 버튼을 파괴적 스타일로 렌더한다', () => {
    render(
      <ConfirmDialog
        open
        tone="danger"
        title="삭제할까요?"
        confirmLabel="삭제"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByTestId('confirm-dialog-confirm')).toHaveClass('bg-error-text');
  });

  it('busy면 버튼을 비활성화한다', () => {
    render(<ConfirmDialog open busy title="삭제할까요?" onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByTestId('confirm-dialog-confirm')).toBeDisabled();
    expect(screen.getByTestId('confirm-dialog-cancel')).toBeDisabled();
  });

  it('busy로 열려도 포커스가 다이얼로그 안으로 들어간다', async () => {
    render(<ConfirmDialog open busy title="삭제할까요?" onConfirm={vi.fn()} onCancel={vi.fn()} />);
    // busy면 취소 버튼이 disabled라 훅이 패널로 폴백 포커스한다.
    await waitFor(() => expect(screen.getByTestId('confirm-dialog')).toHaveFocus());
  });

  it('커스텀 testId 접두어를 적용한다', () => {
    render(
      <ConfirmDialog
        open
        testId="day-delete-confirm"
        title="삭제할까요?"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByTestId('day-delete-confirm')).toBeInTheDocument();
    expect(screen.getByTestId('day-delete-confirm-confirm')).toBeInTheDocument();
  });
});

describe('공통 AlertDialog 취소 정책', () => {
  it('확인 요청 중 버튼이 disabled돼도 포커스와 취소 잠금은 패널 안에 남는다', async () => {
    const cancel = vi.fn();
    function PendingConfirm() {
      const [busy, setBusy] = useState(false);
      return (
        <ConfirmDialog
          open
          title="삭제"
          busy={busy}
          onCancel={cancel}
          onConfirm={() => setBusy(true)}
        />
      );
    }
    const user = userEvent.setup();
    render(<PendingConfirm />);
    await user.click(screen.getByTestId('confirm-dialog-confirm'));
    expect(screen.getByTestId('confirm-dialog')).toHaveFocus();
    await user.click(screen.getByTestId('confirm-dialog-backdrop'));
    await user.keyboard('{Escape}');
    expect(screen.getByTestId('confirm-dialog')).toHaveFocus();
    expect(cancel).not.toHaveBeenCalled();
  });

  it('초기 포커스는 취소 버튼에 있고 Escape는 취소만 호출한다', async () => {
    const cancel = vi.fn(),
      confirm = vi.fn();
    render(<ConfirmDialog open title="삭제" onCancel={cancel} onConfirm={confirm} />);
    expect(screen.getByTestId('confirm-dialog-cancel')).toHaveFocus();
    await userEvent.setup().keyboard('{Escape}');
    expect(cancel).toHaveBeenCalledTimes(1);
    expect(confirm).not.toHaveBeenCalled();
  });
  it('바깥 scrim 클릭은 취소로 연결되고 busy이면 막는다', async () => {
    const cancel = vi.fn(),
      user = userEvent.setup();
    const { rerender } = render(
      <ConfirmDialog open title="삭제" onCancel={cancel} onConfirm={() => {}} />,
    );
    await user.click(screen.getByTestId('confirm-dialog-backdrop'));
    expect(cancel).toHaveBeenCalledTimes(1);
    rerender(<ConfirmDialog open busy title="삭제" onCancel={cancel} onConfirm={() => {}} />);
    await user.click(screen.getByTestId('confirm-dialog-backdrop'));
    await user.keyboard('{Escape}');
    expect(cancel).toHaveBeenCalledTimes(1);
  });
  it('패널에서 시작해 scrim으로 놓는 drag는 취소하지 않는다', async () => {
    const cancel = vi.fn(),
      user = userEvent.setup();
    render(<ConfirmDialog open title="삭제" onCancel={cancel} onConfirm={() => {}} />);
    const panel = screen.getByTestId('confirm-dialog'),
      overlay = screen.getByTestId('confirm-dialog-backdrop');
    await user.pointer([
      { keys: '[MouseLeft>]', target: panel },
      { target: overlay },
      { keys: '[/MouseLeft]', target: overlay },
    ]);
    expect(cancel).not.toHaveBeenCalled();
  });
});
