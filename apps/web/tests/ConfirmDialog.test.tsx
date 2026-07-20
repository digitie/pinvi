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
    expect(screen.getByText('이 작업은 되돌릴 수 없습니다.')).toBeInTheDocument();
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
    render(
      <ConfirmDialog open busy title="삭제할까요?" onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );
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
